"""Regression tests for linked cash fact rectification and independent checking."""
from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from .test_settlement import TestSettlement


@tagged('post_install', '-at_install')
class TestCashRectification(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_id, actors = TestSettlement._fixture(cls.env)
        cls.users = {role: cls.env['res.users'].browse(uid) for role, uid in actors.items()}

    def _case(self):
        settlement, report, advance = TestSettlement._case(self.env, self.users)
        case = self.env['ps.te.correction'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'trip_id': settlement.trip_id.id, 'category': 'funding',
                'description': 'Synthetic cash entry correction', 'expected_revision': settlement.trip_id.preparing_revision})
        return case, advance.cash_event_id

    def _new(self, case, root, amount=75000, reference=None):
        return self.env['ps.te.cash.rectification'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'correction_id': case.id, 'root_event_id': root.id,
                'amount': amount, 'reference': reference or root.external_reference, 'date': fields.Date.today(),
                'reason': 'Synthetic data entry repair, not a payment', 'expected_revision': case.revision})

    def _verify(self, record, reference='SYNTHETIC-RECT-VERIFIED'):
        record.with_user(self.users['finance']).action_review('approved', 'Synthetic approved correction assertion')
        record.with_user(self.users['cash']).action_verify(reference, 'Synthetic external fact verification')

    def test_01_data_correction_retains_actual_row_and_requires_independent_check(self):
        case, root = self._case()
        before = (root.amount, root.external_reference, root.execution_date)
        before_count = self.env['ps.te.cash.event'].search_count([])
        record = self._new(case, root)
        with self.assertRaises(ValidationError):
            record.with_user(self.users['cash']).action_verify('PREMATURE', 'Finance has not reviewed')
        self._verify(record)
        self.assertEqual(record.state, 'verified')
        self.assertEqual(record.proposed_amount, 75000)
        self.assertEqual((root.amount, root.external_reference, root.execution_date), before)
        self.assertEqual(self.env['ps.te.cash.event'].search_count([]), before_count)
        self.assertEqual(record._effective(root), record.sudo())
        self.assertTrue(case.active_trip_id)
        with self.assertRaises(ValidationError):
            case.with_user(self.users['finance']).action_propose_no_change('FALSE-NO-CHANGE', 'Must adjust fully', case.revision)

    def test_02_verified_chain_keeps_previous_assertions_and_handles_actual_zero(self):
        case, root = self._case()
        first = self._new(case, root)
        self._verify(first)
        second = self._new(case, root, amount=0)
        self.assertEqual(second.previous_id, first)
        self._verify(second, 'SYNTHETIC-RECT-ZERO')
        self.assertEqual(second.proposed_amount, 0)
        self.assertEqual(second._effective(root), second.sudo())
        self.assertEqual(first.state, 'verified')
        self.assertGreater(root.amount, 0)
        with self.assertRaises(AccessError):
            first.write({'proposed_amount': 1})
        with self.assertRaises(AccessError):
            second.unlink()

    def test_03_wrong_roles_and_other_trip_sources_are_denied(self):
        case, root = self._case()
        record = self._new(case, root)
        with self.assertRaises(AccessError):
            record.action_review('approved', 'Owner cannot approve')
        with self.assertRaises(AccessError):
            record.with_user(self.users['manager']).read(['proposed_amount'])
        case2, root2 = self._case()
        with self.assertRaises(ValidationError):
            self._new(case2, root)
        with self.assertRaises(AccessError):
            self.env['ps.te.cash.reference.claim'].with_user(self.users['owner']).create({
                'company_id': self.company_id, 'reference': 'FORGED', 'root_event_id': root.id})

    def test_04_corrected_reference_reservation_blocks_different_actual_movement(self):
        case, root = self._case()
        record = self._new(case, root, reference='SYNTHETIC-CORRECTED-BANK-REFERENCE')
        self._verify(record)
        case2, root2 = self._case()
        conflict = self._new(case2, root2, reference=record.proposed_reference)
        conflict.with_user(self.users['finance']).action_review('approved', 'Synthetic conflict check')
        with self.assertRaises(ValidationError):
            conflict.with_user(self.users['cash']).action_verify('COLLISION', 'Duplicate external reference')
        self.assertEqual(conflict.state, 'cash')
        self.assertEqual(self.env['ps.te.cash.reference.claim'].sudo().search_count([
            ('company_id', '=', self.company_id), ('reference', '=', record.proposed_reference)]), 1)

    def test_05_pending_proposal_can_be_replaced_without_resetting_cash_or_case(self):
        case, root = self._case()
        first = self._new(case, root)
        first.action_invalidate_pending('Synthetic owner withdrew unverified proposal')
        self.assertEqual(first.state, 'refused')
        self.assertTrue(case.active_trip_id)
        replacement = self._new(case, root, amount=70000)
        self._verify(replacement)
        with self.assertRaises(ValidationError):
            replacement.action_invalidate_pending('Cannot withdraw already verified facts')
        self.assertEqual(root.amount, 100000)

    def test_06_reserved_corrected_reference_cannot_record_a_new_actual_payment(self):
        case, root = self._case()
        record = self._new(case, root, reference='SYNTHETIC-RESERVED-ACTUAL-COLLISION')
        self._verify(record)
        settlement, report, advance = TestSettlement._case(self.env, self.users, pending=True)
        cash = advance.with_user(self.users['cash'])
        cash.action_start_disbursement('SYNTHETIC-NEW-ATTEMPT', 'Synthetic attempted payment', advance.revision)
        before = self.env['ps.te.cash.event'].search_count([])
        with self.assertRaises(ValidationError):
            cash.action_record_disbursement(100000, record.proposed_reference, fields.Date.today(), advance.revision)
        self.assertEqual(self.env['ps.te.cash.event'].search_count([]), before)
        self.assertFalse(advance.cash_event_id)
        self.assertEqual(advance.payment_outcome, 'uncertain')

    def _paid_settlement(self, accepted):
        settlement, report, advance = TestSettlement._case(self.env, self.users, accepted=accepted)
        settlement.action_submit(settlement.revision)
        settlement.with_user(self.users['finance']).action_approve('Synthetic reviewed settlement', settlement.revision)
        cash = settlement.with_user(self.users['cash'])
        cash.action_start_cash('SYNTHETIC-PRIOR-SETTLEMENT', 'Synthetic real prior movement', settlement.revision)
        cash.action_record_cash(abs(settlement.difference_amount), 'SYNTHETIC-SETTLEMENT-' + str(settlement.id),
                                fields.Date.today(), settlement.revision)
        settlement.with_user(self.users['finance']).action_close('Synthetic prior workflow closure', settlement.revision)
        return settlement, report, advance

    def _correction(self, trip):
        return self.env['ps.te.correction'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'trip_id': trip.id, 'category': 'funding',
                'description': 'Synthetic full post-closure adjustment', 'expected_revision': trip.preparing_revision})

    def test_07_net_cash_includes_prior_topup_and_substitutes_verified_leaf_only(self):
        settlement, report, advance = self._paid_settlement(150000)
        cash = self.env['ps.te.cash.event']
        self.assertEqual(cash._verified_net(settlement.trip_id)['amount'], 150000)
        case = self._correction(settlement.trip_id)
        record = self._new(case, advance.cash_event_id, amount=75000)
        pending = cash._verified_net(settlement.trip_id)
        self.assertIsNone(pending['amount'])
        self.assertEqual(pending['verified_net'], 150000)
        self.assertIn('unverified_rectification', pending['holds'])
        self._verify(record)
        actual = cash._verified_net(settlement.trip_id)
        self.assertTrue(actual['known'])
        self.assertEqual(actual['amount'], 125000)
        self.assertEqual(len(actual['leaves']), 2)
        second = self._new(case, advance.cash_event_id, amount=70000)
        self._verify(second, 'SYNTHETIC-SECOND-LEAF')
        self.assertEqual(cash._verified_net(settlement.trip_id)['amount'], 120000)
        self.assertEqual(advance.disbursed_amount, 100000)
        self.assertEqual(settlement.state, 'closed')
        self.assertTrue(case.active_trip_id)

    def test_08_net_cash_subtracts_prior_returns_and_never_infers_unknown_zero(self):
        settlement, report, advance = self._paid_settlement(60000)
        cash = self.env['ps.te.cash.event']
        self.assertEqual(cash._verified_net(settlement.trip_id)['amount'], 60000)
        case = self._correction(settlement.trip_id)
        record = self._new(case, settlement.cash_event_id, amount=10000)
        self._verify(record)
        self.assertEqual(cash._verified_net(settlement.trip_id)['amount'], 90000)
        self.assertEqual(settlement.cash_event_id.amount, 40000)
        unknown, _, _ = TestSettlement._case(self.env, self.users, funding=None)
        self.assertFalse(cash._verified_net(unknown.trip_id)['known'])
        self.assertIsNone(cash._verified_net(unknown.trip_id)['amount'])
        unknown.with_user(self.users['cash']).action_confirm_no_funding(
            'SYNTHETIC-EXPLICIT-ZERO-FUNDING', 'Synthetic independent no-funding check', unknown.revision)
        self.assertEqual(cash._verified_net(unknown.trip_id)['amount'], 0)

    def test_09_rectified_amount_date_validation_and_untrusted_context(self):
        case, root = self._case()
        for bad in (True, False, -1, 0.5, 'NaN', 'Infinity', 'invalid', 99999999999901):
            with self.assertRaises(ValidationError):
                self._new(case, root, amount=bad)
        record = self._new(case, root, amount='0')
        self.assertEqual(record.proposed_amount, 0)
        record.action_invalidate_pending('Synthetic replace validation proposal')
        forged = self.env['ps.te.cash.rectification'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id], default_state='verified', default_verified_by_id=self.users['cash'].id,
            default_active_predecessor_key='FORGED').create({'correction_id': case.id, 'root_event_id': root.id,
                'amount': 90000, 'reference': root.external_reference, 'date': fields.Date.today(),
                'reason': 'Synthetic context isolation', 'expected_revision': case.revision})
        self.assertEqual(forged.state, 'finance')
        self.assertFalse(forged.verified_by_id)
        self.assertNotEqual(forged.active_predecessor_key, 'FORGED')
