"""Versioned financial adjustments; originals are never reopened or overwritten.

The software workflow records approvals and external facts. It neither moves
bank money nor posts accounting/tax entries.
"""
import hashlib
import json
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from .expense_report import PsTeExpenseReport
from .trip_request import PsTeTripRequest
from .correction import TripCorrection
from .trip_advance import PsTeTripAdvance
from .trip_amendment import TripAmendment


class FinancialAdjustment(models.Model):
    _name = 'ps.te.adjustment'
    _description = 'PS T&E Versioned Financial Adjustment'
    _rec_name = 'reference'
    _order = 'id desc'
    _one_active = models.Constraint('UNIQUE(active_trip_id)', 'Only one financial adjustment may remain active per trip.')

    reference = fields.Char(required=True, readonly=True)
    correction_id = fields.Many2one('ps.te.correction', required=True, readonly=True, ondelete='restrict')
    trip_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True, ondelete='restrict', index=True)
    active_trip_id = fields.Many2one('ps.te.trip.request', readonly=True, ondelete='restrict')
    owner_id = fields.Many2one(related='correction_id.owner_id', store=True)
    company_id = fields.Many2one(related='correction_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    finance_reviewer_id = fields.Many2one('res.users', required=True, readonly=True)
    cash_operator_id = fields.Many2one('res.users', required=True, readonly=True)
    reason = fields.Text(required=True, readonly=True)
    revision = fields.Integer(required=True, default=1, readonly=True)
    source_digest = fields.Char(required=True, readonly=True)
    amendment_id = fields.Many2one('ps.te.trip.amendment', readonly=True, ondelete='restrict')
    amended_purpose = fields.Char(related='amendment_id.purpose')
    amended_destination = fields.Char(related='amendment_id.destination')
    amended_start_date = fields.Date(related='amendment_id.start_date')
    amended_end_date = fields.Date(related='amendment_id.end_date')
    amendment_manager_id = fields.Many2one(related='amendment_id.decided_by_id')
    previous_report_id = fields.Many2one('ps.te.expense.report', readonly=True, ondelete='restrict',
        groups='ps_expenses.group_ps_te_finance,ps_expenses.group_ps_te_trip_employee')
    carry_report_id = fields.Many2one('ps.te.expense.report', readonly=True, ondelete='restrict')
    report_id = fields.Many2one('ps.te.expense.report', readonly=True, ondelete='restrict',
        groups='ps_expenses.group_ps_te_finance,ps_expenses.group_ps_te_trip_employee')
    state = fields.Selection([('draft', 'Adjustment Expense Preparation'), ('cash', 'Independent Adjustment Cash Check'),
        ('finance', 'Final Adjustment Authorization'), ('approved', 'Adjustment Authorized'),
        ('closed', 'Adjustment Workflow Closed'), ('withdrawn', 'Unexecuted Adjustment Withdrawn')],
        required=True, default='draft', readonly=True)
    accepted_amount = fields.Monetary(readonly=True)
    retained_amount = fields.Monetary(readonly=True)
    difference_amount = fields.Monetary(readonly=True)
    proposal_snapshot = fields.Text(readonly=True)
    proposed_by_id = fields.Many2one('res.users', readonly=True)
    proposal_reason = fields.Text(readonly=True)
    cash_confirmed_by_id = fields.Many2one('res.users', readonly=True)
    cash_confirmation_reference = fields.Char(readonly=True)
    no_funding_reference = fields.Char(readonly=True)
    no_funding_confirmed_by_id = fields.Many2one('res.users', readonly=True)
    approved_by_id = fields.Many2one('res.users', readonly=True)
    approved_at = fields.Datetime(readonly=True)
    cash_outcome = fields.Selection([('not_started', 'No Adjustment Cash Recorded'),
        ('uncertain', 'External Cash Outcome Unconfirmed'), ('recorded', 'External Cash Recorded')],
        required=True, default='not_started', readonly=True)
    cash_attempt_reference = fields.Char(readonly=True)
    cash_event_id = fields.Many2one('ps.te.cash.event', readonly=True, ondelete='restrict')
    closed_by_id = fields.Many2one('res.users', readonly=True)
    closed_at = fields.Datetime(readonly=True)
    event_ids = fields.One2many('ps.te.adjustment.event', 'adjustment_id', readonly=True)
    accounting_status = fields.Selection([('not_verified', 'External Accounting Not Verified')],
        default='not_verified', required=True, readonly=True)
    money_comparison_current = fields.Boolean(compute='_compute_money_comparison')
    current_net_retained = fields.Monetary(compute='_compute_money_comparison')
    current_remaining_amount = fields.Monetary(compute='_compute_money_comparison')
    workflow_next_step = fields.Text(string='Next Step', compute='_compute_next_step')

    @api.depends('state', 'cash_outcome', 'cash_event_id', 'trip_id.correction_hold',
        'trip_id.latest_completed_adjustment_id', 'report_id.accepted_basis_ready',
        'correction_id.source_digest', 'company_id.ps_te_finance_reviewer_id', 'company_id.ps_te_cash_operator_id',
        'company_id.ps_te_expense_policy_reference', 'company_id.ps_te_settlement_policy_reference')
    def _compute_money_comparison(self):
        for record in self:
            known = False
            money = self.env['ps.te.cash.event']._verified_net(record.sudo().trip_id)
            try:
                if record.state == 'approved':
                    record._proposal_current()
                    known = money['known']
                elif record.state == 'closed':
                    trip = record.sudo().trip_id
                    config = self.env['ps.te.settlement']._configuration(trip)
                    record.sudo().report_id._policy()
                    if record.sudo().amendment_id:
                        record.sudo().amendment_id._financial_decision_current()
                    known = bool(trip.latest_completed_adjustment_id == record and not trip.correction_hold
                        and config['finance_reviewer_id'] == record.finance_reviewer_id.id
                        and config['cash_operator_id'] == record.cash_operator_id.id and money['known']
                        and money['amount'] == record.accepted_amount)
            except (AccessError, ValidationError):
                known = False
            record.money_comparison_current = known
            record.current_net_retained = money['amount'] if known else 0
            record.current_remaining_amount = abs(record.accepted_amount - money['amount']) if known else 0

    @api.depends_context('lang')
    def _compute_next_step(self):
        for record in self:
            if record.state in ('investigate', 'verify'):
                message = _('Investigate only the old external attempt with current independent officers. Do not start another payment; a fresh successor review must resolve the held case.')
            elif record.state == 'reconciled':
                message = _('Old attempt reconciled, not financially closed. Owner: create a successor expense version; finance and cash must review the whole remaining difference under current policy.')
            elif record.cash_outcome == 'uncertain':
                message = _('Cash operator: reconcile the existing settlement attempt using external evidence before any retry or closure. A lost response does not prove non-execution.')
            elif record.state == 'closed':
                message = _('Workflow closed. External accounting is still not verified; retained history must not be overwritten.')
            elif record.state == 'withdrawn':
                message = _('This unexecuted version is retained as history. The correction hold remains; use a fresh version, never overwrite this one.')
            elif record.state == 'cash':
                message = _('Assigned cash operator: independently verify the cumulative external cash facts proposed by finance, not the private expense proofs.')
            elif record.state == 'finance':
                message = _('Assigned finance: check the independent cash confirmation and explicitly authorize the exact whole adjustment difference.')
            elif record.state == 'approved':
                message = _('Resolve the exact authorized whole payment or return, then finance explicitly closes. A zero difference requires closure without a fake cash movement.')
            else:
                message = _('Owner: author the complete new expense basis or explicitly carry previous claims for fresh finance review. Original approvals are not reused; unknown funding must be independently confirmed.')
            record.workflow_next_step = message

    @api.model_create_multi
    def create(self, vals_list):
        self.browse().check_access('create')
        allowed = {'correction_id', 'reason', 'expected_revision'}
        if any(set(vals) != allowed for vals in vals_list):
            raise AccessError(_('Adjustment identities, sources and decisions are server controlled.'))
        cases = self.env['ps.te.correction'].browse(sorted({vals['correction_id'] for vals in vals_list})).exists()
        cases.check_access('read')
        for case in cases:
            case._actor('owner')
        self.env['ps.te.trip.request'].browse(sorted(cases.mapped('trip_id').ids)).lock_for_update()
        prepared = []
        for vals in vals_list:
            case = self.env['ps.te.correction'].browse(vals['correction_id']).exists()
            if len(case) != 1:
                raise ValidationError(_('Select the exact active financial correction case.'))
            case._lock()
            case._actor('owner')
            case._revision(vals['expected_revision'])
            case._check_snapshot()
            trip = case.trip_id
            previous = trip.effective_expense_report_id or trip.expense_report_id
            # The owner may author a first complete basis if none existed. A
            # missing previous report is not an accepted zero expense basis.
            if (not case.active_trip_id
                    or (trip.state != 'approved' and trip.cancellation_status != 'approved')
                    or trip.advance_id.payment_outcome == 'uncertain' or trip.settlement_id.cash_outcome == 'uncertain'):
                raise ValidationError(_('Resolve uncertain execution and identify the previous reviewed expense basis first.'))
            reason = self.env['ps.te.trip.advance']._text(vals['reason'], _('Adjustment reason'))
            reconciled = self.sudo().search([('correction_id', '=', case.id), ('state', '=', 'reconciled')], order='id desc', limit=1)
            carry = reconciled.report_id if reconciled else previous
            prepared.append({'reference': 'ADJ-' + uuid.uuid4().hex.upper(), 'correction_id': case.id,
                'trip_id': trip.id, 'active_trip_id': trip.id, 'reason': reason, 'state': 'draft', 'revision': 1,
                'previous_report_id': previous.id, 'carry_report_id': carry.id, 'source_digest': case.source_digest,
                'amendment_id': reconciled.amendment_id.id or False,
                'finance_reviewer_id': case.finance_reviewer_id.id, 'cash_operator_id': case.cash_operator_id.id})
        safe = self.with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
        with self.env.cr.savepoint():
            records = super(FinancialAdjustment, safe).create(prepared)
            for record in records:
                report = self.env['ps.te.expense.report']._create_adjustment_report(record)
                super(FinancialAdjustment, record).write({'report_id': report.id})
                record._event('opened', record.reason)
        return records

    def write(self, vals):
        raise AccessError(_('Use adjustment workflow actions; direct changes are forbidden.'))

    def unlink(self):
        raise AccessError(_('Adjustment versions and decisions must be retained.'))

    def _actor(self, role):
        self.ensure_one()
        self.correction_id._actor(role)
        if role == 'owner':
            return
        if (self.finance_reviewer_id != self.correction_id.finance_reviewer_id
                or self.cash_operator_id != self.correction_id.cash_operator_id):
            raise ValidationError(_('Adjustment officers changed; renew the unexecuted review.'))

    def _lock(self):
        self.ensure_one()
        self.check_access('write')
        self.correction_id._lock()
        self.lock_for_update()
        self.invalidate_recordset()

    def _revision(self, expected):
        if type(expected) is not int or self.revision != expected:
            raise ValidationError(_('Stale financial adjustment revision. Reload the case.'))

    def _check_sources(self):
        self.ensure_one()
        case = self.correction_id
        case._check_snapshot()
        if self.sudo().amendment_id:
            self.sudo().amendment_id._financial_decision_current()
        previous = self.trip_id.effective_expense_report_id or self.trip_id.expense_report_id
        if (not self.active_trip_id or not case.active_trip_id or case.source_digest != self.source_digest
                or previous != self.previous_report_id or self.trip_id.correction_case_id != case):
            raise ValidationError(_('Adjustment sources changed; retain the hold and renew review.'))

    def _event(self, kind, reason):
        data = self.sudo()
        return self.env['ps.te.adjustment.event']._append({
            'adjustment_id': self.id, 'actor_id': self.env.uid, 'occurred_at': fields.Datetime.now(),
            'revision': self.revision, 'kind': kind, 'reason': reason,
            'snapshot': json.dumps({'state': data.state, 'source_digest': data.source_digest,
                'report_id': data.report_id.id, 'previous_report_id': data.previous_report_id.id,
                'accepted': data.accepted_amount, 'retained': data.retained_amount, 'difference': data.difference_amount,
                'proposal': data.proposal_snapshot, 'cash_outcome': data.cash_outcome,
                'attempt': data.cash_attempt_reference, 'event_id': data.cash_event_id.id,
                'proposed_by': data.proposed_by_id.id, 'cash_confirmed_by': data.cash_confirmed_by_id.id,
                'cash_reference': data.cash_confirmation_reference, 'approved_by': data.approved_by_id.id,
                'reconciliation': {'finance': data.reconciliation_finance_id.id, 'cash': data.reconciliation_cash_id.id,
                    'digest': data.reconciliation_digest, 'snapshot': data.reconciliation_snapshot,
                    'outcome': data.observed_outcome, 'amount': data.observed_amount,
                    'reference': data.observed_reference, 'date': str(data.observed_date),
                    'evidence': data.observation_evidence, 'proposed_by': data.observation_proposed_by_id.id,
                    'verified_by': data.observation_verified_by_id.id, 'verification': data.observation_verification_reference,
                    'completed_by': data.reconciliation_completed_by_id.id,
                    'completed_at': str(data.reconciliation_completed_at)}}, sort_keys=True)})

    def action_copy_previous_basis(self, reason, expected_revision):
        self._lock()
        self._actor('owner')
        self._revision(expected_revision)
        self._check_sources()
        report = self.report_id
        report._lock()
        report._draft()
        if not self.carry_report_id or report.line_ids or report.zero_expense_declared:
            raise ValidationError(_('Copy the previous basis only into an empty adjustment version.'))
        reason = self.env['ps.te.trip.advance']._text(reason, _('Adjustment reason'))
        with self.env.cr.savepoint():
            for old in self.carry_report_id.line_ids:
                line_id = report.action_add_line(old.description, old.claimed_amount, old.expense_date, report.revision)
                for evidence in old._active_proofs():
                    report.action_reuse_evidence(line_id, evidence.id, report.revision)
            if self.carry_report_id.zero_expense_declared:
                report.action_declare_zero_expenses(reason, report.revision)
            self._event('basis_copied', reason)
        return True

    def action_open_expenses(self):
        self.ensure_one()
        self.check_access('read')
        self.report_id._assert_viewer()
        return self.report_id._entry_action()

    def action_open_operation(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Financial Adjustment Operation'),
                'res_model': 'ps.te.adjustment.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_adjustment_id': self.id, 'default_expected_revision': self.revision,
                            'default_amount': abs(self.difference_amount)}}

    def _renew_owned_sources(self, reason):
        """Only after an explicit authorized domain operation while held.

        Not a public refresh or a context bypass. Previous snapshots remain in
        both histories. Policy/officer drift still requires separate renewal.
        """
        case = self.correction_id
        case._event('snapshot_replaced', reason)
        sources = case._sources(self.trip_id)
        super(TripCorrection, case).write({**sources, 'revision': case.revision + 1})
        super(FinancialAdjustment, self).write({'source_digest': sources['source_digest'],
                                               'revision': self.revision + 1})
        case._event('refreshed', reason)

    def action_declare_no_advance(self, reason, expected_revision):
        self._lock()
        self._actor('owner')
        self._revision(expected_revision)
        self._check_sources()
        reason = self.env['ps.te.trip.advance']._text(reason, _('Cancellation reason'))
        trip = self.trip_id
        advance = trip.sudo().advance_id
        if (self.state != 'draft' or advance.has_disbursement or advance.cash_event_id
                or advance.payment_outcome == 'uncertain'):
            raise ValidationError(_('Recorded disbursement cannot be cancelled; resolve it through settlement.'))
        with self.env.cr.savepoint():
            if advance and advance.state != 'cancelled':
                advance._event('cancelled', self.reference + ': ' + reason)
                super(PsTeTripAdvance, advance).write({'state': 'cancelled', 'decision_reason': reason})
            super(PsTeTripRequest, trip).write({'advance_choice': 'not_requested'})
            trip._record_event('advance_not_requested', self.reference + ': ' + reason)
            self._renew_owned_sources(reason)
            self._event('no_advance_declared', reason)
        return True

    def action_confirm_no_funding(self, reference, reason, expected_revision):
        self._lock()
        self._actor('cash')
        self._revision(expected_revision)
        self._check_sources()
        helper = self.env['ps.te.trip.advance']
        reference, reason = helper._text(reference, _('No-funding reconciliation reference')), helper._text(reason, _('No-funding confirmation reason'))
        trip = self.sudo().trip_id
        advance = trip.advance_id
        if (self.state != 'draft' or trip.advance_choice != 'not_requested'
                or (advance and (advance.state != 'cancelled' or advance.has_disbursement
                                  or advance.cash_event_id or advance.payment_outcome == 'uncertain'))):
            raise ValidationError(_('Resolve or cancel the advance and explicitly declare no advance first.'))
        if self.no_funding_reference:
            if self.no_funding_reference == reference and self.no_funding_confirmed_by_id == self.env.user:
                return True
            raise ValidationError(_('A different no-funding confirmation is already retained for this adjustment.'))
        super().write({'no_funding_reference': reference, 'no_funding_confirmed_by_id': self.env.uid})
        self._event('no_funding_confirmed', reason)
        return True

    def _basis_snapshot(self):
        data = self.sudo()
        report = data.report_id
        report._policy()
        if not report.accepted_basis_ready:
            raise ValidationError(_('Review every line of the new expense version before proposing an adjustment.'))
        money = self.env['ps.te.cash.event']._verified_net(data.trip_id, exclude_adjustment=data)
        if not money['known']:
            raise ValidationError(_('Reconcile all cash facts and funding before proposing the exact adjustment.'))
        return {'source': data.source_digest, 'expense': [report.id, report.revision, report.state,
            report.accepted_total, report.policy_reference, report.finance_reviewer_id.id],
            'cash_digest': money['digest'], 'retained': money['amount']}

    def _proposal_current(self):
        self._check_sources()
        if not self.proposal_snapshot or json.loads(self.proposal_snapshot) != self._basis_snapshot():
            raise ValidationError(_('Adjustment expense or cash facts changed; renew the exact unexecuted proposal.'))

    def action_propose_basis(self, reason, expected_revision):
        self._lock()
        self._actor('finance')
        self._revision(expected_revision)
        self._check_sources()
        reason = self.env['ps.te.trip.advance']._text(reason, _('Review reason'))
        if self.state != 'draft':
            raise ValidationError(_('Propose only a fully reviewed draft adjustment version.'))
        report = self.sudo().report_id
        with self.env.cr.savepoint():
            if self.sudo().amendment_id.state == 'finance':
                # Never apply trip facts if the new expense/cash basis is not
                # ready. The whole application + proposal is atomic.
                self._basis_snapshot()
                self.sudo().amendment_id._apply_financial_amendment(self)
            snapshot = self._basis_snapshot()
            super(PsTeExpenseReport, report).write({'basis_locked': True})
            super().write({'state': 'cash', 'revision': self.revision + 1,
                'accepted_amount': report.accepted_total, 'retained_amount': snapshot['retained'],
                'difference_amount': report.accepted_total - snapshot['retained'], 'proposal_reason': reason,
                'proposal_snapshot': json.dumps(snapshot, sort_keys=True), 'proposed_by_id': self.env.uid})
            self._event('basis_proposed', reason)
        return True

    def action_confirm_cash(self, reference, reason, expected_revision):
        self._lock()
        self._actor('cash')
        self._revision(expected_revision)
        self._proposal_current()
        helper = self.env['ps.te.trip.advance']
        reference, reason = helper._text(reference, _('Reconciliation reference')), helper._text(reason, _('Review reason'))
        if (self.state in ('finance', 'approved') and self.cash_confirmed_by_id == self.env.user
                and self.cash_confirmation_reference == reference):
            return True
        if (self.state != 'cash' or self.proposed_by_id != self.finance_reviewer_id
                or self.proposed_by_id == self.env.user):
            raise ValidationError(_('Current finance must propose the exact basis before an independent cash check.'))
        super().write({'state': 'finance', 'cash_confirmed_by_id': self.env.uid, 'cash_confirmation_reference': reference})
        self._event('cash_checked', reason)
        return True

    def action_authorize(self, reason, expected_revision):
        self._lock()
        self._actor('finance')
        self._revision(expected_revision)
        self._proposal_current()
        reason = self.env['ps.te.trip.advance']._text(reason, _('Review reason'))
        if self.state == 'approved' and self.approved_by_id == self.env.user:
            return True
        if (self.state != 'finance' or self.cash_confirmed_by_id != self.cash_operator_id
                or not self.cash_confirmation_reference or self.cash_confirmed_by_id == self.env.user):
            raise ValidationError(_('Complete the independent cash check before final finance authorization.'))
        super().write({'state': 'approved', 'approved_by_id': self.env.uid, 'approved_at': fields.Datetime.now()})
        self._event('authorized', reason)
        return True

    def action_start_cash(self, reference, reason, expected_revision):
        self._lock()
        self._actor('cash')
        self._revision(expected_revision)
        self._proposal_current()
        helper = self.env['ps.te.trip.advance']
        reference, reason = helper._text(reference, _('Payment attempt reference')), helper._text(reason, _('Review reason'))
        if self.state != 'approved' or self.difference_amount == 0 or self.cash_event_id:
            raise ValidationError(_('Prepare only an authorized whole remaining adjustment payment or return.'))
        if self.cash_outcome == 'uncertain':
            if self.cash_attempt_reference == reference:
                return True
            raise ValidationError(_('Reconcile the uncertain cash operation before another attempt.'))
        super().write({'cash_outcome': 'uncertain', 'cash_attempt_reference': reference})
        self._event('cash_started', reason)
        return True

    def action_confirm_not_executed(self, reference, reason, expected_revision):
        self._lock()
        self._actor('cash')
        self._revision(expected_revision)
        self._proposal_current()
        helper = self.env['ps.te.trip.advance']
        reference, reason = helper._text(reference, _('Reconciliation reference')), helper._text(reason, _('Review reason'))
        if self.state != 'approved' or self.cash_outcome != 'uncertain' or self.cash_event_id:
            raise ValidationError(_('Reconcile only the exact prepared uncertain adjustment attempt.'))
        self._event('cash_nonexecution_checked', reference + ': ' + reason)
        super().write({'cash_outcome': 'not_started'})
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
            raise ValidationError(_('A different adjustment cash movement is already recorded.'))
        self._proposal_current()
        if (self.state != 'approved' or self.cash_outcome != 'uncertain'
                or self.difference_amount == 0 or amount != abs(self.difference_amount)):
            raise ValidationError(_('Record only the prepared exact whole adjustment amount.'))
        if date < fields.Datetime.context_timestamp(self, self.approved_at).date() or date > fields.Date.context_today(self):
            raise ValidationError(_('Cash date must be between approval date and today.'))
        with self.env.cr.savepoint():
            event = self.env['ps.te.cash.event']._record_movement(
                self, 'topup' if self.difference_amount > 0 else 'return', amount, reference, date)
            super().write({'cash_event_id': event.id, 'cash_outcome': 'recorded'})
            self._event('cash_recorded', _('External top-up or return recorded with source reference'))
        return True

    def action_close(self, reason, expected_revision):
        self._lock()
        self._actor('finance')
        self._revision(expected_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Workflow closure reason'))
        if self.state == 'closed':
            return True
        self._proposal_current()
        money = self.env['ps.te.cash.event']._verified_net(self.trip_id)
        if (self.state != 'approved' or self.cash_outcome == 'uncertain' or not money['known']
                or money['amount'] != self.accepted_amount
                or (self.difference_amount != 0 and not self.cash_event_id)
                or (self.difference_amount == 0 and self.cash_event_id)):
            raise ValidationError(_('Resolve the full verified money difference before explicit adjustment closure.'))
        trip = self.sudo().trip_id
        # This action resolves its exact linked active correction. The normal
        # trip guard deliberately blocks ALL active corrections, including this
        # one, so use the explicit cancellation check without a caller flag.
        if trip.cancellation_status == 'requested':
            raise ValidationError(_('Decide the pending trip cancellation before closing this adjustment.'))
        if trip.amendment_hold:
            raise ValidationError(_('Integrate the approved trip amendment before closing this financial adjustment.'))
        with self.env.cr.savepoint():
            super().write({'state': 'closed', 'active_trip_id': False,
                           'closed_by_id': self.env.uid, 'closed_at': fields.Datetime.now()})
            # Original trip.expense_report_id, original settlement and its past
            # closure remain unchanged. Only the effective version advances.
            super(PsTeTripRequest, trip).write({'effective_expense_report_id': self.sudo().report_id.id,
                                               'latest_completed_adjustment_id': self.id})
            if trip.expense_report_id:
                super(PsTeExpenseReport, trip.expense_report_id).write({'basis_locked': True})
            if trip.case_status != 'workflow_closed':
                super(PsTeTripRequest, trip).write({'case_status': 'workflow_closed',
                    'case_closed_at': self.closed_at, 'case_closed_by_id': self.env.uid})
            case = self.correction_id
            super(TripCorrection, case).write({'state': 'adjusted', 'active_trip_id': False,
                'resolved_by_id': self.env.uid, 'resolved_at': fields.Datetime.now()})
            case._event('adjustment_closed', self.reference + ': ' + reason)
            self._event('workflow_closed', reason)
        return True

    def action_withdraw(self, reason, expected_revision):
        self._lock()
        self._actor('owner')
        self._revision(expected_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Adjustment reason'))
        if not self.active_trip_id or self.cash_event_id or self.cash_outcome != 'not_started':
            raise ValidationError(_('Executed, closed or uncertain adjustments cannot be withdrawn.'))
        with self.env.cr.savepoint():
            self._event('proposal_withdrawn', reason)
            super(PsTeExpenseReport, self.sudo().report_id).write({'basis_locked': True})
            super().write({'state': 'withdrawn', 'active_trip_id': False})
        return True


class AdjustmentProofLink(models.Model):
    _name = 'ps.te.expense.proof.link'
    _description = 'PS T&E Immutable Expense Proof Reference'
    _unique_active_proof = models.Constraint('UNIQUE(active_report_id, evidence_id)',
        'An existing proof may support only one active line in an adjustment version.')

    line_id = fields.Many2one('ps.te.expense.line', required=True, readonly=True, ondelete='restrict')
    report_id = fields.Many2one(related='line_id.report_id', store=True)
    evidence_id = fields.Many2one('ps.te.expense.evidence', required=True, readonly=True, ondelete='restrict')
    active_report_id = fields.Many2one('ps.te.expense.report', readonly=True, ondelete='restrict')
    filename = fields.Char(related='evidence_id.filename')
    sha256 = fields.Char(related='evidence_id.sha256')
    linked_by_id = fields.Many2one('res.users', required=True, readonly=True)
    linked_at = fields.Datetime(required=True, readonly=True)
    superseded = fields.Boolean(default=False, readonly=True)
    superseded_reason = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Link an existing proof through its adjustment expense report.'))

    @api.model
    def _append(self, line, evidence):
        # Private factory: caller already holds the exact authorized report lock.
        safe = self.sudo().with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
        if self.sudo().search_count([('active_report_id', '=', line.report_id.id), ('evidence_id', '=', evidence.id)]):
            raise ValidationError(_('An existing proof may support only one active line in an adjustment version.'))
        return super(AdjustmentProofLink, safe).create({'line_id': line.id, 'evidence_id': evidence.id,
            'active_report_id': line.report_id.id, 'linked_by_id': self.env.uid, 'linked_at': fields.Datetime.now()})

    def write(self, vals):
        raise AccessError(_('Proof references cannot be edited or reparented.'))

    def unlink(self):
        raise AccessError(_('Historical proof references must be retained.'))

    def action_supersede(self, reason, expected_revision):
        self.ensure_one()
        self.check_access('read')
        report = self.report_id
        report._lock()
        report._assert_actor('owner')
        report._revision(expected_revision)
        report._draft()
        reason = self.env['ps.te.trip.advance']._text(reason, _('Supersession reason'))
        if self.superseded:
            raise ValidationError(_('This proof has already been superseded.'))
        super(AdjustmentProofLink, self.sudo()).write({'superseded': True, 'superseded_reason': reason, 'active_report_id': False})
        report._advance_revision()
        report._event('evidence_superseded', reason, self.line_id)
        return True

    def action_download(self):
        self.ensure_one()
        self.check_access('read')
        self.report_id._assert_viewer()
        return self.evidence_id.action_download()


class AdjustmentEvent(models.Model):
    _name = 'ps.te.adjustment.event'
    _description = 'PS T&E Financial Adjustment History'
    _order = 'id desc'

    adjustment_id = fields.Many2one('ps.te.adjustment', required=True, readonly=True, ondelete='restrict')
    actor_id = fields.Many2one('res.users', required=True, readonly=True)
    occurred_at = fields.Datetime(required=True, readonly=True)
    revision = fields.Integer(required=True, readonly=True)
    kind = fields.Char(required=True, readonly=True)
    reason = fields.Text(required=True, readonly=True)
    snapshot = fields.Text(required=True, readonly=True)
    event_label = fields.Char(string='History Action', compute='_compute_event_label')

    @api.depends_context('lang')
    @api.depends('kind')
    def _compute_event_label(self):
        labels = {'opened': _('History: financial adjustment opened'),
            'basis_copied': _('History: previous claims copied for fresh review'),
            'basis_proposed': _('History: exact adjustment basis proposed'),
            'cash_checked': _('History: cumulative cash independently checked'),
            'authorized': _('History: exact adjustment difference authorized'),
            'cash_started': _('History: external cash attempt prepared'),
            'cash_nonexecution_checked': _('History: external non-execution confirmed'),
            'cash_recorded': _('History: actual external movement recorded'),
            'no_funding_confirmed': _('History: no funding explicitly confirmed'),
            'no_advance_declared': _('No Advance Requested'),
            'workflow_closed': _('History: workflow closed, accounting separate'),
            'proposal_withdrawn': _('History: unexecuted adjustment withdrawn')}
        labels.update({
            'manager_amendment_bound': _('History: manager amendment bound to financial review'),
            'manager_amendment_applied': _('History: manager-approved trip facts applied by finance'),
            'reconciliation_bindings_retained': _('History: previous attempt authority retained'),
            'existing_attempt_review_requested': _('History: current-officer old-attempt investigation requested'),
            'old_outcome_proposed': _('History: observed old-attempt outcome proposed'),
            'old_outcome_verified': _('History: observed old-attempt outcome independently verified'),
            'old_attempt_reconciled_successor_required': _('History: old attempt reconciled, fresh successor required'),
        })
        for event in self:
            event.event_label = labels.get(event.kind, _('Unrecognized history event; inspect the retained code.'))

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Adjustment history is generated only by workflow actions.'))

    @api.model
    def _append(self, values):
        safe = self.sudo().with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
        return super(AdjustmentEvent, safe).create(values)

    def write(self, vals):
        raise AccessError(_('Adjustment history cannot be changed.'))

    def unlink(self):
        raise AccessError(_('Adjustment history must be retained.'))


class AdjustmentTripState(models.Model):
    _inherit = 'ps.te.trip.request'

    effective_expense_report_id = fields.Many2one('ps.te.expense.report', readonly=True, ondelete='restrict',
        groups='ps_expenses.group_ps_te_finance,ps_expenses.group_ps_te_trip_employee')
    latest_completed_adjustment_id = fields.Many2one('ps.te.adjustment', readonly=True, ondelete='restrict')

    def action_open_expenses(self):
        self.ensure_one()
        self.check_access('read')
        self._assert_current_membership()
        active = self.correction_case_id.adjustment_ids.filtered('active_trip_id')
        report = active.report_id if active else self.effective_expense_report_id
        if report:
            return report._entry_action()
        return super().action_open_expenses()

    def action_open_settlement(self):
        self.ensure_one()
        self.check_access('read')
        self._assert_current_membership()
        active = self.correction_case_id.adjustment_ids.filtered('active_trip_id')
        current = active or self.latest_completed_adjustment_id
        if current:
            return {'type': 'ir.actions.act_window', 'res_model': 'ps.te.adjustment',
                    'res_id': current.id, 'view_mode': 'form'}
        return super().action_open_settlement()


class CorrectionAdjustmentGuard(models.Model):
    _inherit = 'ps.te.correction'

    adjustment_ids = fields.One2many('ps.te.adjustment', 'correction_id', readonly=True)
    state = fields.Selection(selection_add=[('adjusted', 'Financial Adjustment Completed')],
                             ondelete={'adjusted': 'set default'})

    @api.model
    def _sources(self, trip):
        values = super()._sources(trip)
        snapshot = json.loads(values['source_snapshot'])
        effective = trip.sudo().effective_expense_report_id
        snapshot['effective_adjustment'] = [effective.id, effective.revision, effective.state,
            effective.accepted_total, effective.policy_reference, trip.sudo().latest_completed_adjustment_id.id]
        amendment = trip.sudo().amendment_id
        snapshot['trip_amendment'] = [amendment.id, amendment.revision, amendment.state,
            amendment.source_digest, amendment.decided_by_id.id, str(amendment.decided_at)]
        encoded = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str)
        return {'source_snapshot': encoded, 'source_digest': hashlib.sha256(encoded.encode()).hexdigest()}

    def _no_active_adjustment(self):
        if self.sudo().adjustment_ids.filtered('active_trip_id'):
            raise ValidationError(_('Withdraw the unexecuted adjustment before replacing its correction sources.'))

    def action_refresh(self, reason, expected_revision):
        self._no_active_adjustment()
        return super().action_refresh(reason, expected_revision)

    def action_return_for_revision(self, reason, expected_revision):
        self._no_active_adjustment()
        return super().action_return_for_revision(reason, expected_revision)

    def _bindings_current(self):
        if self.sudo().adjustment_ids.filtered(lambda item: item.state != 'withdrawn'):
            raise ValidationError(_('Complete the financial adjustment instead of resolving it as unchanged sources.'))
        return super()._bindings_current()

    def action_create_adjustment(self, reason, expected_revision):
        self._lock()
        self._actor('owner')
        self._revision(expected_revision)
        adjustment = self.env['ps.te.adjustment'].create({'correction_id': self.id, 'reason': reason,
                                                         'expected_revision': expected_revision})
        return {'type': 'ir.actions.act_window', 'res_model': adjustment._name, 'res_id': adjustment.id, 'view_mode': 'form'}


class FinancialTripAmendment(models.Model):
    _inherit = 'ps.te.trip.amendment'

    state = fields.Selection(selection_add=[('withdrawn', 'Unapplied Amendment Withdrawn')],
                             ondelete={'withdrawn': 'set default'})
    applied_trip_revision = fields.Integer(readonly=True)
    financial_applied_by_id = fields.Many2one('res.users', readonly=True)
    withdrawal_reason = fields.Text(readonly=True)
    withdrawn_by_id = fields.Many2one('res.users', readonly=True)
    withdrawn_at = fields.Datetime(readonly=True)

    def _financial_decision_current(self):
        """Validate the recorded manager decision, not the finance user's role.

        Financial changes made through the linked held adjustment are re-bound
        separately; they do not alter the immutable manager trip-fact proposal.
        """
        self.ensure_one()
        amendment, trip = self.sudo(), self.sudo().trip_id
        manager = trip._current_approver()
        if (amendment.state not in ('finance', 'applied') or amendment.decided_by_id != amendment.manager_id
                or not amendment.decided_at or not amendment.decision_reason or manager != amendment.manager_id
                or manager != trip.approver_id or manager == trip.owner_id or not manager.active
                or trip.company_id not in manager.company_ids
                or not manager.has_group('ps_expenses.group_ps_te_trip_manager')
                or trip.amendment_id != amendment or trip.cancellation_status != 'none'):
            raise ValidationError(_('A current independent manager decision on these exact trip changes is required.'))
        if amendment.state == 'finance':
            original = json.loads(amendment.original_facts)
            keys = ('purpose', 'destination', 'start_date', 'end_date', 'preparing_revision',
                    'submitted_revision', 'state', 'approver_id', 'cancellation_status', 'case_status')
            valid = all(str(trip[key]) == original[key] for key in keys)
        else:
            valid = (trip.preparing_revision == amendment.applied_trip_revision and
                all(trip[key] == amendment[key] for key in ('purpose', 'destination', 'start_date', 'end_date')))
        if not valid:
            raise ValidationError(_('The approved amendment trip facts changed; obtain a fresh manager decision.'))

    def action_start_financial_adjustment(self, reason, expected_revision):
        self._lock()
        trip = self.trip_id
        trip._assert_current_membership()
        if type(expected_revision) is not int or expected_revision != self.revision:
            raise ValidationError(_('Stale amendment revision.'))
        if self.state != 'finance' or not self.active_trip_id:
            raise ValidationError(_('Start financial revalidation only after this amendment receives manager approval.'))
        self._financial_decision_current()
        reason = self.env['ps.te.trip.advance']._text(reason, _('Adjustment reason'))
        existing = self.env['ps.te.adjustment'].sudo().search([('amendment_id', '=', self.id), ('active_trip_id', '!=', False)])
        if existing:
            return {'type': 'ir.actions.act_window', 'res_model': existing._name, 'res_id': existing.id, 'view_mode': 'form'}
        with self.env.cr.savepoint():
            case = trip.correction_case_id
            if case and case.active_trip_id:
                if not case.sudo().adjustment_ids.filtered(lambda item: item.amendment_id == self):
                    raise ValidationError(_('Use the existing unrelated financial correction before this amendment.'))
            else:
                # Bounded private factory resolves ONLY this owner's manager-approved
                # amendment hold. Normal correction.create keeps its generic guard.
                model = self.env['ps.te.correction']
                model.browse().check_access('create')
                values = {'reference': 'COR-' + uuid.uuid4().hex.upper(), 'trip_id': trip.id,
                    'active_trip_id': trip.id, 'owner_id': trip.owner_id.id, 'company_id': trip.company_id.id,
                    'category': 'basis', 'description': reason, 'revision': 1, 'state': 'submitted',
                    **model._configuration(trip), **model._sources(trip)}
                safe = model.with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
                case = super(TripCorrection, safe).create(values)
                trip._bind_correction(case)
                case._event('opened', reason)
            adjustment = self.env['ps.te.adjustment'].create({'correction_id': case.id, 'reason': reason,
                                                            'expected_revision': case.revision})
            super(FinancialAdjustment, adjustment).write({'amendment_id': self.id})
            adjustment._event('manager_amendment_bound', self.reference)
        return {'type': 'ir.actions.act_window', 'res_model': adjustment._name, 'res_id': adjustment.id, 'view_mode': 'form'}

    def _apply_financial_amendment(self, adjustment):
        adjustment._actor('finance')
        amendment, trip = self.sudo(), self.sudo().trip_id
        if (adjustment.sudo().amendment_id != amendment or adjustment.trip_id != trip
                or adjustment.state != 'draft' or amendment.state != 'finance' or not amendment.active_trip_id):
            raise ValidationError(_('Amendment source mismatch.'))
        self._financial_decision_current()
        advance = trip.advance_id
        if (advance.payment_outcome == 'uncertain' or trip.settlement_id.cash_outcome == 'uncertain'
                or (advance and not advance.has_disbursement and advance.state != 'cancelled')):
            raise ValidationError(_('Reconcile or explicitly cancel unexecuted old funding before applying amended trip facts.'))
        revision = trip.preparing_revision + 1
        values = {key: amendment[key] for key in ('purpose', 'destination', 'start_date', 'end_date')}
        values.update(preparing_revision=revision, submitted_revision=revision,
            submission_intent=trip._intent_for_revision(revision), submission_receipt='PTR-RCPT-' + uuid.uuid4().hex.upper(),
            submitted_by_id=trip.owner_id.id, submitted_at=amendment.requested_at,
            decision_by_id=amendment.decided_by_id.id, decision_at=amendment.decided_at,
            decision_reason=_('Manager amendment %s applied after explicit finance review') % amendment.reference)
        values.update({'submitted_' + key: amendment[key] for key in ('purpose', 'destination', 'start_date', 'end_date')})
        super(PsTeTripRequest, trip).write(values)
        super(TripAmendment, amendment).write({'state': 'applied', 'active_trip_id': False,
            'applied_at': fields.Datetime.now(), 'applied_trip_revision': revision, 'financial_applied_by_id': self.env.uid})
        trip._record_event('financial_amendment_applied', values['decision_reason'])
        adjustment._renew_owned_sources(values['decision_reason'])
        adjustment._event('manager_amendment_applied', self.reference)
        return True

    def action_withdraw_unapplied(self, reason, expected_revision):
        self._lock()
        self.trip_id._assert_current_membership()
        if type(expected_revision) is not int or expected_revision != self.revision:
            raise ValidationError(_('Stale amendment revision.'))
        reason = self.env['ps.te.trip.advance']._text(reason, _('Amendment reason'))
        if self.state not in ('manager', 'finance') or not self.active_trip_id:
            raise ValidationError(_('Only an unapplied amendment may be withdrawn.'))
        if self.env['ps.te.adjustment'].sudo().search_count([('amendment_id', '=', self.id), ('active_trip_id', '!=', False)]):
            raise ValidationError(_('Withdraw the unexecuted linked adjustment before withdrawing its trip amendment.'))
        super(TripAmendment, self).write({'state': 'withdrawn', 'active_trip_id': False, 'withdrawal_reason': reason,
                       'withdrawn_by_id': self.env.uid, 'withdrawn_at': fields.Datetime.now()})
        return True

    def action_open_owner_operation(self):
        self.ensure_one()
        self.check_access('read')
        self.trip_id._assert_current_membership()
        return {'type': 'ir.actions.act_window', 'name': _('Trip Amendment'),
            'res_model': 'ps.te.amendment.wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_trip_id': self.trip_id.id, 'default_amendment_id': self.id,
                'default_expected_revision': self.revision, 'default_operation': 'financial' if self.state == 'finance' else 'withdraw'}}


class AdjustmentWizard(models.TransientModel):
    _name = 'ps.te.adjustment.wizard'
    _description = 'Financial Adjustment Operation'

    adjustment_id = fields.Many2one('ps.te.adjustment', required=True, readonly=True)
    expected_revision = fields.Integer(required=True, readonly=True)
    operation = fields.Selection([('copy', 'Copy Previous Claims for Fresh Review'),
        ('no_advance', 'Cancel Unexecuted Advance and Declare None'), ('no_funding', 'Confirm No Advance Funding'),
        ('propose', 'Propose Reviewed Adjustment Basis'), ('confirm', 'Confirm Cumulative External Cash'),
        ('authorize', 'Authorize Exact Adjustment Difference'), ('start', 'Prepare External Adjustment Cash'),
        ('record', 'Record External Adjustment Cash'), ('none', 'Confirm Adjustment Attempt Not Executed'),
        ('close', 'Close Fully Resolved Adjustment'), ('withdraw', 'Withdraw Unexecuted Adjustment')], required=True)
    currency_id = fields.Many2one(related='adjustment_id.currency_id')
    amount = fields.Monetary()
    external_reference = fields.Char()
    execution_date = fields.Date(default=fields.Date.context_today)
    reason = fields.Text(required=True)

    def action_apply(self):
        self.ensure_one()
        record, expected = self.adjustment_id, self.expected_revision
        if self.operation == 'copy':
            record.action_copy_previous_basis(self.reason, expected)
        elif self.operation == 'no_advance':
            record.action_declare_no_advance(self.reason, expected)
        elif self.operation == 'no_funding':
            record.action_confirm_no_funding(self.external_reference, self.reason, expected)
        elif self.operation == 'propose':
            record.action_propose_basis(self.reason, expected)
        elif self.operation == 'confirm':
            record.action_confirm_cash(self.external_reference, self.reason, expected)
        elif self.operation == 'authorize':
            record.action_authorize(self.reason, expected)
        elif self.operation == 'start':
            record.action_start_cash(self.external_reference, self.reason, expected)
        elif self.operation == 'record':
            record.action_record_cash(self.amount, self.external_reference, self.execution_date, expected)
        elif self.operation == 'none':
            record.action_confirm_not_executed(self.external_reference, self.reason, expected)
        elif self.operation == 'close':
            record.action_close(self.reason, expected)
        elif self.operation == 'withdraw':
            record.action_withdraw(self.reason, expected)
        else:
            raise ValidationError(_('Unsupported financial adjustment operation.'))
        return {'type': 'ir.actions.act_window_close'}
