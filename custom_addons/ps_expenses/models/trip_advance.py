from decimal import Decimal, InvalidOperation
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class PsTeTripAdvance(models.Model):
    _name = 'ps.te.trip.advance'
    _description = 'PS T&E Advance Request'
    _rec_name = 'reference'
    _order = 'id desc'

    _trip_unique = models.Constraint('UNIQUE(trip_id)', 'A trip may have only one advance record.')
    _cash_reference_unique = models.Constraint(
        'UNIQUE(company_id, cash_reference)', 'The external disbursement reference is already recorded in this company.',
    )

    reference = fields.Char(required=True, readonly=True, copy=False, index=True)
    trip_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True, ondelete='restrict', index=True)
    owner_id = fields.Many2one('res.users', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', required=True, readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Awaiting Finance Review'),
        ('approved', 'Approved — Not Disbursed'), ('refused', 'Refused'),
        ('cancelled', 'Cancelled — No Disbursement'),
        ('disbursed', 'External Disbursement Recorded'),
    ], required=True, default='draft', readonly=True, index=True)
    revision = fields.Integer(required=True, default=1, readonly=True)
    purpose = fields.Text(required=True, readonly=True)
    requested_amount = fields.Monetary(required=True, readonly=True)
    policy_reference = fields.Char(required=True, readonly=True)
    finance_reviewer_id = fields.Many2one('res.users', required=True, readonly=True, index=True)
    cash_operator_id = fields.Many2one('res.users', required=True, readonly=True, index=True)
    submitted_at = fields.Datetime(readonly=True)
    submission_receipt = fields.Char(readonly=True)
    approved_amount = fields.Monetary(readonly=True)
    approved_by_id = fields.Many2one('res.users', readonly=True)
    approved_at = fields.Datetime(readonly=True)
    has_approval = fields.Boolean(compute='_compute_known_amounts')
    decision_reason = fields.Text(readonly=True)
    disbursed_amount = fields.Monetary(readonly=True)
    disbursed_by_id = fields.Many2one('res.users', readonly=True)
    disbursed_at = fields.Datetime(readonly=True)
    disbursement_date = fields.Date(readonly=True)
    cash_reference = fields.Char(readonly=True, index=True)
    has_disbursement = fields.Boolean(compute='_compute_known_amounts')
    payment_outcome = fields.Selection([
        ('not_started', 'No Execution Recorded'), ('uncertain', 'Execution Outcome Unconfirmed'),
        ('not_executed', 'Confirmed Not Executed'), ('recorded', 'Disbursement Recorded'),
    ], default='not_started', required=True, readonly=True)
    payment_attempt_reference = fields.Char(readonly=True)
    no_payment_reference = fields.Char(readonly=True)
    cash_event_id = fields.Many2one('ps.te.cash.event', readonly=True, ondelete='restrict')
    event_ids = fields.One2many('ps.te.advance.event', 'advance_id', readonly=True)
    finance_assignment_valid = fields.Boolean(compute='_compute_assignment_validity', store=True)
    cash_assignment_valid = fields.Boolean(compute='_compute_assignment_validity', store=True)

    @api.depends('approved_by_id', 'disbursed_by_id')
    def _compute_known_amounts(self):
        for advance in self:
            advance.has_approval = bool(advance.approved_by_id)
            advance.has_disbursement = bool(advance.disbursed_by_id)

    @api.depends(
        'finance_reviewer_id', 'cash_operator_id',
        'company_id.ps_te_finance_reviewer_id', 'company_id.ps_te_cash_operator_id',
    )
    def _compute_assignment_validity(self):
        for advance in self:
            advance.finance_assignment_valid = advance.finance_reviewer_id == advance.company_id.ps_te_finance_reviewer_id
            advance.cash_assignment_valid = advance.cash_operator_id == advance.company_id.ps_te_cash_operator_id

    @api.model
    def _amount(self, value):
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError(_('Enter a positive whole-VND amount.'))
        if (
            not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value()
            or amount > Decimal('999999999999')
        ):
            raise ValidationError(_('Enter a positive whole-VND amount up to 999,999,999,999.'))
        return float(amount)

    @api.model
    def _text(self, value, label):
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(_('%s is required.') % label)
        return value.strip()

    @api.model
    def _configuration(self, trip):
        company = trip.company_id.sudo()
        finance = company.ps_te_finance_reviewer_id
        cash = company.ps_te_cash_operator_id
        policy = self._text(company.ps_te_advance_policy_reference, _('Advance policy reference'))
        if not company.currency_id.active or company.currency_id.name != 'VND' or company.currency_id.rounding != 1:
            raise ValidationError(_('This release supports company currency VND with whole-unit rounding only.'))
        if not finance or not cash or finance == cash or trip.owner_id in (finance, cash):
            raise ValidationError(_('Configure distinct finance and cash officers other than the requester.'))
        for user, group in (
            (finance, 'ps_expenses.group_ps_te_finance'),
            (cash, 'ps_expenses.group_ps_te_cash'),
        ):
            if not user.active or company not in user.company_ids or not user.has_group(group):
                raise ValidationError(_('Advance officers must be active authorized company members.'))
        return {
            'policy_reference': policy, 'finance_reviewer_id': finance.id,
            'cash_operator_id': cash.id, 'currency_id': company.currency_id.id,
        }

    @api.model_create_multi
    def create(self, vals_list):
        self.browse().check_access('create')
        prepared = []
        # Prevalidate every input before any record is created (mixed batch atomicity).
        for source in vals_list:
            if set(source) - {'trip_id', 'requested_amount', 'purpose'}:
                raise AccessError(_('Advance workflow fields are server controlled.'))
            trip = self.env['ps.te.trip.request'].browse(source.get('trip_id')).exists()
            if len(trip) != 1:
                raise ValidationError(_('Select one approved trip.'))
            trip.check_access('read')
            trip._assert_current_membership()
            prepared.append((trip, self._amount(source.get('requested_amount')), self._text(source.get('purpose'), _('Advance purpose'))))
        trips = self.env['ps.te.trip.request'].browse(sorted({item[0].id for item in prepared}))
        trips.lock_for_update()
        trips.invalidate_recordset()
        result_vals = []
        for trip, amount, purpose in prepared:
            trip._assert_current_membership()
            trip._assert_travel_open()
            if trip.state != 'approved' or trip.case_status != 'open' or trip.funding_lock_settlement_id:
                raise ValidationError(_('Business approval is required before requesting an advance.'))
            if trip.advance_id:
                raise ValidationError(_('This trip already has an advance record. Open the existing record.'))
            result_vals.append({
                'trip_id': trip.id, 'owner_id': trip.owner_id.id, 'company_id': trip.company_id.id,
                'reference': 'ADV-' + uuid.uuid4().hex.upper(), 'revision': 1,
                'requested_amount': amount, 'purpose': purpose, 'state': 'draft',
                **self._configuration(trip),
            })
        safe = self.with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
        records = super(PsTeTripAdvance, safe).create(result_vals)
        for advance in records:
            advance.trip_id._set_advance_choice('requested', advance)
            advance._event('created', _('Advance draft created'))
        return records

    def write(self, vals):
        raise AccessError(_('Use advance workflow actions; direct field changes are not permitted.'))

    def unlink(self):
        raise AccessError(_('Advance records must be retained.'))

    def copy(self, default=None):
        raise AccessError(_('Advance records cannot be copied.'))

    def _lock(self):
        self.ensure_one()
        self.check_access('write')
        self.trip_id.lock_for_update()
        self.lock_for_update()
        self.trip_id.invalidate_recordset()
        self.invalidate_recordset()
        if self.trip_id.funding_lock_settlement_id and not self.has_disbursement:
            raise ValidationError(_('This funding basis is locked by settlement.'))

    def _assert_actor(self, role):
        self.ensure_one()
        trip = self.trip_id
        user = self.env.user
        if (
            not user.active or self.company_id not in user.company_ids
            or self.company_id not in self.env.companies
            or not trip.employee_id.sudo().active or not trip.employee_mapping_valid
        ):
            raise AccessError(_('Advance access is not permitted.'))
        if role == 'owner':
            trip._assert_current_membership()
            return
        assigned = self.finance_reviewer_id if role == 'finance' else self.cash_operator_id
        valid = self.finance_assignment_valid if role == 'finance' else self.cash_assignment_valid
        if (
            role not in ('finance', 'cash') or user != assigned or not valid or user == self.owner_id
            or not user.has_group('ps_expenses.group_ps_te_' + role)
        ):
            raise AccessError(_('Only the currently assigned advance officer may perform this action.'))
        if role == 'cash' and (user == self.finance_reviewer_id or user == self.approved_by_id):
            raise AccessError(_('The approving officer cannot confirm their own disbursement.'))

    def _assert_revision(self, revision):
        if type(revision) is not int or revision != self.revision:
            raise ValidationError(_('Stale or invalid advance revision. Reload the advance.'))

    def _assert_policy(self):
        current_config = self._configuration(self.trip_id)
        if current_config['policy_reference'] != self.policy_reference:
            raise ValidationError(_('The policy changed. Withdraw and resubmit for fresh review.'))
        if not self.finance_assignment_valid or not self.cash_assignment_valid:
            raise ValidationError(_('The assigned officers changed. Withdraw and resubmit for fresh review.'))
        if self.trip_id.state != 'approved' or self.company_id.currency_id != self.currency_id or not self.currency_id.active or self.currency_id.rounding != 1:
            raise ValidationError(_('The approved trip or VND currency binding is no longer valid.'))

    def _event(self, event_type, reason, revision=None):
        return self.env['ps.te.advance.event'].sudo()._append({
            'advance_id': self.id, 'actor_id': self.env.uid, 'occurred_at': fields.Datetime.now(),
            'event_type': event_type, 'revision': self.revision if revision is None else revision, 'reason': reason,
            'purpose': self.purpose,
            'requested_amount': self.requested_amount, 'approved_amount': self.approved_amount,
            'has_approval': bool(self.approved_by_id), 'disbursed_amount': self.disbursed_amount,
            'has_disbursement': bool(self.disbursed_by_id), 'cash_reference': self.cash_reference,
            'policy_reference': self.policy_reference,
            'payment_outcome': self.payment_outcome, 'attempt_reference': self.payment_attempt_reference,
            'no_payment_reference': self.no_payment_reference,
        })

    def action_edit(self, amount, purpose, expected_revision):
        self._lock()
        self.trip_id._assert_travel_open()
        self._assert_actor('owner')
        self._assert_revision(expected_revision)
        if self.state != 'draft' or self.has_disbursement:
            raise ValidationError(_('Only an unexecuted draft advance may be edited.'))
        super().write({
            'requested_amount': self._amount(amount), 'purpose': self._text(purpose, _('Advance purpose')),
            'revision': self.revision + 1,
        })
        self._event('edited', _('Advance draft revised'))
        return True

    def action_submit(self, expected_revision):
        self._lock()
        self.trip_id._assert_travel_open()
        self._assert_actor('owner')
        self._assert_revision(expected_revision)
        if self.state in ('submitted', 'approved', 'disbursed') and self.submission_receipt:
            return True
        if self.state != 'draft' or self.has_disbursement:
            raise ValidationError(_('Only an unexecuted draft may be submitted.'))
        config = self._configuration(self.trip_id)
        super().write({
            **config, 'state': 'submitted', 'submitted_at': fields.Datetime.now(),
            'submission_receipt': 'ADV-RCPT-' + uuid.uuid4().hex.upper(),
        })
        self._event('submitted', _('Advance submitted for finance review'))
        return True

    def action_review(self, decision, reason, expected_revision, approved_amount=None):
        self._lock()
        self.trip_id._assert_travel_open()
        self._assert_actor('finance')
        self._assert_revision(expected_revision)
        if decision not in ('approved', 'refused', 'returned'):
            raise ValidationError(_('Unsupported advance decision.'))
        reason = self._text(reason, _('Decision reason'))
        amount = self._amount(approved_amount) if decision == 'approved' else 0
        if amount > self.requested_amount:
            raise ValidationError(_('Approved amount cannot exceed the requested amount.'))
        if self.state != 'submitted':
            if self.state == decision and self.decision_reason == reason and (decision != 'approved' or self.approved_amount == amount):
                return True
            raise ValidationError(_('Only the exact submitted revision may be decided.'))
        vals = {'state': 'draft' if decision == 'returned' else decision, 'decision_reason': reason}
        if decision == 'approved':
            self._assert_policy()
            vals.update(approved_amount=amount, approved_by_id=self.env.uid, approved_at=fields.Datetime.now())
        if decision == 'returned':
            vals.update(revision=self.revision + 1, submission_receipt=False)
        super().write(vals)
        self._event(decision, reason, revision=expected_revision)
        return True

    def action_cancel(self, reason, expected_revision):
        self._lock()
        self._assert_actor('owner')
        self.trip_id._assert_no_active_correction()
        self._assert_revision(expected_revision)
        reason = self._text(reason, _('Cancellation reason'))
        if self.has_disbursement or self.state == 'disbursed' or self.payment_outcome == 'uncertain':
            raise ValidationError(_('Recorded disbursement cannot be cancelled; resolve it through settlement.'))
        if self.state == 'cancelled':
            if self.decision_reason != reason:
                raise ValidationError(_('The advance was already cancelled with a different reason.'))
            return True
        super().write({'state': 'cancelled', 'decision_reason': reason})
        self._event('cancelled', reason)
        return True

    def action_revise(self, reason, expected_revision):
        self._lock()
        self.trip_id._assert_travel_open()
        self._assert_actor('owner')
        self._assert_revision(expected_revision)
        reason = self._text(reason, _('Revision reason'))
        if self.has_disbursement or self.payment_outcome == 'uncertain' or self.state not in ('submitted', 'approved', 'refused', 'cancelled'):
            raise ValidationError(_('Only an unexecuted submitted/decided advance may be revised.'))
        super().write({
            'state': 'draft', 'revision': self.revision + 1, 'approved_by_id': False,
            'approved_at': False, 'approved_amount': 0, 'submission_receipt': False,
            'decision_reason': False,
        })
        self.trip_id._set_advance_choice('requested', self)
        self._event('revised', reason)
        return True

    def action_record_disbursement(self, amount, reference, execution_date, expected_revision):
        self._lock()
        self._assert_actor('cash')
        self._assert_revision(expected_revision)
        amount = self._amount(amount)
        reference = self._text(reference, _('External payment reference'))
        try:
            execution_date = fields.Date.to_date(execution_date)
        except (ValueError, TypeError):
            raise ValidationError(_('A valid external payment date is required.'))
        if not execution_date:
            raise ValidationError(_('A valid external payment date is required.'))
        if self.state == 'disbursed':
            if (self.disbursed_amount, self.cash_reference, self.disbursement_date) == (amount, reference, execution_date):
                return True
            raise ValidationError(_('A different disbursement is already recorded. Do not retry as a new payment.'))
        self._assert_policy()
        if self.state != 'approved' or not self.approved_by_id or amount != self.approved_amount:
            raise ValidationError(_('Record only the exact approved amount of an approved advance.'))
        if self.payment_outcome != 'uncertain':
            raise ValidationError(_('Prepare the external cash operation before recording or reconciling it.'))
        approval_date = fields.Datetime.context_timestamp(self, self.approved_at).date()
        if execution_date < approval_date or execution_date > fields.Date.context_today(self):
            raise ValidationError(_('Payment date must be between approval date and today.'))
        if self.sudo().search_count([
            ('company_id', '=', self.company_id.id), ('cash_reference', '=', reference), ('id', '!=', self.id),
        ]):
            raise ValidationError(_('This external disbursement reference is already recorded in the company.'))
        event = self.env['ps.te.cash.event']._record_movement(self, 'advance', amount, reference, execution_date)
        super().write({
            'state': 'disbursed', 'disbursed_amount': amount, 'cash_reference': reference,
            'disbursement_date': execution_date, 'disbursed_by_id': self.env.uid,
            'disbursed_at': fields.Datetime.now(),
            'payment_outcome': 'recorded', 'cash_event_id': event.id,
        })
        self._event('disbursed', _('External disbursement recorded with a source reference'))
        return True

    def action_start_disbursement(self, attempt_reference, reason, expected_revision):
        self._lock()
        self.trip_id._assert_travel_open()
        self._assert_actor('cash')
        self._assert_revision(expected_revision)
        self._assert_policy()
        attempt_reference = self._text(attempt_reference, _('Execution attempt reference'))
        reason = self._text(reason, _('Execution preparation reason'))
        if self.state != 'approved' or self.has_disbursement:
            raise ValidationError(_('Prepare only an approved, unexecuted advance.'))
        if self.payment_outcome == 'uncertain':
            if self.payment_attempt_reference == attempt_reference:
                return True
            raise ValidationError(_('Reconcile the uncertain attempt before preparing another one.'))
        super().write({'payment_outcome': 'uncertain', 'payment_attempt_reference': attempt_reference})
        self._event('cash_started', reason)
        return True

    def action_confirm_no_payment(self, reference, reason, expected_revision):
        self._lock()
        self._assert_actor('cash')
        self._assert_revision(expected_revision)
        reference = self._text(reference, _('Reconciliation reference'))
        reason = self._text(reason, _('No-payment confirmation reason'))
        if self.state != 'approved' or self.has_disbursement:
            raise ValidationError(_('A recorded disbursement cannot be reclassified as no payment.'))
        if self.payment_outcome == 'not_executed' and self.no_payment_reference == reference:
            return True
        if self.payment_outcome != 'uncertain':
            raise ValidationError(_('Reconcile the prepared uncertain operation first.'))
        super().write({'payment_outcome': 'not_executed', 'no_payment_reference': reference})
        self._event('cash_not_executed', reason)
        return True

    def _ensure_cash_event(self):
        self.ensure_one()
        if not self.has_disbursement or self.state != 'disbursed':
            raise ValidationError(_('There is no recorded advance funding basis.'))
        if not self.cash_event_id:
            event = self.env['ps.te.cash.event']._record_movement(
                self, 'advance', self.disbursed_amount, self.cash_reference, self.disbursement_date,
                actor_id=self.disbursed_by_id.id, recorded_at=self.disbursed_at,
            )
            super().write({'cash_event_id': event.id, 'payment_outcome': 'recorded'})
        return self.cash_event_id

    def action_open_operation(self):
        self.ensure_one()
        self.check_access('read')
        return {
            'type': 'ir.actions.act_window', 'name': _('Advance Operation'),
            'res_model': 'ps.te.advance.wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_advance_id': self.id, 'default_trip_id': self.trip_id.id,
                        'default_expected_revision': self.revision, 'default_amount': self.requested_amount,
                        'default_purpose': self.purpose},
        }


class PsTeAdvanceEvent(models.Model):
    _name = 'ps.te.advance.event'
    _description = 'PS T&E Advance History'
    _order = 'id desc'

    advance_id = fields.Many2one('ps.te.trip.advance', required=True, readonly=True, ondelete='restrict', index=True)
    actor_id = fields.Many2one('res.users', required=True, readonly=True)
    occurred_at = fields.Datetime(required=True, readonly=True)
    event_type = fields.Selection([(key, key.title()) for key in (
        'created', 'edited', 'submitted', 'approved', 'refused', 'returned',
        'cancelled', 'revised', 'disbursed',
        'cash_started', 'cash_not_executed',
    )], required=True, readonly=True)
    revision = fields.Integer(required=True, readonly=True)
    reason = fields.Text(readonly=True)
    purpose = fields.Text(readonly=True)
    currency_id = fields.Many2one(related='advance_id.currency_id', readonly=True)
    requested_amount = fields.Monetary(readonly=True)
    approved_amount = fields.Monetary(readonly=True)
    has_approval = fields.Boolean(readonly=True)
    disbursed_amount = fields.Monetary(readonly=True)
    has_disbursement = fields.Boolean(readonly=True)
    cash_reference = fields.Char(readonly=True)
    policy_reference = fields.Char(readonly=True)
    payment_outcome = fields.Char(readonly=True)
    attempt_reference = fields.Char(readonly=True)
    no_payment_reference = fields.Char(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Advance history is created only by workflow actions.'))

    @api.model
    def _append(self, vals):
        return super().create(vals)

    def write(self, vals):
        raise AccessError(_('Advance history cannot be changed.'))

    def unlink(self):
        raise AccessError(_('Advance history cannot be deleted.'))
