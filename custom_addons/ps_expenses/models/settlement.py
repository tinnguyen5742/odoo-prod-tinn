import json
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class PsTeSettlement(models.Model):
    _name = 'ps.te.settlement'
    _description = 'PS T&E Settlement'
    _rec_name = 'reference'
    _order = 'id desc'
    _trip_unique = models.Constraint('UNIQUE(trip_id)', 'A trip may have only one settlement record.')

    reference = fields.Char(required=True, readonly=True)
    trip_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True, ondelete='restrict', index=True)
    report_id = fields.Many2one('ps.te.expense.report', required=True, readonly=True, ondelete='restrict')
    report_revision = fields.Integer(required=True, readonly=True)
    expense_policy_reference = fields.Char(required=True, readonly=True)
    expense_basis_kind = fields.Selection([
        ('itemized', 'Itemized Expense Review'), ('zero_declaration', 'Explicit Zero-Expense Review'),
    ], required=True, default='itemized', readonly=True)
    accepted_amount = fields.Monetary(required=True, readonly=True)
    owner_id = fields.Many2one('res.users', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', required=True, readonly=True)
    finance_reviewer_id = fields.Many2one('res.users', required=True, readonly=True, index=True)
    cash_operator_id = fields.Many2one('res.users', required=True, readonly=True, index=True)
    finance_assignment_valid = fields.Boolean(compute='_compute_assignments', store=True)
    cash_assignment_valid = fields.Boolean(compute='_compute_assignments', store=True)
    policy_reference = fields.Char(required=True, readonly=True)
    revision = fields.Integer(required=True, default=1, readonly=True)
    state = fields.Selection([
        ('draft', 'Prepared Draft'), ('submitted', 'Finance Review'),
        ('approved', 'Approved — Resolve Recorded Obligations'),
        ('closed', 'Workflow Closed — Accounting Separate'),
    ], required=True, default='draft', readonly=True)
    submitted_receipt = fields.Char(readonly=True)
    funding_known = fields.Boolean(default=False, readonly=True)
    funding_kind = fields.Selection([('unknown', 'Unconfirmed Funding'), ('advance', 'Recorded Advance'), ('none', 'Confirmed No Advance Payment')], default='unknown', readonly=True)
    advance_id = fields.Many2one('ps.te.trip.advance', readonly=True, ondelete='restrict')
    advance_revision = fields.Integer(readonly=True)
    funding_amount = fields.Monetary(readonly=True)
    funding_reference = fields.Char(readonly=True)
    funding_confirmed_by_id = fields.Many2one('res.users', readonly=True)
    funding_confirmed_at = fields.Datetime(readonly=True)
    difference_known = fields.Boolean(compute='_compute_difference')
    difference_amount = fields.Monetary(compute='_compute_difference')
    direction = fields.Selection([
        ('unknown', 'Unconfirmed'), ('balanced', 'Equal — No Additional Cash'),
        ('topup', 'Company Owes Employee'), ('return', 'Employee Owes Company'),
    ], compute='_compute_difference')
    remaining_amount = fields.Monetary(compute='_compute_difference')
    approved_by_id = fields.Many2one('res.users', readonly=True)
    approved_at = fields.Datetime(readonly=True)
    approval_reason = fields.Text(readonly=True)
    cash_outcome = fields.Selection([
        ('not_started', 'No Settlement Cash Recorded'), ('uncertain', 'External Cash Outcome Unconfirmed'),
        ('recorded', 'External Cash Recorded'),
    ], required=True, default='not_started', readonly=True)
    cash_attempt_reference = fields.Char(readonly=True)
    cash_event_id = fields.Many2one('ps.te.cash.event', readonly=True, ondelete='restrict')
    no_execution_reference = fields.Char(readonly=True)
    closed_by_id = fields.Many2one('res.users', readonly=True)
    closed_at = fields.Datetime(readonly=True)
    accounting_status = fields.Selection([('not_verified', 'External Accounting Not Verified')], default='not_verified', required=True, readonly=True)
    event_ids = fields.One2many('ps.te.settlement.event', 'settlement_id', readonly=True)
    correction_hold = fields.Boolean(related='trip_id.correction_hold', readonly=True)

    @api.depends('finance_reviewer_id', 'cash_operator_id', 'company_id.ps_te_finance_reviewer_id', 'company_id.ps_te_cash_operator_id')
    def _compute_assignments(self):
        for record in self:
            record.finance_assignment_valid = record.finance_reviewer_id == record.company_id.ps_te_finance_reviewer_id
            record.cash_assignment_valid = record.cash_operator_id == record.company_id.ps_te_cash_operator_id

    @api.depends('funding_known', 'funding_amount', 'accepted_amount', 'cash_event_id.amount')
    def _compute_difference(self):
        for record in self:
            difference = record.accepted_amount - record.funding_amount if record.funding_known else 0
            record.difference_known = record.funding_known
            record.difference_amount = difference
            record.direction = ('unknown' if not record.funding_known else 'balanced' if difference == 0 else 'topup' if difference > 0 else 'return')
            record.remaining_amount = max(abs(difference) - (record.cash_event_id.amount or 0), 0) if record.funding_known else 0

    @api.model
    def _configuration(self, trip):
        company = trip.company_id.sudo()
        helper = self.env['ps.te.trip.advance']
        policy = helper._text(company.ps_te_settlement_policy_reference, _('Settlement policy reference'))
        finance, cash = company.ps_te_finance_reviewer_id, company.ps_te_cash_operator_id
        if not finance or not cash or finance == cash or trip.owner_id in (finance, cash):
            raise ValidationError(_('Configure distinct finance/cash officers other than the requester.'))
        if not company.currency_id.active or company.currency_id.name != 'VND' or company.currency_id.rounding != 1:
            raise ValidationError(_('Settlement supports active whole-unit VND only.'))
        for user, group in ((finance, 'finance'), (cash, 'cash')):
            if not user.active or company not in user.company_ids or not user.has_group('ps_expenses.group_ps_te_' + group):
                raise ValidationError(_('Settlement officers must have current company membership and the matching role.'))
        return {'finance_reviewer_id': finance.id, 'cash_operator_id': cash.id,
                'policy_reference': policy, 'currency_id': company.currency_id.id}

    @api.model
    def _snapshot(self, trip):
        report = trip.sudo().expense_report_id
        if not report or not report.accepted_basis_ready or not report._business_basis_valid():
            raise ValidationError(_('A fully reviewed, current expense basis is required.'))
        advance = trip.sudo().advance_id
        values = {
            'report_id': report.id, 'report_revision': report.revision,
            'accepted_amount': report.accepted_total, 'expense_policy_reference': report.policy_reference,
            'expense_basis_kind': 'zero_declaration' if report.zero_expense_declared else 'itemized',
            'advance_id': advance.id or False, 'advance_revision': advance.revision or 0,
            'funding_known': False, 'funding_kind': 'unknown', 'funding_amount': 0,
            'funding_reference': False, 'funding_confirmed_by_id': False, 'funding_confirmed_at': False,
        }
        if advance and advance.has_disbursement and advance.state == 'disbursed':
            advance._ensure_cash_event()
            values.update(funding_known=True, funding_kind='advance', funding_amount=advance.disbursed_amount,
                          funding_reference=advance.cash_reference, funding_confirmed_by_id=advance.disbursed_by_id.id,
                          funding_confirmed_at=advance.disbursed_at)
        return values

    @api.model_create_multi
    def create(self, vals_list):
        self.browse().check_access('create')
        trips = []
        for values in vals_list:
            if set(values) != {'trip_id'}:
                raise AccessError(_('Settlement bases and workflow fields are server controlled.'))
            trip = self.env['ps.te.trip.request'].browse(values['trip_id']).exists()
            if len(trip) != 1:
                raise ValidationError(_('Select one approved trip.'))
            trip.check_access('read')
            trip._assert_current_membership()
            trips.append(trip)
        self.env['ps.te.trip.request'].browse(sorted({trip.id for trip in trips})).lock_for_update()
        prepared = []
        for trip in trips:
            trip.invalidate_recordset()
            trip._assert_current_membership()
            trip._assert_no_active_correction()
            if trip.settlement_id or trip.case_status != 'open':
                raise ValidationError(_('Use the existing open-case settlement.'))
            if trip.advance_id:
                trip.advance_id.lock_for_update()
            if trip.expense_report_id:
                trip.expense_report_id.lock_for_update()
            prepared.append({'reference': 'SET-' + uuid.uuid4().hex.upper(),
                             'trip_id': trip.id, 'owner_id': trip.owner_id.id, 'company_id': trip.company_id.id,
                             'state': 'draft', 'revision': 1, **self._configuration(trip), **self._snapshot(trip)})
        safe = self.with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
        records = super(PsTeSettlement, safe).create(prepared)
        for record in records:
            record.trip_id._bind_settlement(record)
            record._event('prepared', _('Settlement bases prepared; unknown funding remains explicit'))
        return records

    def write(self, vals):
        raise AccessError(_('Use settlement workflow actions instead of direct field changes.'))

    def unlink(self):
        raise AccessError(_('Settlement records must be retained.'))

    def copy(self, default=None):
        raise AccessError(_('Settlement records cannot be copied.'))

    def _lock(self):
        self.ensure_one()
        self.check_access('write')
        trip = self.sudo().trip_id
        trip.lock_for_update()
        trip.invalidate_recordset()
        if trip.advance_id:
            trip.advance_id.lock_for_update()
        if trip.expense_report_id:
            trip.expense_report_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()
        self.sudo().report_id.invalidate_recordset()
        if trip.advance_id:
            trip.advance_id.invalidate_recordset()

    def _actor(self, role):
        user = self.env.user
        record = self.sudo()
        if (not user.active or record.company_id not in user.company_ids or record.company_id not in self.env.companies
                or not record.trip_id.employee_id.active or not record.trip_id.employee_mapping_valid):
            raise AccessError(_('Settlement access is not permitted.'))
        if role == 'owner':
            if user != record.owner_id or not user.has_group('ps_expenses.group_ps_te_trip_employee'):
                raise AccessError(_('Only the current requester may prepare or submit this settlement.'))
            return
        actor = record.finance_reviewer_id if role == 'finance' else record.cash_operator_id
        valid = record.finance_assignment_valid if role == 'finance' else record.cash_assignment_valid
        if (role not in ('finance', 'cash') or user != actor or not valid or user == record.owner_id
                or not user.has_group('ps_expenses.group_ps_te_' + role)):
            raise AccessError(_('Only the currently assigned settlement officer may perform this action.'))

    def _revision(self, revision):
        if type(revision) is not int or revision != self.revision:
            raise ValidationError(_('Stale settlement revision. Reload before acting.'))

    def _policy(self):
        current = self._configuration(self.sudo().trip_id)
        if any(current[key] != value for key, value in (
            ('policy_reference', self.policy_reference), ('currency_id', self.currency_id.id),
            ('finance_reviewer_id', self.finance_reviewer_id.id), ('cash_operator_id', self.cash_operator_id.id),
        )):
            raise ValidationError(_('Settlement policy or officers changed; revalidation is required.'))

    def _verify_sources(self, require_funding=True):
        self._policy()
        record = self.sudo()
        trip, report = record.trip_id, record.report_id
        if trip.latest_completed_adjustment_id:
            raise ValidationError(_('Historical settlement — consult the latest completed adjustment for the current financial outcome.'))
        if (not report._business_basis_valid() or trip.expense_report_id != report or not report.accepted_basis_ready
                or report.revision != self.report_revision or report.accepted_total != self.accepted_amount
                or report.policy_reference != self.expense_policy_reference
                or self.expense_basis_kind != ('zero_declaration' if report.zero_expense_declared else 'itemized')):
            raise ValidationError(_('The expense basis changed or is unresolved. Refresh and review the settlement.'))
        advance = trip.advance_id
        if advance != record.advance_id or (advance and advance.revision != self.advance_revision):
            raise ValidationError(_('The advance basis changed. Refresh the settlement.'))
        if not require_funding:
            return
        if not self.funding_known:
            raise ValidationError(_('Funding is unconfirmed; missing or pending cash cannot be treated as zero.'))
        if self.funding_kind == 'advance':
            if (not advance or not advance.has_disbursement or advance.state != 'disbursed'
                    or advance.disbursed_amount != self.funding_amount or advance.cash_reference != self.funding_reference):
                raise ValidationError(_('The recorded advance funding no longer matches the settlement.'))
        elif self.funding_kind == 'none':
            if (trip.advance_choice != 'not_requested' or not self.funding_confirmed_by_id or not self.funding_reference
                    or (advance and (advance.state != 'cancelled' or advance.has_disbursement or advance.payment_outcome == 'uncertain'))):
                raise ValidationError(_('No-payment funding requires explicit current confirmation and no executable advance.'))
        else:
            raise ValidationError(_('Funding is not identified.'))

    def _event(self, event_type, reason):
        return self.env['ps.te.settlement.event'].sudo()._append({
            'settlement_id': self.id, 'actor_id': self.env.uid, 'occurred_at': fields.Datetime.now(),
            'revision': self.revision, 'event_type': event_type, 'reason': reason,
            'snapshot': json.dumps({
                'report_id': self.report_id.id, 'report_revision': self.report_revision,
                'accepted_amount': self.accepted_amount, 'funding_known': self.funding_known,
                'expense_basis_kind': self.expense_basis_kind,
                'funding_kind': self.funding_kind, 'funding_amount': self.funding_amount,
                'funding_reference': self.funding_reference, 'direction': self.direction,
                'difference': self.difference_amount if self.difference_known else None,
                'policy_reference': self.policy_reference, 'expense_policy_reference': self.expense_policy_reference,
                'cash_outcome': self.cash_outcome, 'cash_attempt': self.cash_attempt_reference,
                'cash_event_id': self.cash_event_id.id, 'state': self.state,
            }, sort_keys=True),
        })

    def action_refresh(self, reason, expected_revision):
        self._lock()
        self._actor('owner')
        self.sudo().trip_id._assert_no_active_correction()
        self._revision(expected_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Refresh reason'))
        if self.state not in ('draft', 'submitted') or self.cash_outcome != 'not_started' or self.cash_event_id:
            raise ValidationError(_('Only an unapproved, unexecuted preparation may be refreshed.'))
        self._event('preparation_replaced', reason)
        super().write({**self._configuration(self.sudo().trip_id), **self._snapshot(self.sudo().trip_id),
                       'state': 'draft', 'revision': self.revision + 1, 'submitted_receipt': False})
        self._event('refreshed', reason)
        return True

    def action_confirm_no_funding(self, reference, reason, expected_revision):
        self._lock()
        self._actor('cash')
        self._revision(expected_revision)
        self._verify_sources(require_funding=False)
        reference = self.env['ps.te.trip.advance']._text(reference, _('No-funding reconciliation reference'))
        reason = self.env['ps.te.trip.advance']._text(reason, _('No-funding confirmation reason'))
        trip = self.sudo().trip_id
        advance = trip.advance_id
        if self.state not in ('draft', 'submitted'):
            raise ValidationError(_('Confirm funding before finance approval.'))
        if (trip.advance_choice != 'not_requested'
                or (advance and (advance.state != 'cancelled' or advance.has_disbursement or advance.payment_outcome == 'uncertain'))):
            raise ValidationError(_('Resolve or cancel the advance and explicitly declare no advance first.'))
        if self.funding_kind == 'none' and self.funding_known and self.funding_reference == reference:
            return True
        super().write({'funding_known': True, 'funding_kind': 'none', 'funding_amount': 0,
                       'funding_reference': reference, 'funding_confirmed_by_id': self.env.uid,
                       'funding_confirmed_at': fields.Datetime.now(), 'revision': self.revision + 1})
        self._event('no_funding_confirmed', reason)
        return True

    def action_submit(self, expected_revision):
        self._lock()
        self._actor('owner')
        self.sudo().trip_id._assert_no_active_correction()
        self._revision(expected_revision)
        if self.state in ('submitted', 'approved', 'closed') and self.submitted_receipt:
            return True
        self._verify_sources(require_funding=False)
        if self.state != 'draft':
            raise ValidationError(_('Only a prepared draft may be submitted.'))
        super().write({'state': 'submitted', 'submitted_receipt': 'SET-RCPT-' + uuid.uuid4().hex.upper()})
        self._event('submitted', _('Settlement preparation submitted'))
        return True

    def action_approve(self, reason, expected_revision):
        self._lock()
        self._actor('finance')
        self.sudo().trip_id._assert_no_pending_cancellation()
        self._revision(expected_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Approval reason'))
        if self.state == 'approved' and self.approval_reason == reason:
            return True
        if self.state != 'submitted':
            raise ValidationError(_('Only the submitted settlement revision may be approved.'))
        self._verify_sources()
        self.sudo().report_id._set_settlement_lock(self, True)
        self.sudo().trip_id._set_funding_lock(self)
        super().write({'state': 'approved', 'approved_by_id': self.env.uid,
                       'approved_at': fields.Datetime.now(), 'approval_reason': reason})
        self._event('approved', reason)
        return True

    def action_return(self, reason, expected_revision):
        self._lock()
        self._actor('finance')
        self.sudo().trip_id._assert_no_active_correction()
        self._revision(expected_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Return reason'))
        if self.state not in ('submitted', 'approved') or self.cash_outcome != 'not_started' or self.cash_event_id:
            raise ValidationError(_('Executed, uncertain or closed settlements cannot be reset.'))
        self._event('returned', reason)
        self.sudo().report_id._set_settlement_lock(self, False)
        self.sudo().trip_id._set_funding_lock(False)
        super().write({'state': 'draft', 'revision': self.revision + 1,
                       'approved_by_id': False, 'approved_at': False, 'approval_reason': False,
                       'submitted_receipt': False})
        return True

    def action_start_cash(self, attempt_reference, reason, expected_revision):
        self._lock()
        self._actor('cash')
        self.sudo().trip_id._assert_no_pending_cancellation()
        self._revision(expected_revision)
        self._verify_sources()
        attempt_reference = self.env['ps.te.trip.advance']._text(attempt_reference, _('Cash attempt reference'))
        reason = self.env['ps.te.trip.advance']._text(reason, _('Cash preparation reason'))
        if self.state != 'approved' or self.direction == 'balanced' or self.cash_event_id:
            raise ValidationError(_('Prepare only an approved outstanding top-up or return.'))
        if self.cash_outcome == 'uncertain':
            if self.cash_attempt_reference == attempt_reference:
                return True
            raise ValidationError(_('Reconcile the uncertain cash operation before another attempt.'))
        super().write({'cash_outcome': 'uncertain', 'cash_attempt_reference': attempt_reference})
        self._event('cash_started', reason)
        return True

    def action_confirm_cash_not_executed(self, reference, reason, expected_revision):
        self._lock()
        self._actor('cash')
        self._revision(expected_revision)
        reference = self.env['ps.te.trip.advance']._text(reference, _('Reconciliation reference'))
        reason = self.env['ps.te.trip.advance']._text(reason, _('Reconciliation reason'))
        if self.state != 'approved' or self.cash_outcome != 'uncertain' or self.cash_event_id:
            raise ValidationError(_('Only an unresolved cash attempt can be confirmed not executed.'))
        super().write({'cash_outcome': 'not_started', 'no_execution_reference': reference})
        self._event('cash_not_executed', reason)
        return True

    def action_record_cash(self, amount, reference, execution_date, expected_revision):
        self._lock()
        self._actor('cash')
        self._revision(expected_revision)
        amount = self.env['ps.te.cash.event']._amount(amount)
        reference = self.env['ps.te.trip.advance']._text(reference, _('External cash reference'))
        try:
            date = fields.Date.to_date(execution_date)
        except (ValueError, TypeError):
            raise ValidationError(_('A valid cash execution date is required.'))
        if not date:
            raise ValidationError(_('A valid cash execution date is required.'))
        if self.cash_event_id:
            event = self.cash_event_id.sudo()
            if (event.amount, event.external_reference, event.execution_date) == (amount, reference, date):
                return True
            raise ValidationError(_('A different settlement movement is already recorded.'))
        self._verify_sources()
        if self.state != 'approved' or self.cash_outcome != 'uncertain' or self.direction == 'balanced' or amount != abs(self.difference_amount):
            raise ValidationError(_('Record only the prepared exact top-up or return amount.'))
        if date < fields.Datetime.context_timestamp(self, self.approved_at).date() or date > fields.Date.context_today(self):
            raise ValidationError(_('Cash date must be between approval date and today.'))
        event = self.env['ps.te.cash.event']._record_movement(self, self.direction, amount, reference, date)
        super().write({'cash_event_id': event.id, 'cash_outcome': 'recorded'})
        self._event('cash_recorded', _('External top-up or return recorded with source reference'))
        return True

    def action_close(self, reason, expected_revision):
        self._lock()
        self._actor('finance')
        self.sudo().trip_id._assert_no_pending_cancellation()
        self._revision(expected_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Workflow closure reason'))
        if self.state == 'closed':
            return True
        self._verify_sources()
        if (self.state != 'approved' or self.cash_outcome == 'uncertain' or not self.funding_known
                or self.remaining_amount != 0 or (self.direction != 'balanced' and not self.cash_event_id)):
            raise ValidationError(_('Resolve every known obligation and uncertain cash outcome before closing.'))
        if not self.sudo().report_id.basis_locked or self.sudo().trip_id.funding_lock_settlement_id != self:
            raise ValidationError(_('The approved source bases must remain locked.'))
        super().write({'state': 'closed', 'closed_by_id': self.env.uid, 'closed_at': fields.Datetime.now()})
        self.sudo().trip_id._close_workflow_case(self)
        self._event('workflow_closed', reason)
        return True

    def _return_for_correction(self, correction):
        # Only a linked current-finance case may release an unexecuted basis.
        correction._actor('finance')
        if correction.trip_id != self.trip_id or self.sudo().trip_id.correction_case_id != correction:
            raise ValidationError(_('Correction source mismatch.'))
        if (self.state not in ('draft', 'submitted', 'approved') or self.cash_event_id
                or self.cash_outcome != 'not_started'):
            raise ValidationError(_('Recorded or uncertain settlement cash cannot be reset for correction.'))
        self._event('returned_by_correction', correction.description)
        self.sudo().report_id._set_settlement_lock(self, False)
        self.sudo().trip_id._set_funding_lock(False)
        return super().write({'state': 'draft', 'revision': self.revision + 1,
                              'approved_by_id': False, 'approved_at': False, 'approval_reason': False,
                              'submitted_receipt': False})

    def action_open_operation(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Settlement Operation'),
                'res_model': 'ps.te.settlement.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_settlement_id': self.id, 'default_expected_revision': self.revision,
                            'default_amount': abs(self.difference_amount) if self.difference_known else 0}}


class PsTeSettlementEvent(models.Model):
    _name = 'ps.te.settlement.event'
    _description = 'PS T&E Settlement History'
    _order = 'id desc'

    settlement_id = fields.Many2one('ps.te.settlement', required=True, readonly=True, ondelete='restrict', index=True)
    actor_id = fields.Many2one('res.users', required=True, readonly=True)
    occurred_at = fields.Datetime(required=True, readonly=True)
    revision = fields.Integer(required=True, readonly=True)
    event_type = fields.Char(required=True, readonly=True)
    reason = fields.Text(required=True, readonly=True)
    snapshot = fields.Text(required=True, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Settlement history is generated only by workflow actions.'))

    @api.model
    def _append(self, vals):
        return super().create(vals)

    def write(self, vals):
        raise AccessError(_('Settlement history cannot be changed.'))

    def unlink(self):
        raise AccessError(_('Settlement history must be retained.'))
