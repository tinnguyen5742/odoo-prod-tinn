"""Reconcile old external facts; never silently authorize a second payment."""
from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from .test_adjustment import TestFinancialAdjustment
from .test_settlement import TestSettlement


@tagged('post_install', '-at_install')
class TestAdjustmentReconciliation(TransactionCase):
    _original = TestFinancialAdjustment._original
    _adjust = TestFinancialAdjustment._adjust
    _review = TestFinancialAdjustment._review
    _authorize = TestFinancialAdjustment._authorize
    _pay = TestFinancialAdjustment._pay

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_id, actors = TestSettlement._fixture(cls.env)
        cls.users = {role: cls.env['res.users'].browse(uid) for role, uid in actors.items()}

    def _prepared(self, recorded=False):
        settlement, original, advance = self._original()
        adjustment = self._adjust(settlement.trip_id)
        self._review(adjustment, 150000)
        self._authorize(adjustment)
        if recorded:
            self._pay(adjustment)
        else:
            adjustment.with_user(self.users['cash']).action_start_cash(
                'SYNTHETIC-OLD-ATTEMPT', 'Synthetic old prepared attempt', adjustment.revision)
        return adjustment, settlement, original

    def _change_policy(self):
        company = self.env['res.company'].browse(self.company_id)
        company.ps_te_expense_policy_reference += '-NEW'
        company.ps_te_settlement_policy_reference += '-NEW'

    def _bind(self, adjustment):
        adjustment.action_request_existing_attempt_review('Synthetic investigate old attempt only', adjustment.revision)

    def _observe(self, adjustment, outcome='none', amount=0, reference=False):
        finance = adjustment.with_user(adjustment.reconciliation_finance_id)
        finance.action_propose_existing_outcome(outcome, amount, reference,
            fields.Date.today() if outcome == 'recorded' else False,
            'SYNTHETIC-EXTERNAL-EVIDENCE', 'Synthetic observed external outcome', adjustment.revision)
        adjustment.with_user(adjustment.reconciliation_cash_id).action_verify_existing_outcome(
            'SYNTHETIC-INDEPENDENT-OLD-CHECK', 'Synthetic checked independent external evidence', adjustment.revision)
        finance.action_finish_existing_attempt_review('Synthetic old attempt reconciled, successor still required', adjustment.revision)

    def test_01_policy_drift_uncertain_nonexecution_requires_fresh_successor(self):
        adjustment, settlement, original = self._prepared()
        old = (adjustment.approved_by_id, adjustment.approved_at, adjustment.cash_attempt_reference,
               adjustment.difference_amount, adjustment.report_id, original.accepted_total)
        self._change_policy()
        with self.assertRaises(ValidationError):
            adjustment.with_user(self.users['cash']).action_record_cash(50000, 'UNSAFE-OLD-RECORD', fields.Date.today(), adjustment.revision)
        self._bind(adjustment)
        self._observe(adjustment)
        self.assertEqual(adjustment.state, 'reconciled')
        self.assertFalse(adjustment.active_trip_id)
        self.assertFalse(adjustment.cash_event_id)
        self.assertTrue(adjustment.correction_id.active_trip_id)
        self.assertTrue(settlement.trip_id.correction_hold)
        self.assertEqual((adjustment.approved_by_id, adjustment.approved_at, adjustment.cash_attempt_reference,
                          adjustment.difference_amount, adjustment.report_id, original.accepted_total), old)
        successor = self.env['ps.te.adjustment'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'correction_id': adjustment.correction_id.id,
                'reason': 'Synthetic newly reviewed successor', 'expected_revision': adjustment.correction_id.revision})
        self.assertEqual(successor.carry_report_id, adjustment.report_id)
        self.assertEqual(successor.previous_report_id, original)
        self._review(successor, 150000)
        self._authorize(successor)
        self.assertEqual(successor.difference_amount, 50000)
        self._pay(successor)
        successor.with_user(self.users['finance']).action_close('Synthetic new reviewed resolution', successor.revision)
        self.assertFalse(settlement.trip_id.correction_hold)
        self.assertEqual(settlement.trip_id.effective_expense_report_id, successor.report_id)

    def test_02_old_actual_execution_is_recorded_once_without_new_authority(self):
        adjustment, settlement, original = self._prepared()
        self._change_policy()
        self._bind(adjustment)
        before = self.env['ps.te.cash.event'].search_count([])
        self._observe(adjustment, 'recorded', 50000, 'SYNTHETIC-OBSERVED-OLD-EXECUTION')
        self.assertEqual(self.env['ps.te.cash.event'].search_count([]), before + 1)
        self.assertEqual(adjustment.cash_event_id.amount, 50000)
        self.assertEqual(adjustment.state, 'reconciled')
        self.assertEqual(self.env['ps.te.cash.event']._verified_net(settlement.trip_id)['amount'], 150000)
        with self.assertRaises(ValidationError):
            adjustment.with_user(self.users['cash']).action_start_cash('DO-NOT-PAY-AGAIN', 'No new authorization', adjustment.revision)
        self.assertTrue(settlement.trip_id.correction_hold)
        self.assertFalse(settlement.trip_id.effective_expense_report_id)

    def test_03_recorded_actual_cash_is_confirmed_not_duplicated_or_zeroed(self):
        adjustment, settlement, original = self._prepared(recorded=True)
        root = adjustment.cash_event_id
        self._change_policy()
        self._bind(adjustment)
        finance = adjustment.with_user(self.users['finance'])
        with self.assertRaises(ValidationError):
            finance.action_propose_existing_outcome('none', 0, False, False, 'FALSE-NONE', 'Cannot erase cash', adjustment.revision)
        with self.assertRaises(ValidationError):
            finance.action_propose_existing_outcome('recorded', 1, root.external_reference, fields.Date.today(),
                'FALSE-AMOUNT', 'Use linked rectification, not overwrite', adjustment.revision)
        before = self.env['ps.te.cash.event'].search_count([])
        self._observe(adjustment, 'recorded', root.amount, root.external_reference)
        self.assertEqual(self.env['ps.te.cash.event'].search_count([]), before)
        self.assertEqual(adjustment.cash_event_id, root)
        self.assertTrue(settlement.trip_id.correction_hold)

    def test_04_new_current_officers_verify_old_facts_without_impersonation(self):
        adjustment, settlement, original = self._prepared()
        original_approver = adjustment.approved_by_id
        new_finance = self.users['other']
        new_finance.write({'group_ids': [Command.link(self.env.ref('ps_expenses.group_ps_te_finance').id)]})
        new_cash = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Synthetic replacement cash', 'login': 'replacement.cash.' + str(adjustment.id) + '@example.invalid',
            'company_id': self.company_id, 'company_ids': [Command.set([self.company_id])],
            'group_ids': [Command.set([self.env.ref('base.group_user').id, self.env.ref('ps_expenses.group_ps_te_cash').id])]})
        self.env['res.company'].browse(self.company_id).write({
            'ps_te_finance_reviewer_id': new_finance.id, 'ps_te_cash_operator_id': new_cash.id})
        self._bind(adjustment)
        for role in ('finance', 'cash'):
            with self.assertRaises(AccessError):
                adjustment.with_user(self.users[role]).read(['reconciliation_digest'])
        self._observe(adjustment, 'recorded', 50000, 'SYNTHETIC-NEW-OFFICER-OLD-FACT')
        self.assertEqual(adjustment.approved_by_id, original_approver)
        self.assertEqual(adjustment.observation_proposed_by_id, new_finance)
        self.assertEqual(adjustment.observation_verified_by_id, new_cash)
        self.assertEqual(adjustment.cash_event_id.actor_id, new_cash)
        self.assertFalse(settlement.trip_id.effective_expense_report_id)

    def test_05_observed_amount_exception_stays_held_for_fresh_full_difference(self):
        adjustment, settlement, original = self._prepared()
        self._change_policy()
        self._bind(adjustment)
        self._observe(adjustment, 'recorded', 20000, 'SYNTHETIC-OBSERVED-EXCEPTION-NOT-INSTALLMENT')
        self.assertEqual(adjustment.cash_event_id.amount, 20000)
        self.assertEqual(adjustment.difference_amount, 50000)
        self.assertEqual(self.env['ps.te.cash.event']._verified_net(settlement.trip_id)['amount'], 120000)
        self.assertTrue(settlement.trip_id.correction_hold)
        self.assertEqual(adjustment.state, 'reconciled')
        with self.assertRaises(ValidationError):
            adjustment.with_user(self.users['cash']).action_record_cash(30000, 'FALSE-INSTALLMENT', fields.Date.today(), adjustment.revision)

    def test_06_wrong_roles_self_check_and_source_drift_cannot_verify(self):
        adjustment, settlement, original = self._prepared()
        self._bind(adjustment)
        with self.assertRaises(AccessError):
            adjustment.action_propose_existing_outcome('none', 0, False, False, 'OWNER-FORGE', 'Cannot self approve', adjustment.revision)
        with self.assertRaises(ValidationError):
            adjustment.with_user(self.users['cash']).action_verify_existing_outcome('EARLY', 'No finance proposal', adjustment.revision)
        adjustment.with_user(self.users['finance']).action_propose_existing_outcome(
            'none', 0, False, False, 'SYNTHETIC-SOURCE-CHECK', 'Synthetic no execution', adjustment.revision)
        self._change_policy()
        with self.assertRaises(ValidationError):
            adjustment.with_user(self.users['cash']).action_verify_existing_outcome('STALE', 'Source changed', adjustment.revision)
        self._bind(adjustment)
        self.assertFalse(adjustment.observation_proposed_by_id)
        self.assertFalse(adjustment.observation_verified_by_id)
        self._observe(adjustment)

    def test_07_drift_after_verified_nonexecution_can_rebind_without_restarting_cash(self):
        adjustment, settlement, original = self._prepared()
        self._bind(adjustment)
        finance, cash = adjustment.with_user(self.users['finance']), adjustment.with_user(self.users['cash'])
        finance.action_propose_existing_outcome('none', 0, False, False, 'SYNTHETIC-NONE-OBSERVED', 'Synthetic no execution', adjustment.revision)
        cash.action_verify_existing_outcome('SYNTHETIC-NONE-VERIFIED', 'Synthetic independent no execution', adjustment.revision)
        self.assertEqual(adjustment.cash_outcome, 'not_started')
        self._change_policy()
        with self.assertRaises(ValidationError):
            finance.action_finish_existing_attempt_review('Stale verification', adjustment.revision)
        self._bind(adjustment)
        self.assertEqual(adjustment.state, 'investigate')
        self._observe(adjustment)
        self.assertEqual(adjustment.state, 'reconciled')
        self.assertFalse(adjustment.cash_event_id)
        with self.assertRaises(ValidationError):
            cash.action_start_cash('NEVER-RESTART-OLD', 'No fresh authorization', adjustment.revision)

    def test_08_corrected_zero_of_recorded_root_is_confirmed_without_fake_reversal(self):
        adjustment, settlement, original = self._prepared(recorded=True)
        root = adjustment.cash_event_id
        self._change_policy()
        self._bind(adjustment)
        case = adjustment.correction_id
        correction = self.env['ps.te.cash.rectification'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'correction_id': case.id, 'root_event_id': root.id,
                'amount': 0, 'reference': root.external_reference, 'date': fields.Date.today(),
                'reason': 'Synthetic entered cash was never actually executed', 'expected_revision': case.revision})
        correction.with_user(self.users['finance']).action_review('approved', 'Synthetic zero actual correction')
        correction.with_user(self.users['cash']).action_verify('SYNTHETIC-ZERO-FACT', 'Synthetic independent zero fact')
        before = self.env['ps.te.cash.event'].search_count([])
        self._observe(adjustment, 'recorded', 0, root.external_reference)
        self.assertEqual(root.amount, 50000)
        self.assertEqual(correction.proposed_amount, 0)
        self.assertEqual(self.env['ps.te.cash.event'].search_count([]), before)
        self.assertEqual(self.env['ps.te.cash.event']._verified_net(settlement.trip_id)['amount'], 100000)
        self.assertTrue(settlement.trip_id.correction_hold)
