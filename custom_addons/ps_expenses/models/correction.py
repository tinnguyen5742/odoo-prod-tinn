import hashlib
import json
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class TripCorrection(models.Model):
    _name = 'ps.te.correction'
    _description = 'PS T&E Correction and Revalidation'
    _rec_name = 'reference'
    _order = 'id desc'
    _one_active = models.Constraint('UNIQUE(active_trip_id)', 'Only one active correction is allowed per trip.')

    reference = fields.Char(required=True, readonly=True)
    trip_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True, ondelete='restrict', index=True)
    active_trip_id = fields.Many2one('ps.te.trip.request', readonly=True, ondelete='restrict')
    owner_id = fields.Many2one('res.users', required=True, readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True)
    finance_reviewer_id = fields.Many2one('res.users', required=True, readonly=True)
    cash_operator_id = fields.Many2one('res.users', required=True, readonly=True)
    finance_assignment_valid = fields.Boolean(compute='_assignments', store=True)
    cash_assignment_valid = fields.Boolean(compute='_assignments', store=True)
    category = fields.Selection([('basis', 'Expense or Settlement Basis'), ('funding', 'Funding Record'),
                                 ('authority', 'Policy or Authority')], required=True, readonly=True)
    description = fields.Text(required=True, readonly=True)
    revision = fields.Integer(default=1, required=True, readonly=True)
    state = fields.Selection([('submitted', 'Correction Review'), ('pending_cash', 'Awaiting Independent Cash Check'),
                              ('external_required', 'External Resolution Required'), ('returned', 'Returned for Source Revision'),
                              ('resolved', 'Investigation Resolved — Sources Unchanged')], default='submitted', required=True, readonly=True)
    source_digest = fields.Char(required=True, readonly=True)
    source_snapshot = fields.Text(required=True, readonly=True)
    proposal_reason = fields.Text(readonly=True)
    proposal_reference = fields.Char(readonly=True)
    proposed_by_id = fields.Many2one('res.users', readonly=True)
    cash_confirmation_reference = fields.Char(readonly=True)
    cash_confirmed_by_id = fields.Many2one('res.users', readonly=True)
    resolved_by_id = fields.Many2one('res.users', readonly=True)
    resolved_at = fields.Datetime(readonly=True)
    event_ids = fields.One2many('ps.te.correction.event', 'correction_id', readonly=True)

    @api.depends('company_id.ps_te_finance_reviewer_id', 'company_id.ps_te_cash_operator_id', 'finance_reviewer_id', 'cash_operator_id')
    def _assignments(self):
        for record in self:
            record.finance_assignment_valid = record.finance_reviewer_id == record.company_id.ps_te_finance_reviewer_id
            record.cash_assignment_valid = record.cash_operator_id == record.company_id.ps_te_cash_operator_id

    @api.model
    def _configuration(self, trip):
        company = trip.company_id.sudo()
        finance, cash = company.ps_te_finance_reviewer_id, company.ps_te_cash_operator_id
        if not finance or not cash or finance == cash or trip.owner_id in (finance, cash):
            raise ValidationError(_('Configure distinct current finance and cash officers for correction review.'))
        for user, role in ((finance, 'finance'), (cash, 'cash')):
            if not user.active or company not in user.company_ids or not user.has_group('ps_expenses.group_ps_te_' + role):
                raise ValidationError(_('Correction officers need current company membership and matching roles.'))
        return {'finance_reviewer_id': finance.id, 'cash_operator_id': cash.id}

    @api.model
    def _sources(self, trip):
        trip = trip.sudo()
        advance, report, settlement, company = trip.advance_id, trip.expense_report_id, trip.settlement_id, trip.company_id
        # Deliberately no proof contents, filenames, employee line descriptions or claimed totals.
        data = {'trip': [trip.id, trip.preparing_revision, trip.state, trip.cancellation_status,
                         trip.cancellation_revision, trip.case_status],
                'company': [company.id, company.currency_id.id, company.ps_te_finance_reviewer_id.id,
                            company.ps_te_cash_operator_id.id, company.ps_te_advance_policy_reference,
                            company.ps_te_expense_policy_reference, company.ps_te_settlement_policy_reference],
                'advance': [advance.id, advance.revision, advance.state, advance.payment_outcome,
                            advance.disbursed_amount if advance.has_disbursement else None, advance.cash_reference,
                            str(advance.disbursement_date), advance.cash_event_id.id, advance.policy_reference,
                            advance.finance_reviewer_id.id, advance.cash_operator_id.id, advance.payment_attempt_reference],
                'expense': [report.id, report.revision, report.state, report.accepted_basis_ready,
                            report.accepted_total if report.accepted_basis_ready else None,
                            report.policy_reference, report.finance_reviewer_id.id, report.basis_locked],
                'settlement': [settlement.id, settlement.revision, settlement.state, settlement.cash_outcome,
                               settlement.cash_event_id.id, settlement.funding_known,
                               settlement.funding_amount if settlement.funding_known else None,
                               settlement.accepted_amount, settlement.policy_reference,
                               settlement.finance_reviewer_id.id, settlement.cash_operator_id.id,
                               settlement.cash_attempt_reference]}
        encoded = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
        return {'source_snapshot': encoded, 'source_digest': hashlib.sha256(encoded.encode()).hexdigest()}

    @api.model
    def _lock_sources(self, trip):
        trip.lock_for_update()
        trip.invalidate_recordset()
        for source in (trip.sudo().advance_id, trip.sudo().expense_report_id, trip.sudo().settlement_id):
            if source:
                source.lock_for_update()
                source.invalidate_recordset()

    @api.model_create_multi
    def create(self, vals_list):
        self.browse().check_access('create')
        prepared = []
        for vals in vals_list:
            if set(vals) != {'trip_id', 'category', 'description', 'expected_revision'}:
                raise AccessError(_('Correction identities, source snapshots and decisions are server controlled.'))
            trip = self.env['ps.te.trip.request'].browse(vals['trip_id']).exists()
            if len(trip) != 1:
                raise ValidationError(_('Select one trip for correction.'))
            trip.check_access('read')
            trip._assert_current_membership()
            if vals['category'] not in ('basis', 'funding', 'authority'):
                raise ValidationError(_('Unsupported correction category.'))
            reason = self.env['ps.te.trip.advance']._text(vals['description'], _('Correction description'))
            if len(reason) > 4000:
                raise ValidationError(_('Keep the correction description within 4000 characters.'))
            prepared.append((trip, vals, reason))
        if len({trip.id for trip, _, _ in prepared}) != len(prepared):
            raise ValidationError(_('Only one correction request per trip is allowed in a batch.'))
        self.env['ps.te.trip.request'].browse(sorted({trip.id for trip, _, _ in prepared})).lock_for_update()
        values = []
        for trip, vals, reason in prepared:
            self._lock_sources(trip)
            trip._assert_current_membership()
            if type(vals['expected_revision']) is not int or vals['expected_revision'] != trip.preparing_revision:
                raise ValidationError(_('Stale or conflicting preparing revision.'))
            if trip._has_active_correction():
                raise ValidationError(_('Use the active correction case instead of creating another one.'))
            values.append({'reference': 'COR-' + uuid.uuid4().hex.upper(), 'trip_id': trip.id,
                           'active_trip_id': trip.id, 'owner_id': trip.owner_id.id, 'company_id': trip.company_id.id,
                           'category': vals['category'], 'description': reason, 'revision': 1, 'state': 'submitted',
                           **self._configuration(trip), **self._sources(trip)})
        safe = self.with_context({k: v for k, v in self.env.context.items() if not k.startswith('default_')})
        records = super(TripCorrection, safe).create(values)
        for record in records:
            record.trip_id._bind_correction(record)
            record._event('opened', record.description)
        return records

    def write(self, vals):
        raise AccessError(_('Use correction actions; source facts and decisions cannot be edited directly.'))

    def unlink(self):
        raise AccessError(_('Correction cases and their history must be retained.'))

    def _lock(self):
        self.ensure_one()
        self.check_access('write')
        self._lock_sources(self.sudo().trip_id)
        self.lock_for_update()
        self.invalidate_recordset()

    def _actor(self, role):
        user, record = self.env.user, self.sudo()
        trip = record.trip_id
        if (not user.active or not user._is_internal() or record.company_id not in user.company_ids
                or record.company_id not in self.env.companies or not trip.employee_id.active or not trip.employee_mapping_valid):
            raise AccessError(_('Correction access is not permitted.'))
        if role == 'owner':
            if user != record.owner_id or not user.has_group('ps_expenses.group_ps_te_trip_employee'):
                raise AccessError(_('Only the requester may open or refresh the correction.'))
            return
        assigned = record.finance_reviewer_id if role == 'finance' else record.cash_operator_id
        valid = record.finance_assignment_valid if role == 'finance' else record.cash_assignment_valid
        if (role not in ('finance', 'cash') or user != assigned or not valid or user == record.owner_id
                or not user.has_group('ps_expenses.group_ps_te_' + role)):
            raise AccessError(_('Only the current assigned correction officer may perform this action.'))

    def _revision(self, revision):
        if type(revision) is not int or revision != self.revision:
            raise ValidationError(_('Stale correction revision. Reload the case.'))

    def _check_snapshot(self):
        if self.source_digest != self._sources(self.sudo().trip_id)['source_digest']:
            raise ValidationError(_('Correction sources or policy bindings changed. Refresh and review the exact snapshot.'))

    def _event(self, kind, reason):
        return self.env['ps.te.correction.event'].sudo()._append({
            'correction_id': self.id, 'actor_id': self.env.uid, 'occurred_at': fields.Datetime.now(),
            'revision': self.revision, 'kind': kind, 'reason': reason,
            'snapshot': json.dumps({'digest': self.source_digest, 'sources': json.loads(self.source_snapshot),
                                    'state': self.state, 'finance_id': self.finance_reviewer_id.id,
                                    'cash_id': self.cash_operator_id.id, 'proposal_reference': self.proposal_reference,
                                    'cash_reference': self.cash_confirmation_reference}, ensure_ascii=False, sort_keys=True)})

    def action_refresh(self, reason, expected_revision):
        self._lock()
        self._actor('owner')
        self._revision(expected_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Refresh reason'))
        if not self.active_trip_id:
            raise ValidationError(_('A resolved correction cannot be reopened or rewritten.'))
        self._event('snapshot_replaced', reason)
        super().write({**self._configuration(self.sudo().trip_id), **self._sources(self.sudo().trip_id),
                       'revision': self.revision + 1, 'state': 'submitted', 'proposal_reason': False,
                       'proposal_reference': False, 'proposed_by_id': False,
                       'cash_confirmation_reference': False, 'cash_confirmed_by_id': False})
        self._event('refreshed', reason)
        return True

    def action_return_for_revision(self, reason, expected_revision):
        self._lock()
        self._actor('finance')
        self._revision(expected_revision)
        self._check_snapshot()
        reason = self.env['ps.te.trip.advance']._text(reason, _('Return reason'))
        trip = self.sudo().trip_id
        advance, settlement = trip.advance_id, trip.settlement_id
        if (not self.active_trip_id or trip.case_status != 'open'
                or (advance and advance.payment_outcome == 'uncertain')
                or (settlement and (settlement.cash_event_id or settlement.cash_outcome != 'not_started' or settlement.state == 'closed'))
                or (self.category == 'funding' and advance.has_disbursement)):
            raise ValidationError(_('Executed, closed or uncertain sources require separate reconciliation, not reset.'))
        with self.env.cr.savepoint():
            if settlement:
                settlement._return_for_correction(self)
            super().write({'state': 'returned', 'active_trip_id': False,
                           'resolved_by_id': self.env.uid, 'resolved_at': fields.Datetime.now()})
            self._event('returned_for_revision', reason)
        return True

    def action_require_external(self, reference, reason, expected_revision):
        self._lock()
        self._actor('finance')
        self._revision(expected_revision)
        self._check_snapshot()
        if not self.active_trip_id:
            raise ValidationError(_('A resolved correction cannot be reopened or rewritten.'))
        helper = self.env['ps.te.trip.advance']
        reference, reason = helper._text(reference, _('Reconciliation reference')), helper._text(reason, _('Review reason'))
        super().write({'state': 'external_required', 'revision': self.revision + 1,
                       'proposal_reference': reference, 'proposal_reason': reason,
                       'proposed_by_id': self.env.uid, 'cash_confirmation_reference': False, 'cash_confirmed_by_id': False})
        self._event('external_required', reason)
        return True

    def _bindings_current(self):
        trip = self.sudo().trip_id
        if (trip.advance_id.payment_outcome == 'uncertain' or trip.settlement_id.cash_outcome == 'uncertain'):
            raise ValidationError(_('Reconcile uncertain external execution before a no-change disposition.'))
        if trip.advance_id:
            trip.advance_id._assert_policy()
        if trip.expense_report_id:
            trip.expense_report_id._policy()
        if trip.settlement_id:
            trip.settlement_id._verify_sources(require_funding=False)

    def action_propose_no_change(self, reference, reason, expected_revision):
        self._lock()
        self._actor('finance')
        self._revision(expected_revision)
        self._check_snapshot()
        self._bindings_current()
        if not self.active_trip_id:
            raise ValidationError(_('A resolved correction cannot be reopened or rewritten.'))
        helper = self.env['ps.te.trip.advance']
        reference, reason = helper._text(reference, _('Reconciliation reference')), helper._text(reason, _('Review reason'))
        if self.state == 'pending_cash':
            if (self.proposal_reference, self.proposal_reason) == (reference, reason):
                return True
            raise ValidationError(_('Refresh the case before replacing an existing no-change proposal.'))
        super().write({'state': 'pending_cash', 'revision': self.revision + 1,
                       'proposal_reference': reference, 'proposal_reason': reason,
                       'proposed_by_id': self.env.uid, 'cash_confirmation_reference': False, 'cash_confirmed_by_id': False})
        self._event('no_change_proposed', reason)
        return True

    def action_confirm_no_change(self, reference, reason, expected_revision):
        self._lock()
        self._actor('cash')
        self._revision(expected_revision)
        self._check_snapshot()
        self._bindings_current()
        helper = self.env['ps.te.trip.advance']
        reference, reason = helper._text(reference, _('Reconciliation reference')), helper._text(reason, _('Review reason'))
        if self.state != 'pending_cash' or not self.proposed_by_id or self.proposed_by_id == self.env.user:
            raise ValidationError(_('Finance must propose unchanged facts before an independent cash check.'))
        if self.cash_confirmed_by_id:
            if self.cash_confirmation_reference == reference:
                return True
            raise ValidationError(_('A different cash confirmation is already recorded for this snapshot.'))
        super().write({'cash_confirmation_reference': reference, 'cash_confirmed_by_id': self.env.uid})
        self._event('no_change_cash_checked', reason)
        return True

    def action_resolve_no_change(self, reason, expected_revision):
        self._lock()
        self._actor('finance')
        self._revision(expected_revision)
        self._check_snapshot()
        self._bindings_current()
        reason = self.env['ps.te.trip.advance']._text(reason, _('Review reason'))
        if self.state == 'resolved':
            return True
        if (self.state != 'pending_cash' or not self.cash_confirmed_by_id or not self.cash_confirmation_reference
                or self.cash_confirmed_by_id == self.env.user):
            raise ValidationError(_('Complete the independent no-change checks before resolving the correction.'))
        super().write({'state': 'resolved', 'active_trip_id': False,
                       'resolved_by_id': self.env.uid, 'resolved_at': fields.Datetime.now()})
        self._event('resolved_without_source_change', reason)
        return True

    def action_open_operation(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Correction Case'),
                'res_model': 'ps.te.correction.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_correction_id': self.id, 'default_trip_id': self.trip_id.id,
                            'default_expected_revision': self.revision}}


class CorrectionEvent(models.Model):
    _name = 'ps.te.correction.event'
    _description = 'PS T&E Correction History'
    _order = 'id desc'

    correction_id = fields.Many2one('ps.te.correction', required=True, readonly=True, ondelete='restrict')
    actor_id = fields.Many2one('res.users', required=True, readonly=True)
    occurred_at = fields.Datetime(required=True, readonly=True)
    revision = fields.Integer(required=True, readonly=True)
    kind = fields.Char(required=True, readonly=True)
    reason = fields.Text(required=True, readonly=True)
    snapshot = fields.Text(required=True, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Correction history is created only by workflow actions.'))

    @api.model
    def _append(self, vals):
        safe = self.with_context({k: v for k, v in self.env.context.items() if not k.startswith('default_')})
        return super(CorrectionEvent, safe).create(vals)

    def write(self, vals):
        raise AccessError(_('Correction history cannot be changed.'))

    def unlink(self):
        raise AccessError(_('Correction history must be retained.'))
