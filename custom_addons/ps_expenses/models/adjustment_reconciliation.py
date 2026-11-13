"""Recover an OLD cash attempt after authority/policy drift, never pay again.

Original approval/amount/attempt/expense facts stay frozen. Only a current
independent fact investigation may append an observed external outcome and
release this version for a freshly reviewed successor, keeping the parent hold.
"""
import hashlib
import json

from odoo import fields, models, _
from odoo.exceptions import AccessError, ValidationError

from .adjustment import FinancialAdjustment
from .correction import TripCorrection


class AdjustmentReconciliation(models.Model):
    _inherit = 'ps.te.adjustment'

    state = fields.Selection(selection_add=[('investigate', 'Existing Attempt Fact Investigation'),
        ('verify', 'Independent Existing Attempt Verification'), ('reconciled', 'Old Attempt Reconciled — New Review Required')],
        ondelete={'investigate': 'set default', 'verify': 'set default', 'reconciled': 'set default'})
    reconciliation_finance_id = fields.Many2one('res.users', readonly=True)
    reconciliation_cash_id = fields.Many2one('res.users', readonly=True)
    reconciliation_snapshot = fields.Text(readonly=True)
    reconciliation_digest = fields.Char(readonly=True)
    observed_outcome = fields.Selection([('none', 'Confirmed Non-Execution'), ('recorded', 'Observed External Execution')], readonly=True)
    observed_amount = fields.Monetary(readonly=True)
    observed_reference = fields.Char(readonly=True)
    observed_date = fields.Date(readonly=True)
    observation_evidence = fields.Char(readonly=True)
    observation_proposed_by_id = fields.Many2one('res.users', readonly=True)
    observation_verified_by_id = fields.Many2one('res.users', readonly=True)
    observation_verification_reference = fields.Char(readonly=True)
    reconciliation_completed_by_id = fields.Many2one('res.users', readonly=True)
    reconciliation_completed_at = fields.Datetime(readonly=True)

    def _reconciliation_current(self, role):
        self.correction_id._actor(role)
        case = self.correction_id
        if (not self.active_trip_id or not case.active_trip_id or self.state not in ('investigate', 'verify')
                or case.finance_reviewer_id != self.reconciliation_finance_id
                or case.cash_operator_id != self.reconciliation_cash_id):
            raise ValidationError(_('Renew current independent officers for this existing-attempt investigation.'))
        # Validate current supported currency/officers, but do not reuse the old
        # policy as permission for new execution.
        self.env['ps.te.settlement']._configuration(self.sudo().trip_id)

    def _observation_fingerprint(self):
        data = self.sudo()
        trip = data.trip_id
        root = data.cash_event_id
        leaf = self.env['ps.te.cash.rectification']._effective(root) if root else False
        if root and self.env['ps.te.cash.rectification'].sudo().search_count([
                ('root_event_id', '=', root.id), ('state', 'in', ('finance', 'cash'))]):
            raise ValidationError(_('Resolve pending cash fact rectifications before verifying the old attempt.'))
        snapshot = {'sources': self.correction_id._sources(trip)['source_digest'],
            'attempt': data.cash_attempt_reference, 'original_approved': [data.approved_by_id.id, str(data.approved_at), data.difference_amount],
            'cash_outcome': data.cash_outcome, 'root': [root.id, root.amount, root.external_reference,
                str(root.execution_date), root.kind] if root else None,
            'leaf': [leaf.id, leaf.proposed_amount, leaf.proposed_reference, str(leaf.proposed_date)] if leaf else None,
            'officers': [data.reconciliation_finance_id.id, data.reconciliation_cash_id.id]}
        encoded = json.dumps(snapshot, sort_keys=True)
        return encoded, hashlib.sha256(encoded.encode()).hexdigest()

    def action_request_existing_attempt_review(self, reason, expected_revision):
        self._lock()
        case = self.correction_id
        case._actor('owner')
        self._revision(expected_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Reconciliation reason'))
        if (not self.active_trip_id or not case.active_trip_id or self.state not in ('approved', 'investigate', 'verify')
                or not self.cash_attempt_reference or (self.cash_outcome not in ('uncertain', 'recorded')
                    and not (self.state == 'verify' and self.observed_outcome == 'none' and self.observation_verified_by_id))):
            raise ValidationError(_('Use this recovery path only for an existing uncertain or recorded approved attempt.'))
        configuration = case._configuration(self.sudo().trip_id)
        self.env['ps.te.settlement']._configuration(self.sudo().trip_id)
        with self.env.cr.savepoint():
            self._event('reconciliation_bindings_retained', reason)
            case._event('snapshot_replaced', reason)
            super(TripCorrection, case).write({**configuration, **case._sources(self.sudo().trip_id),
                                               'revision': case.revision + 1})
            super(FinancialAdjustment, self).write({'state': 'investigate', 'revision': self.revision + 1,
                'reconciliation_finance_id': configuration['finance_reviewer_id'],
                'reconciliation_cash_id': configuration['cash_operator_id'],
                'reconciliation_snapshot': False, 'reconciliation_digest': False,
                'observed_outcome': False, 'observed_amount': 0, 'observed_reference': False,
                'observed_date': False, 'observation_evidence': False, 'observation_proposed_by_id': False,
                'observation_verified_by_id': False, 'observation_verification_reference': False})
            self._event('existing_attempt_review_requested', reason)
        return True

    def action_propose_existing_outcome(self, outcome, amount, reference, execution_date, evidence_reference, reason, expected_revision):
        self._lock()
        self._reconciliation_current('finance')
        self._revision(expected_revision)
        helper = self.env['ps.te.trip.advance']
        reason = helper._text(reason, _('Reconciliation reason'))
        evidence = helper._text(evidence_reference, _('Reconciliation reference'))
        if self.state != 'investigate' or outcome not in ('none', 'recorded'):
            raise ValidationError(_('Propose only the observed outcome of the old prepared attempt.'))
        if outcome == 'recorded':
            amount = (self.env['ps.te.cash.rectification']._corrected_amount(amount) if self.cash_event_id
                      else self.env['ps.te.cash.event']._amount(amount))
            reference = helper._text(reference, _('External cash reference'))
            try:
                date = fields.Date.to_date(execution_date)
            except (ValueError, TypeError):
                raise ValidationError(_('A valid cash execution date is required.'))
            if not date or date > fields.Date.context_today(self) or date < self.approved_at.date():
                raise ValidationError(_('Cash date must be between approval date and today.'))
        else:
            if type(amount) is bool or amount != 0 or reference or execution_date or self.cash_event_id:
                raise ValidationError(_('Confirmed non-execution cannot erase a recorded movement or carry a payment amount.'))
            amount, reference, date = 0, False, False
        root = self.sudo().cash_event_id
        if root:
            leaf = self.env['ps.te.cash.rectification']._effective(root)
            effective = (leaf.proposed_amount, leaf.proposed_reference, leaf.proposed_date) if leaf else (
                root.amount, root.external_reference, root.execution_date)
            if outcome != 'recorded' or effective != (amount, reference, date):
                raise ValidationError(_('Use linked rectification for incorrect recorded facts; do not overwrite the old movement.'))
        snapshot, digest = self._observation_fingerprint()
        super(FinancialAdjustment, self).write({'state': 'verify', 'observed_outcome': outcome,
            'observed_amount': amount, 'observed_reference': reference, 'observed_date': date,
            'observation_evidence': evidence, 'observation_proposed_by_id': self.env.uid,
            'reconciliation_snapshot': snapshot, 'reconciliation_digest': digest})
        self._event('old_outcome_proposed', reason)
        return True

    def action_verify_existing_outcome(self, verification_reference, reason, expected_revision):
        self._lock()
        self._reconciliation_current('cash')
        self._revision(expected_revision)
        helper = self.env['ps.te.trip.advance']
        reference, reason = helper._text(verification_reference, _('Reconciliation reference')), helper._text(reason, _('Reconciliation reason'))
        if (self.state != 'verify' or self.observation_proposed_by_id != self.reconciliation_finance_id
                or self.observation_proposed_by_id == self.env.user):
            raise ValidationError(_('Current finance must propose the old outcome before independent cash verification.'))
        if self.reconciliation_digest != self._observation_fingerprint()[1]:
            raise ValidationError(_('Old-attempt facts or authority changed; propose and verify them again.'))
        if self.observation_verified_by_id:
            if self.observation_verified_by_id == self.env.user and self.observation_verification_reference == reference:
                return True
            raise ValidationError(_('A different verification is already retained for this old-attempt snapshot.'))
        with self.env.cr.savepoint():
            if self.observed_outcome == 'recorded' and not self.cash_event_id:
                event = self.env['ps.te.cash.event']._record_movement(self,
                    'topup' if self.difference_amount > 0 else 'return', self.observed_amount,
                    self.observed_reference, self.observed_date)
                super(FinancialAdjustment, self).write({'cash_event_id': event.id, 'cash_outcome': 'recorded'})
            elif self.observed_outcome == 'none':
                super(FinancialAdjustment, self).write({'cash_outcome': 'not_started'})
            super(FinancialAdjustment, self).write({'observation_verified_by_id': self.env.uid,
                'observation_verification_reference': reference})
            snapshot, digest = self._observation_fingerprint()
            super(FinancialAdjustment, self).write({'reconciliation_snapshot': snapshot, 'reconciliation_digest': digest})
            self._event('old_outcome_verified', reason)
        return True

    def action_finish_existing_attempt_review(self, reason, expected_revision):
        self._lock()
        self._reconciliation_current('finance')
        self._revision(expected_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Reconciliation reason'))
        if (self.state != 'verify' or self.observation_verified_by_id != self.reconciliation_cash_id
                or not self.observation_verification_reference or self.observation_verified_by_id == self.env.user
                or self.cash_outcome == 'uncertain' or self.reconciliation_digest != self._observation_fingerprint()[1]):
            raise ValidationError(_('Complete independent old-attempt verification before routing a fresh successor review.'))
        with self.env.cr.savepoint():
            super(FinancialAdjustment, self).write({'state': 'reconciled', 'active_trip_id': False,
                'reconciliation_completed_by_id': self.env.uid, 'reconciliation_completed_at': fields.Datetime.now()})
            case = self.correction_id
            case._event('snapshot_replaced', reason)
            super(TripCorrection, case).write({**case._sources(self.sudo().trip_id), 'revision': case.revision + 1})
            self._event('old_attempt_reconciled_successor_required', reason)
        # Deliberately no finance closure, no effective-report pointer change,
        # no clearing correction.active_trip_id, no bank call and no new cash.
        return True


class ReconciliationWizard(models.TransientModel):
    _inherit = 'ps.te.adjustment.wizard'

    operation = fields.Selection(selection_add=[('recover', 'Request Current-Officer Old-Attempt Review'),
        ('observe_none', 'Propose Old Attempt Not Executed'), ('observe_recorded', 'Propose Observed Old Attempt Cash'),
        ('verify_old', 'Verify Observed Old Attempt'), ('finish_old', 'Finish Old Attempt — Require New Review')],
        ondelete={'recover': 'cascade', 'observe_none': 'cascade', 'observe_recorded': 'cascade',
                  'verify_old': 'cascade', 'finish_old': 'cascade'})
    evidence_reference = fields.Char()

    def action_apply(self):
        self.ensure_one()
        record, revision = self.adjustment_id, self.expected_revision
        if self.operation == 'recover':
            record.action_request_existing_attempt_review(self.reason, revision)
        elif self.operation in ('observe_none', 'observe_recorded'):
            actual = self.operation == 'observe_recorded'
            record.action_propose_existing_outcome('recorded' if actual else 'none', self.amount if actual else 0,
                self.external_reference if actual else False, self.execution_date if actual else False,
                self.evidence_reference, self.reason, revision)
        elif self.operation == 'verify_old':
            record.action_verify_existing_outcome(self.external_reference, self.reason, revision)
        elif self.operation == 'finish_old':
            record.action_finish_existing_attempt_review(self.reason, revision)
        else:
            return super().action_apply()
        return {'type': 'ir.actions.act_window_close'}
