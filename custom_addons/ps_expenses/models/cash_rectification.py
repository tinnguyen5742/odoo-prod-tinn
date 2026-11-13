"""Đính chính dữ kiện thu chi: không sinh giao dịch trả/hoàn tiền giả.

Linked correction assertions retain original cash facts and keep the financial
case held until the complete adjustment workflow explicitly resolves it.
"""
import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class CashReferenceClaim(models.Model):
    _name = 'ps.te.cash.reference.claim'
    _description = 'PS T&E Reserved External Cash Reference'
    _unique_reference = models.Constraint('UNIQUE(company_id, reference)', 'This external reference belongs to another cash fact.')

    company_id = fields.Many2one('res.company', required=True, readonly=True)
    reference = fields.Char(required=True, readonly=True)
    root_event_id = fields.Many2one('ps.te.cash.event', required=True, readonly=True, ondelete='restrict')

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Cash references are reserved only by verified workflow facts.'))

    @api.model
    def _claim(self, root, reference):
        root.ensure_one()
        # Serialize lookup + reservation across all workflows in this company.
        # Different trip locks alone cannot protect a shared external reference.
        root.company_id.lock_for_update()
        reference = self.env['ps.te.trip.advance']._text(reference, _('External cash reference'))
        existing = self.sudo().search([('company_id', '=', root.company_id.id), ('reference', '=', reference)], limit=1)
        # Existing/legacy real movement references are reserved too, even if a
        # historic row predates this alias registry. Never silently reassign one.
        old = self.env['ps.te.cash.event'].sudo().search([
            ('company_id', '=', root.company_id.id), ('external_reference', '=', reference)])
        if (old and old != root) or (existing and existing.root_event_id != root):
            raise ValidationError(_('This external reference belongs to another cash fact.'))
        legacy = self.env['ps.te.trip.advance'].sudo().search([
            ('company_id', '=', root.company_id.id), ('cash_reference', '=', reference)])
        if legacy and (not root.advance_id or legacy != root.advance_id):
            raise ValidationError(_('This external reference belongs to another cash fact.'))
        if existing:
            return existing
        safe = self.sudo().with_context({k: v for k, v in self.env.context.items() if not k.startswith('default_')})
        return super(CashReferenceClaim, safe).create({'company_id': root.company_id.id,
                                                     'reference': reference, 'root_event_id': root.id})

    def write(self, vals):
        raise AccessError(_('Reserved cash references cannot be reassigned.'))

    def unlink(self):
        raise AccessError(_('Reserved cash references must be retained.'))


class CashRectification(models.Model):
    _name = 'ps.te.cash.rectification'
    _description = 'PS T&E Linked Cash Fact Rectification'
    _rec_name = 'reference'
    _order = 'id desc'
    _one_successor = models.Constraint('UNIQUE(active_predecessor_key)', 'A cash fact already has a pending or verified successor.')

    reference = fields.Char(required=True, readonly=True)
    correction_id = fields.Many2one('ps.te.correction', required=True, readonly=True, ondelete='restrict')
    root_event_id = fields.Many2one('ps.te.cash.event', required=True, readonly=True, ondelete='restrict')
    previous_id = fields.Many2one('ps.te.cash.rectification', readonly=True, ondelete='restrict')
    active_predecessor_key = fields.Char(readonly=True)
    trip_id = fields.Many2one(related='root_event_id.trip_id', store=True)
    owner_id = fields.Many2one(related='root_event_id.owner_id', store=True)
    company_id = fields.Many2one(related='root_event_id.company_id', store=True)
    currency_id = fields.Many2one(related='root_event_id.currency_id')
    proposed_amount = fields.Monetary(required=True, readonly=True)
    proposed_reference = fields.Char(required=True, readonly=True)
    proposed_date = fields.Date(required=True, readonly=True)
    reason = fields.Text(required=True, readonly=True)
    source_digest = fields.Char(required=True, readonly=True)
    state = fields.Selection([('finance', 'Awaiting Rectification Review'), ('cash', 'Awaiting External Fact Verification'),
                             ('verified', 'Cash Fact Rectification Verified'), ('refused', 'Rectification Refused')],
                            default='finance', required=True, readonly=True)
    approved_by_id = fields.Many2one('res.users', readonly=True)
    approved_at = fields.Datetime(readonly=True)
    approval_reason = fields.Text(readonly=True)
    verification_reference = fields.Char(readonly=True)
    verified_by_id = fields.Many2one('res.users', readonly=True)
    verified_at = fields.Datetime(readonly=True)

    @api.model
    def _corrected_amount(self, value):
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError(_('Enter a nonnegative whole-VND corrected cash amount.'))
        if (type(value) is bool or not amount.is_finite() or amount < 0
                or amount != amount.to_integral_value() or amount > Decimal('99999999999900')):
            raise ValidationError(_('Enter a nonnegative whole-VND corrected cash amount.'))
        return float(amount)

    @api.model
    def _effective(self, root):
        root.ensure_one()
        candidates = self.sudo().search([('root_event_id', '=', root.id), ('state', '=', 'verified')], order='id desc', limit=1)
        return candidates

    @api.model
    def _fingerprint(self, case, root, previous):
        data = {'case': [case.id, case.source_digest, case.finance_reviewer_id.id, case.cash_operator_id.id],
                'root': [root.id, root.amount, root.external_reference, str(root.execution_date), root.kind],
                'previous': [previous.id, previous.proposed_amount, previous.proposed_reference,
                             str(previous.proposed_date), previous.state] if previous else None}
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    @api.model_create_multi
    def create(self, vals_list):
        self.browse().check_access('create')
        allowed = {'correction_id', 'root_event_id', 'amount', 'reference', 'date', 'reason', 'expected_revision'}
        if any(set(v) != allowed for v in vals_list):
            raise AccessError(_('Cash rectification facts and decisions are server controlled.'))
        cases = self.env['ps.te.correction'].browse(sorted({v['correction_id'] for v in vals_list})).exists()
        cases.check_access('read')
        for case in cases:
            case._actor('owner')
        self.env['ps.te.trip.request'].browse(sorted(cases.mapped('trip_id').ids)).lock_for_update()
        prepared = []
        for vals in vals_list:
            if set(vals) != allowed:
                raise AccessError(_('Cash rectification facts and decisions are server controlled.'))
            case = self.env['ps.te.correction'].browse(vals['correction_id']).exists()
            if len(case) != 1:
                raise ValidationError(_('Select the exact active financial correction case.'))
            case._lock()
            case._actor('owner')
            case._revision(vals['expected_revision'])
            case._check_snapshot()
            if not case.active_trip_id or (case.category != 'funding' and not case.sudo().adjustment_ids.filtered('active_trip_id')):
                raise ValidationError(_('Use an active funding correction for cash fact rectification.'))
            root = self.env['ps.te.cash.event'].browse(vals['root_event_id']).exists()
            if len(root) != 1 or root.trip_id != case.trip_id or root.company_id != case.company_id:
                raise ValidationError(_('Cash rectification source mismatch.'))
            root.check_access('read')
            root.lock_for_update()
            previous = self._effective(root)
            amount = self._corrected_amount(vals['amount'])
            reference = self.env['ps.te.trip.advance']._text(vals['reference'], _('External cash reference'))
            reason = self.env['ps.te.trip.advance']._text(vals['reason'], _('Rectification reason'))
            try:
                date = fields.Date.to_date(vals['date'])
            except (ValueError, TypeError):
                raise ValidationError(_('Use a known execution date, not a future date.'))
            if not date or date > fields.Date.today():
                raise ValidationError(_('Use a known execution date, not a future date.'))
            current = (previous.proposed_amount, previous.proposed_reference, previous.proposed_date) if previous else (
                root.amount, root.external_reference, root.execution_date)
            if (amount, reference, date) == current:
                raise ValidationError(_('A rectification must identify changed cash facts.'))
            prepared.append({'reference': 'RCF-' + uuid.uuid4().hex.upper(), 'correction_id': case.id,
                'root_event_id': root.id, 'previous_id': previous.id or False,
                'active_predecessor_key': ('rect:' + str(previous.id)) if previous else ('cash:' + str(root.id)),
                'proposed_amount': amount, 'proposed_reference': reference, 'proposed_date': date,
                'reason': reason, 'source_digest': self._fingerprint(case, root, previous), 'state': 'finance'})
        safe = self.with_context({k: v for k, v in self.env.context.items() if not k.startswith('default_')})
        return super(CashRectification, safe).create(prepared)

    def write(self, vals):
        raise AccessError(_('Cash rectification proposals and verified assertions are immutable.'))

    def unlink(self):
        raise AccessError(_('Linked cash rectifications must be retained.'))

    def _lock_and_check(self, role):
        self.ensure_one()
        self.check_access('write')
        case = self.correction_id
        case._lock()
        case._actor(role)
        if not case.active_trip_id:
            raise ValidationError(_('The financial correction must remain active until full resolution.'))
        case._check_snapshot()
        self.root_event_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()
        if self.source_digest != self._fingerprint(case, self.root_event_id, self.previous_id):
            raise ValidationError(_('Cash rectification source or officer bindings changed; renew review.'))
        if self._effective(self.root_event_id) != self.previous_id and self.state != 'verified':
            raise ValidationError(_('A newer verified cash assertion already supersedes this proposal.'))
        trip = case.sudo().trip_id
        if trip.advance_id.payment_outcome == 'uncertain' or trip.settlement_id.cash_outcome == 'uncertain':
            raise ValidationError(_('Reconcile uncertain execution before rectifying cash facts.'))
        return case

    def action_review(self, decision, reason):
        case = self._lock_and_check('finance')
        reason = self.env['ps.te.trip.advance']._text(reason, _('Review reason'))
        if self.state != 'finance' or decision not in ('approved', 'refused'):
            raise ValidationError(_('This rectification proposal is not awaiting a finance decision.'))
        values = {'approved_by_id': self.env.uid, 'approved_at': fields.Datetime.now(), 'approval_reason': reason}
        if decision == 'refused':
            values.update(state='refused', active_predecessor_key=False)
        else:
            values.update(state='cash')
        super().write(values)
        case._event('cash_fact_' + decision, self.reference + ': ' + reason)
        return True

    def action_verify(self, evidence_reference, reason):
        case = self._lock_and_check('cash')
        reference = self.env['ps.te.trip.advance']._text(evidence_reference, _('Reconciliation reference'))
        reason = self.env['ps.te.trip.advance']._text(reason, _('Review reason'))
        if self.state == 'verified' and self.verification_reference == reference and self.verified_by_id == self.env.user:
            return True
        if self.state != 'cash' or self.approved_by_id != case.finance_reviewer_id or self.approved_by_id == self.env.user:
            raise ValidationError(_('Current finance must approve the exact cash facts before independent verification.'))
        self.env['ps.te.cash.reference.claim']._claim(self.root_event_id, self.root_event_id.external_reference)
        self.env['ps.te.cash.reference.claim']._claim(self.root_event_id, self.proposed_reference)
        super().write({'state': 'verified', 'verification_reference': reference,
                       'verified_by_id': self.env.uid, 'verified_at': fields.Datetime.now()})
        case._event('cash_fact_verified', self.reference + ': ' + reason)
        return True

    def action_invalidate_pending(self, reason):
        self.ensure_one()
        self.check_access('write')
        case = self.correction_id
        case._lock()
        case._actor('owner')
        self.root_event_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()
        reason = self.env['ps.te.trip.advance']._text(reason, _('Rectification reason'))
        if self.state not in ('finance', 'cash'):
            raise ValidationError(_('Verified cash facts cannot be withdrawn or invalidated.'))
        # The original fact remains effective and the financial case remains
        # held. Only an unverified proposal's unique successor slot is released.
        super().write({'state': 'refused', 'active_predecessor_key': False})
        case._event('cash_fact_proposal_withdrawn', self.reference + ': ' + reason)
        return True


class CashEventReferenceReservation(models.Model):
    _inherit = 'ps.te.cash.event'

    @api.model
    def _record_movement(self, source, kind, amount, reference, date, actor_id=None, recorded_at=None):
        with self.env.cr.savepoint():
            event = super()._record_movement(source, kind, amount, reference, date, actor_id, recorded_at)
            self.env['ps.te.cash.reference.claim']._claim(event, reference)
        return event

    @api.model
    def _verified_net(self, trip, exclude_adjustment=None):
        """Private snapshot, not a cash authorization or an inference of zero.

        Caller must authorize/lock the linked adjustment first. Only immutable
        actual movement roots contribute; a verified rectification substitutes
        its root's data, never adds a second payment. All earlier settlement
        top-ups/returns remain in the sum. Pending assertions/uncertain attempts
        keep `amount=None`, even when some historical facts are known.
        """
        trip.ensure_one()
        trip = trip.sudo()
        advance, settlement = trip.advance_id, trip.settlement_id
        all_adjustments = self.env['ps.te.adjustment'].sudo().search([('trip_id', '=', trip.id)])
        reasons = []
        if advance.payment_outcome == 'uncertain' or settlement.cash_outcome == 'uncertain':
            reasons.append('uncertain_execution')
        roots = self.sudo().search([('trip_id', '=', trip.id)], order='id')
        adjustments = all_adjustments
        if exclude_adjustment:
            adjustments -= exclude_adjustment.sudo()
            roots = roots.filtered(lambda root: root.adjustment_id != exclude_adjustment)
        if adjustments.filtered(lambda item: item.cash_outcome == 'uncertain'):
            reasons.append('uncertain_adjustment_execution')
        if advance.has_disbursement:
            if not advance.cash_event_id or advance.cash_event_id not in roots:
                reasons.append('missing_advance_cash_fact')
        elif not (((settlement.funding_known and settlement.funding_kind == 'none'
                    and settlement.funding_reference and settlement.funding_confirmed_by_id)
                   or all_adjustments.filtered(lambda item: item.no_funding_reference and item.no_funding_confirmed_by_id))
                  and trip.advance_choice == 'not_requested'
                  and (not advance or advance.state == 'cancelled')):
            reasons.append('funding_not_confirmed')
        if settlement.cash_outcome == 'recorded' and (not settlement.cash_event_id or settlement.cash_event_id not in roots):
            reasons.append('missing_settlement_cash_fact')
        corrections = self.env['ps.te.cash.rectification'].sudo()
        pending = corrections.search([('root_event_id', 'in', roots.ids), ('state', 'in', ('finance', 'cash'))])
        if pending:
            reasons.append('unverified_rectification')
        total = Decimal(0)
        leaves = []
        for root in roots:
            leaf = corrections._effective(root)
            amount = leaf.proposed_amount if leaf else root.amount
            reference = leaf.proposed_reference if leaf else root.external_reference
            date = leaf.proposed_date if leaf else root.execution_date
            if root.company_id != trip.company_id or root.currency_id != trip.company_id.currency_id:
                reasons.append('cash_fact_company_currency_mismatch')
            sign = -1 if root.kind == 'return' else 1
            if root.kind not in ('advance', 'topup', 'return'):
                reasons.append('unknown_movement_kind')
            total += sign * Decimal(str(amount))
            leaves.append({'root_id': root.id, 'assertion_id': leaf.id or None, 'kind': root.kind,
                           'amount': amount, 'reference': reference, 'date': str(date)})
        snapshot = {'known': not reasons, 'amount': float(total) if not reasons else None,
                    'verified_net': float(total), 'holds': sorted(set(reasons)), 'leaves': leaves}
        snapshot['digest'] = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
        return snapshot


class CorrectionRectificationHold(models.Model):
    _inherit = 'ps.te.correction'

    rectification_ids = fields.One2many('ps.te.cash.rectification', 'correction_id', readonly=True)

    def _bindings_current(self):
        if self.sudo().rectification_ids.filtered(lambda r: r.state != 'refused'):
            raise ValidationError(_('Cash fact rectifications require full financial adjustment, not no-change investigation.'))
        return super()._bindings_current()

    def action_open_cash_rectification(self):
        self.ensure_one()
        self.check_access('read')
        self._actor('owner')
        return {'type': 'ir.actions.act_window', 'name': _('Cash Fact Rectification'),
                'res_model': 'ps.te.cash.rectification.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_correction_id': self.id, 'default_trip_id': self.trip_id.id,
                            'default_expected_revision': self.revision}}


class CashRectificationOperations(models.Model):
    _inherit = 'ps.te.cash.rectification'

    def action_open_operation(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Cash Fact Rectification'),
                'res_model': 'ps.te.cash.rectification.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_correction_id': self.correction_id.id, 'default_trip_id': self.trip_id.id,
                            'default_rectification_id': self.id, 'default_expected_revision': self.correction_id.revision}}


class CashRectificationWizard(models.TransientModel):
    _name = 'ps.te.cash.rectification.wizard'
    _description = 'Cash Fact Rectification'

    correction_id = fields.Many2one('ps.te.correction', required=True, readonly=True)
    trip_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True)
    rectification_id = fields.Many2one('ps.te.cash.rectification', readonly=True)
    expected_revision = fields.Integer(required=True, readonly=True)
    root_event_id = fields.Many2one('ps.te.cash.event')
    currency_id = fields.Many2one(related='trip_id.company_id.currency_id')
    amount = fields.Monetary()
    external_reference = fields.Char()
    execution_date = fields.Date(default=fields.Date.context_today)
    reason = fields.Text(required=True)
    operation = fields.Selection([('approved', 'Approve'), ('refused', 'Refuse'),
                                  ('verify', 'Verify External Cash Facts'), ('withdraw', 'Withdraw Unverified Proposal')])

    def action_apply(self):
        self.ensure_one()
        if self.correction_id.trip_id != self.trip_id:
            raise ValidationError(_('Cash rectification source mismatch.'))
        if not self.rectification_id:
            record = self.env['ps.te.cash.rectification'].create({'correction_id': self.correction_id.id,
                'root_event_id': self.root_event_id.id, 'amount': self.amount, 'reference': self.external_reference,
                'date': self.execution_date, 'reason': self.reason, 'expected_revision': self.expected_revision})
            return {'type': 'ir.actions.act_window', 'res_model': record._name, 'res_id': record.id, 'view_mode': 'form'}
        record = self.rectification_id
        if record.correction_id != self.correction_id or self.correction_id.revision != self.expected_revision:
            raise ValidationError(_('Cash rectification source mismatch.'))
        if self.operation in ('approved', 'refused'):
            record.action_review(self.operation, self.reason)
        elif self.operation == 'verify':
            record.action_verify(self.external_reference, self.reason)
        elif self.operation == 'withdraw':
            record.action_invalidate_pending(self.reason)
        else:
            raise ValidationError(_('Unsupported cash rectification operation.'))
        return {'type': 'ir.actions.act_window_close'}
