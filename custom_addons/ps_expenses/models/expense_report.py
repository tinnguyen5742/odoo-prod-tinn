import json
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class PsTeExpenseReport(models.Model):
    _name = 'ps.te.expense.report'
    _description = 'PS T&E Expense Report'
    _rec_name = 'reference'
    _order = 'id desc'
    _trip_unique = models.Constraint('UNIQUE(original_trip_id)', 'A trip may have only one expense report.')
    _adjustment_unique = models.Constraint('UNIQUE(adjustment_id)', 'Only one expense version is allowed per adjustment.')

    reference = fields.Char(required=True, readonly=True, index=True)
    trip_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True, ondelete='restrict', index=True)
    adjustment_id = fields.Many2one('ps.te.adjustment', readonly=True, ondelete='restrict', index=True)
    original_trip_id = fields.Many2one('ps.te.trip.request', compute='_original_identity', store=True, readonly=True)
    owner_id = fields.Many2one('res.users', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', required=True, readonly=True)
    finance_reviewer_id = fields.Many2one('res.users', required=True, readonly=True, index=True)
    finance_assignment_valid = fields.Boolean(compute='_compute_assignment', store=True)
    policy_reference = fields.Char(required=True, readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Finance Review'),
        ('returned', 'Correction Required'), ('reviewed', 'Expense Basis Reviewed'),
    ], required=True, default='draft', readonly=True, index=True)
    revision = fields.Integer(required=True, default=1, readonly=True)
    submitted_at = fields.Datetime(readonly=True)
    submission_receipt = fields.Char(readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    reviewed_revision = fields.Integer(readonly=True)
    basis_locked = fields.Boolean(default=False, readonly=True)
    settlement_lock_id = fields.Many2one('ps.te.settlement', readonly=True, ondelete='restrict')
    zero_expense_declared = fields.Boolean(default=False, readonly=True)
    zero_expense_reason = fields.Text(readonly=True)
    zero_expense_declared_by_id = fields.Many2one('res.users', readonly=True)
    zero_expense_declared_at = fields.Datetime(readonly=True)
    zero_expense_cancellation_revision = fields.Integer(readonly=True)
    zero_expense_review_reason = fields.Text(readonly=True)
    zero_expense_reviewed_by_id = fields.Many2one('res.users', readonly=True)
    zero_expense_reviewed_at = fields.Datetime(readonly=True)
    line_ids = fields.One2many('ps.te.expense.line', 'report_id', readonly=True)
    event_ids = fields.One2many('ps.te.expense.event', 'report_id', readonly=True)
    claimed_total = fields.Monetary(compute='_compute_totals')
    accepted_total = fields.Monetary(compute='_compute_totals')
    refused_total = fields.Monetary(compute='_compute_totals')
    unresolved_total = fields.Monetary(compute='_compute_totals')
    accepted_basis_ready = fields.Boolean(compute='_compute_totals')
    correction_hold = fields.Boolean(related='trip_id.correction_hold', readonly=True)
    native_source_ready = fields.Boolean(compute='_native_source_ready', string='Cơ sở có nguồn Expenses chuẩn')

    @api.depends('line_ids.native_expense_id')
    def _native_source_ready(self):
        for report in self:
            report.native_source_ready = all(line.native_expense_id for line in report.line_ids)

    @api.depends('trip_id', 'adjustment_id')
    def _original_identity(self):
        for report in self:
            report.original_trip_id = report.trip_id if not report.adjustment_id else False

    @api.depends('finance_reviewer_id', 'company_id.ps_te_finance_reviewer_id')
    def _compute_assignment(self):
        for report in self:
            report.finance_assignment_valid = report.finance_reviewer_id == report.company_id.ps_te_finance_reviewer_id

    @api.depends(
        'state', 'revision', 'reviewed_revision', 'line_ids.claimed_amount', 'native_source_ready',
        'line_ids.accepted_amount', 'line_ids.decision', 'line_ids.reviewed_revision',
        'finance_assignment_valid', 'finance_reviewer_id.active', 'finance_reviewer_id.group_ids',
        'finance_reviewer_id.company_ids', 'policy_reference', 'company_id.ps_te_expense_policy_reference',
        'company_id.currency_id', 'currency_id.active', 'currency_id.rounding', 'trip_id.state',
        'zero_expense_declared', 'zero_expense_declared_by_id', 'zero_expense_reason',
        'zero_expense_declared_at', 'zero_expense_cancellation_revision',
        'zero_expense_reviewed_by_id', 'zero_expense_reviewed_at', 'zero_expense_review_reason',
        'trip_id.cancellation_status', 'trip_id.cancellation_revision',
    )
    def _compute_totals(self):
        for report in self:
            accepted = refused = unresolved = 0
            for line in report.line_ids:
                if line.reviewed_revision == report.revision and line.decision in ('accepted', 'refused'):
                    accepted += line.accepted_amount
                    refused += line.claimed_amount - line.accepted_amount
                else:
                    unresolved += line.claimed_amount
            report.claimed_total = sum(report.line_ids.mapped('claimed_amount'))
            report.accepted_total = accepted
            report.refused_total = refused
            report.unresolved_total = unresolved
            company = report.company_id.sudo()
            finance = report.finance_reviewer_id.sudo()
            current_binding = bool(
                report.finance_assignment_valid and finance.active
                and company in finance.company_ids
                and finance.has_group('ps_expenses.group_ps_te_finance')
                and finance.has_group('hr_expense.group_hr_expense_team_approver')
                and (company.ps_te_expense_policy_reference or '').strip() == report.policy_reference
                and company.currency_id == report.currency_id and report.currency_id.active
                and report.currency_id.rounding == 1 and report._business_basis_valid()
            )
            zero_ready = bool(
                report.zero_expense_declared and not report.line_ids
                and report.zero_expense_declared_by_id == report.owner_id and report.zero_expense_declared_at
                and report.zero_expense_reason and report.zero_expense_review_reason
                and report.zero_expense_reviewed_by_id == report.finance_reviewer_id and report.zero_expense_reviewed_at
                and report.trip_id.cancellation_status == 'approved'
                and report.zero_expense_cancellation_revision == report.trip_id.cancellation_revision
            )
            itemized_ready = bool(
                report.line_ids and not report.zero_expense_declared
                and all(line.reviewed_revision == report.revision and line.decision in ('accepted', 'refused') for line in report.line_ids)
            )
            report.accepted_basis_ready = bool(
                report.native_source_ready and current_binding and report.state == 'reviewed' and report.reviewed_revision == report.revision
                and (zero_ready or itemized_ready)
            )

    def _business_basis_valid(self):
        self.ensure_one()
        return (self.trip_id.state == 'approved' or
                (self.trip_id.cancellation_status == 'approved' and not self.line_ids))

    @api.model
    def _configuration(self, trip):
        company = trip.company_id.sudo()
        helper = self.env['ps.te.trip.advance']
        policy = helper._text(company.ps_te_expense_policy_reference, _('Expense policy reference'))
        finance = company.ps_te_finance_reviewer_id
        if not company.currency_id.active or company.currency_id.name != 'VND' or company.currency_id.rounding != 1:
            raise ValidationError(_('This release supports active whole-unit VND only.'))
        if (not finance or not finance.active or finance == trip.owner_id or company not in finance.company_ids
                or not finance.has_group('ps_expenses.group_ps_te_finance')
                or not finance.has_group('hr_expense.group_hr_expense_team_approver')):
            raise ValidationError(_('Configure an active finance reviewer other than the requester.'))
        return {'finance_reviewer_id': finance.id, 'policy_reference': policy, 'currency_id': company.currency_id.id}

    @api.model_create_multi
    def create(self, vals_list):
        self.browse().check_access('create')
        trips = []
        for vals in vals_list:
            if set(vals) != {'trip_id'}:
                raise AccessError(_('Expense report workflow values are server controlled.'))
            trip = self.env['ps.te.trip.request'].browse(vals['trip_id']).exists()
            if len(trip) != 1:
                raise ValidationError(_('Select one approved trip.'))
            trip.check_access('read')
            trip._assert_current_membership()
            trips.append(trip)
        self.env['ps.te.trip.request'].browse(sorted({trip.id for trip in trips})).lock_for_update()
        result = []
        for trip in trips:
            trip.invalidate_recordset()
            trip._assert_current_membership()
            trip._assert_no_active_correction()
            if ((trip.state != 'approved' and trip.cancellation_status != 'approved')
                    or trip.expense_report_id or trip.case_status != 'open'):
                raise ValidationError(_('Use one expense report for an approved trip.'))
            result.append({'reference': 'EXP-' + uuid.uuid4().hex.upper(), 'trip_id': trip.id,
                           'owner_id': trip.owner_id.id, 'company_id': trip.company_id.id,
                           'state': 'draft', 'revision': 1, **self._configuration(trip)})
        safe = self.with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
        records = super(PsTeExpenseReport, safe).create(result)
        for report in records:
            report.trip_id._bind_expense_report(report)
            report._event('created', _('Expense draft created'))
        return records

    def write(self, vals):
        raise AccessError(_('Use expense workflow actions instead of direct field changes.'))

    @api.model
    def _create_adjustment_report(self, adjustment):
        adjustment.ensure_one()
        adjustment._actor('owner')
        adjustment._check_sources()
        if adjustment.report_id or adjustment.state != 'draft':
            raise ValidationError(_('Use the existing adjustment expense version.'))
        trip = adjustment.trip_id
        safe = self.with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
        report = super(PsTeExpenseReport, safe).create({
            'reference': 'AEX-' + uuid.uuid4().hex.upper(), 'trip_id': trip.id, 'adjustment_id': adjustment.id,
            'owner_id': trip.owner_id.id, 'company_id': trip.company_id.id, 'state': 'draft', 'revision': 1,
            **self._configuration(trip)})
        report._event('created', _('Expense draft created'))
        return report

    def unlink(self):
        raise AccessError(_('Expense reports must be retained.'))

    def copy(self, default=None):
        raise AccessError(_('Expense reports cannot be copied.'))

    def _assert_viewer(self):
        self.ensure_one()
        # Explicit checks remain meaningful for native binary helpers that sudo
        # the record while preserving the actual requesting user.
        user = self.env.user
        record = self.sudo()
        trip = record.trip_id
        valid_user = (
            user.active and user._is_internal()
            and record.company_id in user.company_ids and record.company_id in self.env.companies
            and trip.employee_id.active and trip.employee_mapping_valid
        )
        owner = user == record.owner_id and user.has_group('ps_expenses.group_ps_te_trip_employee')
        finance = (user == record.finance_reviewer_id and record.finance_assignment_valid
                   and user.has_group('ps_expenses.group_ps_te_finance'))
        if not valid_user or not (owner or finance):
            raise AccessError(_('Expense access is not permitted.'))

    def _assert_actor(self, role):
        self._assert_viewer()
        if role == 'owner':
            self.trip_id._assert_current_membership()
        elif (role != 'finance' or self.env.user != self.finance_reviewer_id or self.env.user == self.owner_id
              or not self.finance_assignment_valid or not self.env.user.has_group('ps_expenses.group_ps_te_finance')):
            raise AccessError(_('Only the currently assigned finance reviewer may decide expenses.'))

    def _lock(self):
        self.ensure_one()
        self.check_access('write')
        if not self.native_source_ready:
            raise ValidationError(_('Cơ sở cũ chưa liên kết Expenses chuẩn. Không tự coi là0 hoặc chuyển dữ liệu; cần kế hoạch chuyển đổi riêng.'))
        if self.adjustment_id:
            self.adjustment_id._lock()
            self.adjustment_id._check_sources()
            if self.adjustment_id.state != 'draft' or self.adjustment_id.report_id != self:
                raise ValidationError(_('This adjustment expense version is no longer editable or reviewable.'))
            self.lock_for_update()
            self.invalidate_recordset()
            if self.basis_locked:
                raise ValidationError(_('This expense basis is locked by settlement.'))
            return
        self.trip_id.lock_for_update()
        self.lock_for_update()
        self.trip_id.invalidate_recordset()
        self.invalidate_recordset()
        self.trip_id._assert_no_active_correction()
        if self.basis_locked:
            raise ValidationError(_('This expense basis is locked by settlement.'))

    def _revision(self, revision):
        if type(revision) is not int or revision != self.revision:
            raise ValidationError(_('Stale expense revision. Reload the report.'))

    def _draft(self):
        if self.state != 'draft':
            raise ValidationError(_('Revise the report before changing submitted expenses or proofs.'))

    def _policy(self):
        config = self._configuration(self.trip_id)
        if (config['policy_reference'] != self.policy_reference or config['finance_reviewer_id'] != self.finance_reviewer_id.id
                or config['currency_id'] != self.currency_id.id or not self._business_basis_valid()):
            raise ValidationError(_('The policy, assignment or trip changed. Revise and resubmit.'))

    def _event(self, event_type, reason, line=None, decision_revision=None):
        lines = line or self.line_ids
        snapshot = [{
            'line_id': item.id, 'description': item.description, 'date': str(item.expense_date),
            'claimed': item.claimed_amount, 'decision': item.decision, 'accepted': item.accepted_amount,
            'reviewed_revision': item.reviewed_revision,
            'proofs': [{'id': proof.id, 'sha256': proof.sha256, 'filename': proof.filename}
                       for proof in item._active_proofs()],
            'proof_links': [{'id': link.id, 'source_evidence_id': link.evidence_id.id}
                            for link in item.proof_link_ids if not link.superseded],
        } for item in lines]
        return self.env['ps.te.expense.event'].sudo()._append({
            'report_id': self.id, 'line_id': line.id if line else False,
            'actor_id': self.env.uid, 'occurred_at': fields.Datetime.now(),
            'revision': self.revision if decision_revision is None else decision_revision,
            'event_type': event_type, 'reason': reason, 'policy_reference': self.policy_reference,
            'snapshot': json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
            'zero_expense_snapshot': json.dumps({
                'declared': self.zero_expense_declared, 'reason': self.zero_expense_reason,
                'declared_by': self.zero_expense_declared_by_id.id, 'declared_at': str(self.zero_expense_declared_at),
                'cancellation_revision': self.zero_expense_cancellation_revision,
                'review_reason': self.zero_expense_review_reason, 'reviewed_by': self.zero_expense_reviewed_by_id.id,
                'reviewed_at': str(self.zero_expense_reviewed_at),
            }, ensure_ascii=False, sort_keys=True),
        })

    def _advance_revision(self):
        return super().write({'revision': self.revision + 1})

    def _set_settlement_lock(self, settlement, locked):
        self.ensure_one()
        if settlement.report_id != self or (self.settlement_lock_id and self.settlement_lock_id != settlement):
            raise ValidationError(_('The settlement does not own this expense basis lock.'))
        return super().write({'basis_locked': locked, 'settlement_lock_id': settlement.id if locked else False})

    def action_upload_evidence(self, line_id, filename, payload, expected_revision):
        self.ensure_one()
        self.check_access('write')
        self._assert_actor('owner')
        line = self._line(line_id)
        return self.env['ps.te.expense.evidence']._upload(line, filename, payload, expected_revision)

    def action_add_line(self, description, amount, expense_date, expected_revision):
        self._lock()
        self._assert_actor('owner')
        self._revision(expected_revision)
        self._draft()
        if self.zero_expense_declared or self.trip_id.state != 'approved':
            raise ValidationError(_('Use the normal approved-trip expense route; withdraw any zero declaration before adding costs.'))
        if len(self.line_ids) >= 100:
            raise ValidationError(_('At most 100 expense lines are supported per report.'))
        vals = self.env['ps.te.expense.line']._validated_values(description, amount, expense_date)
        line = self.env['ps.te.expense.line'].sudo()._append({'report_id': self.id, **vals})
        super().write({'revision': self.revision + 1})
        self._event('line_added', _('Employee expense line added'), line)
        return line.id

    def action_edit_line(self, line_id, description, amount, expense_date, expected_revision):
        self._lock()
        self._assert_actor('owner')
        self._revision(expected_revision)
        self._draft()
        line = self._line(line_id)
        line._update(self.env['ps.te.expense.line']._validated_values(description, amount, expense_date))
        super().write({'revision': self.revision + 1})
        self._event('line_edited', _('Employee expense line revised'), line)
        return True

    def _line(self, line_id):
        if type(line_id) is not int or line_id < 1:
            raise ValidationError(_('Select one expense line.'))
        line = self.env['ps.te.expense.line'].browse(line_id)
        line.check_access('read')
        if line.report_id != self:
            raise AccessError(_('The expense line does not belong to this report.'))
        return line

    def action_submit(self, expected_revision):
        self._lock()
        self._assert_actor('owner')
        self._revision(expected_revision)
        if self.state in ('submitted', 'reviewed') and self.submission_receipt:
            return True
        self._draft()
        if ((not self.line_ids and not self._zero_declaration_current()) or self.trip_id.advance_choice == 'undecided'):
            raise ValidationError(_('Add expense lines and explicitly declare advance intent before submitting.'))
        config = self._configuration(self.trip_id)
        super().write({**config, 'state': 'submitted', 'submitted_at': fields.Datetime.now(),
                       'submission_receipt': 'EXP-RCPT-' + uuid.uuid4().hex.upper()})
        self.line_ids.native_expense_id._ps_submit()
        self._event('submitted', _('Expense revision submitted for finance review'))
        return True

    def _zero_declaration_current(self):
        self.ensure_one()
        return bool(self.zero_expense_declared and not self.line_ids
                    and self.zero_expense_declared_by_id == self.owner_id and self.zero_expense_reason
                    and self.zero_expense_declared_at and self.trip_id.cancellation_status == 'approved'
                    and self.zero_expense_cancellation_revision == self.trip_id.cancellation_revision)

    def action_declare_zero_expenses(self, reason, expected_revision):
        self._lock()
        self._assert_actor('owner')
        self._revision(expected_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Zero-expense declaration reason'))
        self._draft()
        if self.line_ids or self.trip_id.cancellation_status != 'approved':
            raise ValidationError(_('Only a manager-cancelled trip with no expense lines may declare no expenses.'))
        if self.zero_expense_declared:
            if self.zero_expense_reason == reason and self._zero_declaration_current():
                return True
            raise ValidationError(_('Withdraw the current zero declaration before replacing it.'))
        super().write({'zero_expense_declared': True, 'zero_expense_reason': reason,
                       'zero_expense_declared_by_id': self.env.uid, 'zero_expense_declared_at': fields.Datetime.now(),
                       'zero_expense_cancellation_revision': self.trip_id.cancellation_revision,
                       'revision': self.revision + 1})
        self._event('zero_declared', reason)
        return True

    def action_review_zero_expenses(self, decision, reason, expected_revision):
        self._lock()
        self._assert_actor('finance')
        self._revision(expected_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Zero-expense review reason'))
        if decision not in ('accepted', 'returned'):
            raise ValidationError(_('Unsupported zero-expense decision.'))
        if not self._zero_declaration_current():
            raise ValidationError(_('A current explicit employee zero-expense declaration is required.'))
        self._policy()
        if self.state in ('reviewed', 'returned'):
            same = (self.zero_expense_review_reason == reason and self.zero_expense_reviewed_by_id.id == self.env.uid
                    and self.state == ('reviewed' if decision == 'accepted' else 'returned'))
            if same:
                return True
        if self.state != 'submitted':
            raise ValidationError(_('Review only the exact submitted zero-expense revision.'))
        now = fields.Datetime.now()
        super().write({'state': 'reviewed' if decision == 'accepted' else 'returned',
                       'zero_expense_review_reason': reason, 'zero_expense_reviewed_by_id': self.env.uid,
                       'zero_expense_reviewed_at': now, 'reviewed_at': now if decision == 'accepted' else False,
                       'reviewed_revision': self.revision if decision == 'accepted' else 0})
        self._event('zero_' + decision, reason)
        return True

    def action_review_line(self, line_id, decision, reason, accepted_amount, expected_revision):
        self._lock()
        self._assert_actor('finance')
        self._revision(expected_revision)
        line = self._line(line_id)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Review reason'))
        if decision not in ('accepted', 'refused', 'returned'):
            raise ValidationError(_('Unsupported expense decision.'))
        amount = self.env['ps.te.trip.advance']._amount(accepted_amount) if decision == 'accepted' else 0
        if amount > line.claimed_amount:
            raise ValidationError(_('Accepted amount cannot exceed the employee claim.'))
        if line.reviewed_revision == self.revision and line.decision != 'pending':
            if (line.decision, line.decision_reason, line.accepted_amount) == (decision, reason, amount):
                return True
            raise ValidationError(_('This expense line has already been decided for this revision.'))
        if self.state != 'submitted':
            raise ValidationError(_('Only the exact submitted report may be reviewed.'))
        self._policy()
        if decision == 'accepted' and not line._active_proofs():
            raise ValidationError(_('Evidence is required before accepting this expense. Return or refuse it.'))
        line._update({'decision': decision, 'accepted_amount': amount,
                      'decision_reason': reason, 'reviewed_revision': self.revision,
                      'reviewed_by_id': self.env.uid, 'reviewed_at': fields.Datetime.now()})
        self._event('line_' + decision, reason, line)
        if decision == 'returned':
            super().write({'state': 'returned'})
        elif all(item.decision in ('accepted', 'refused') and item.reviewed_revision == self.revision for item in self.line_ids):
            super().write({'state': 'reviewed', 'reviewed_at': fields.Datetime.now(), 'reviewed_revision': self.revision})
            self._event('reviewed', _('All lines decided; accepted basis identified'))
        return True

    def action_revise(self, reason, expected_revision):
        self._lock()
        self._assert_actor('owner')
        self._revision(expected_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Revision reason'))
        if self.state not in ('submitted', 'returned', 'reviewed') and not (self.state == 'draft' and self.zero_expense_declared):
            raise ValidationError(_('Only a submitted or reviewed report may be withdrawn for revision.'))
        self._event('withdrawn', reason)
        self.line_ids._update({'decision': 'pending', 'accepted_amount': 0,
                               'decision_reason': False, 'reviewed_revision': 0,
                               'reviewed_by_id': False, 'reviewed_at': False})
        super().write({'state': 'draft', 'revision': self.revision + 1,
                       'reviewed_at': False, 'reviewed_revision': 0, 'submission_receipt': False,
                       'zero_expense_declared': False, 'zero_expense_reason': False,
                       'zero_expense_declared_by_id': False, 'zero_expense_declared_at': False,
                       'zero_expense_cancellation_revision': 0, 'zero_expense_review_reason': False,
                       'zero_expense_reviewed_by_id': False, 'zero_expense_reviewed_at': False})
        return True

    def action_open_operation(self):
        self.ensure_one()
        self.check_access('read')
        self._assert_viewer()
        return {'type': 'ir.actions.act_window', 'name': _('Expense Operation'),
                'res_model': 'ps.te.expense.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_report_id': self.id, 'default_expected_revision': self.revision}}

    def _entry_action(self):
        """Không cần tạo khoản chi giả để mở kiểm soát bảng kê không chi phí."""
        self.ensure_one()
        self.check_access('read')
        self._assert_viewer()
        if self.trip_id.cancellation_status == 'approved' and not self.line_ids:
            return {'type': 'ir.actions.act_window', 'name': _('Expense Reports'),
                    'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
                    'views': [(self.env.ref('ps_expenses.view_ps_te_expense_form').id, 'form')]}
        return self.action_open_native_expenses()

    def action_open_native_expenses(self):
        self.ensure_one()
        self.check_access('read')
        self._assert_viewer()
        return {'type': 'ir.actions.act_window', 'name': _('Chi phí công tác — Expenses chuẩn'),
            'res_model': 'hr.expense', 'view_mode': 'list,form', 'domain': [('ps_report_id', '=', self.id)],
            'context': {'default_ps_report_id': self.id,
                'default_product_id': self.env.ref('ps_expenses.product_ps_native_expense').id,
                'default_manager_id': self.finance_reviewer_id.id,
                'create': self.env.uid == self.owner_id.id}}

    def action_reuse_evidence(self, line_id, evidence_id, expected_revision):
        self._lock()
        self._assert_actor('owner')
        self._revision(expected_revision)
        self._draft()
        line = self._line(line_id)
        previous = self.adjustment_id.carry_report_id
        if not previous or type(evidence_id) is not int:
            raise ValidationError(_('Select eligible proof from the previous effective expense basis.'))
        evidence = self.env['ps.te.expense.evidence'].browse(evidence_id).exists()
        evidence.check_access('read')
        eligible = previous.line_ids._active_proofs()
        if (len(evidence) != 1 or evidence not in eligible or evidence.company_id != self.company_id
                or evidence.report_id.trip_id != self.trip_id or evidence.report_id.owner_id != self.owner_id):
            raise ValidationError(_('Select eligible proof from the previous effective expense basis.'))
        if len(line._active_proofs()) >= 5:
            raise ValidationError(_('At most five active proofs are supported per expense line.'))
        link = self.env['ps.te.expense.proof.link']._append(line, evidence)
        self._advance_revision()
        self._event('evidence_reused', _('Existing private proof linked without copying or reparenting'), line)
        return link.id


class PsTeExpenseLine(models.Model):
    _name = 'ps.te.expense.line'
    _description = 'PS T&E Employee Expense'
    _rec_name = 'description'

    report_id = fields.Many2one('ps.te.expense.report', required=True, readonly=True, ondelete='restrict', index=True)
    currency_id = fields.Many2one(related='report_id.currency_id', readonly=True)
    native_expense_id = fields.Many2one('hr.expense', readonly=True, copy=False, ondelete='restrict', index=True, string='Expenses chuẩn')
    _native_unique = models.Constraint('UNIQUE(native_expense_id)', 'Only one PS projection is allowed per native expense.')
    description = fields.Char(related='native_expense_id.name', readonly=True, string='Description')
    expense_date = fields.Date(related='native_expense_id.date', readonly=True, string='Expense Date')
    claimed_amount = fields.Monetary(related='native_expense_id.total_amount_currency', readonly=True, string='Claimed Amount')
    decision = fields.Selection(related='native_expense_id.ps_decision', readonly=True)
    accepted_amount = fields.Monetary(related='native_expense_id.ps_accepted_amount', readonly=True)
    decision_reason = fields.Text(related='native_expense_id.ps_decision_reason', readonly=True)
    reviewed_revision = fields.Integer(related='native_expense_id.ps_reviewed_revision', readonly=True)
    reviewed_by_id = fields.Many2one(related='native_expense_id.ps_reviewed_by_id', readonly=True)
    reviewed_at = fields.Datetime(related='native_expense_id.ps_reviewed_at', readonly=True)
    evidence_ids = fields.One2many('ps.te.expense.evidence', 'line_id', readonly=True)
    proof_link_ids = fields.One2many('ps.te.expense.proof.link', 'line_id', readonly=True)

    def _active_proofs(self):
        own = self.mapped('evidence_ids').filtered(lambda evidence: not evidence.superseded)
        linked = self.mapped('proof_link_ids').filtered(lambda link: not link.superseded).mapped('evidence_id')
        return own | linked.filtered(lambda evidence: not evidence.superseded)

    @api.model
    def _validated_values(self, description, amount, expense_date):
        helper = self.env['ps.te.trip.advance']
        try:
            expense_date = fields.Date.to_date(expense_date)
        except (ValueError, TypeError):
            raise ValidationError(_('A valid expense date is required.'))
        if not expense_date or expense_date > fields.Date.context_today(self):
            raise ValidationError(_('Expense date cannot be missing or in the future.'))
        return {'description': helper._text(description, _('Expense description')),
                'claimed_amount': helper._amount(amount), 'expense_date': expense_date}

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Create expense lines through their report.'))

    @api.model
    def _append(self, vals):
        report = self.env['ps.te.expense.report'].browse(vals['report_id'])
        native = self.env['hr.expense']._ps_create_claim(report, vals)
        line = super().create({'report_id': report.id, 'native_expense_id': native.id})
        native._ps_bind_line(line)
        return line

    def _update(self, vals):
        for line in self:
            if not line.native_expense_id:
                raise ValidationError(_('Khoản chi cũ chưa có nguồn Expenses chuẩn; không tự chuyển dữ liệu.'))
            line.native_expense_id._ps_update(vals)
        return True

    def write(self, vals):
        raise AccessError(_('Use report actions to edit or review expense lines.'))

    def unlink(self):
        raise AccessError(_('Expense lines must be retained.'))


class PsTeExpenseEvent(models.Model):
    _name = 'ps.te.expense.event'
    _description = 'PS T&E Expense History'
    _order = 'id desc'

    report_id = fields.Many2one('ps.te.expense.report', required=True, readonly=True, ondelete='restrict', index=True)
    line_id = fields.Many2one('ps.te.expense.line', readonly=True, ondelete='restrict')
    actor_id = fields.Many2one('res.users', required=True, readonly=True)
    occurred_at = fields.Datetime(required=True, readonly=True)
    revision = fields.Integer(required=True, readonly=True)
    event_type = fields.Char(required=True, readonly=True)
    reason = fields.Text(readonly=True)
    policy_reference = fields.Char(readonly=True)
    snapshot = fields.Text(required=True, readonly=True)
    zero_expense_snapshot = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Expense history is generated only by workflow actions.'))

    @api.model
    def _append(self, vals):
        safe = self.with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
        return super(PsTeExpenseEvent, safe).create(vals)

    def write(self, vals):
        raise AccessError(_('Expense history cannot be changed.'))

    def unlink(self):
        raise AccessError(_('Expense history cannot be deleted.'))
