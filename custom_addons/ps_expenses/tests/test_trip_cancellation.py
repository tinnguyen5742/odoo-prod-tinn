import json

from odoo import SUPERUSER_ID, api, fields
from odoo.exceptions import AccessError, LockError, ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged

from .test_settlement import TestSettlement
from .test_advance import TestTripAdvance


@tagged('post_install', '-at_install')
class TestTripCancellation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with cls.registry.cursor() as cr:
            cls.race_company, cls.race_users = TestSettlement._fixture(api.Environment(cr, SUPERUSER_ID, {}))
            cr.commit()
        cls.company_id, users = TestSettlement._fixture(cls.env)
        cls.users = {role: cls.env['res.users'].browse(uid) for role, uid in users.items()}

    def _as(self, record, role):
        return record.with_user(self.users[role]).with_context(allowed_company_ids=[self.company_id])

    def _trip(self):
        return TestTripAdvance._new_trip(self.env, self.users)

    def _request(self, trip, reason='Synthetic cancellation'):
        trip.action_request_cancellation(reason, trip.preparing_revision, trip.cancellation_revision)

    def _approve(self, trip):
        self._as(trip, 'manager').action_decide_cancellation('approved', 'Synthetic manager cancellation', trip.cancellation_revision)

    def test_01_draft_cancellation_is_not_deletion_or_financial_close(self):
        trip = self._as(self.env['ps.te.trip.request'], 'owner').create({'purpose': 'Synthetic unfinished trip'})
        self._request(trip)
        self._approve(trip)
        self.assertEqual(trip.cancellation_status, 'approved')
        self.assertEqual(trip.state, 'preparing')
        self.assertEqual(trip.case_status, 'open')
        with self.assertRaises(ValidationError):
            trip.write({'destination': 'Cannot reopen', 'preparing_revision': 1})
        with self.assertRaises(ValidationError):
            trip.action_submit(1)
        with self.assertRaises(AccessError):
            trip.unlink()

    def test_02_awaiting_manager_cannot_be_business_approved_during_cancellation(self):
        trip = self._as(self.env['ps.te.trip.request'], 'owner').create({
            'purpose': 'Synthetic', 'destination': 'Synthetic', 'start_date': '2026-11-01', 'end_date': '2026-11-02',
        })
        trip.action_submit(1)
        receipt = trip.submission_receipt
        self._request(trip)
        with self.assertRaises(ValidationError):
            self._as(trip, 'manager').action_review('approved', 'Cannot approve pending cancellation', 1)
        self._approve(trip)
        self.assertEqual(trip.submission_receipt, receipt)
        self.assertEqual(trip.state, 'awaiting_business_review')

    def test_03_refusal_withdrawal_replay_and_revision(self):
        trip = self._trip()
        self._request(trip)
        trip.action_request_cancellation('Synthetic cancellation', trip.preparing_revision, 0)
        self.assertEqual(len(trip.event_ids.filtered(lambda e: e.event_type == 'cancellation_requested')), 1)
        manager = self._as(trip, 'manager')
        manager.action_decide_cancellation('refused', 'Trip continues', 1)
        manager.action_decide_cancellation('refused', 'Trip continues', 1)
        self.assertEqual(trip.cancellation_status, 'none')
        self._request(trip, 'Changed circumstances')
        with self.assertRaises(ValidationError):
            manager.action_decide_cancellation('approved', 'Old request', 1)
        trip.action_withdraw_cancellation('Owner withdraws', 2)
        trip.action_withdraw_cancellation('Owner withdraws', 2)
        self.assertEqual(trip.cancellation_status, 'none')
        self.assertEqual(trip.cancellation_revision, 2)

    def test_04_roles_direct_forgery_and_context_defaults(self):
        trip = self._trip()
        self._request(trip)
        for role in ('owner', 'finance', 'cash', 'other'):
            with self.assertRaises(AccessError):
                self._as(trip, role).action_decide_cancellation('approved', 'Wrong actor', 1)
        with self.assertRaises(AccessError):
            trip.write({'cancellation_status': 'approved'})
        with self.assertRaises(AccessError):
            trip.event_ids[:1].write({'cancellation_snapshot': '{}'})
        draft = self._as(self.env['ps.te.trip.request'], 'owner').with_context(
            default_cancellation_status='approved', default_cancellation_revision=99,
        ).create({'purpose': 'Synthetic hostile default'})
        self.assertEqual((draft.cancellation_status, draft.cancellation_revision), ('none', 0))
        self.assertFalse(self._as(self.env['ps.te.trip.request'], 'other').search([('id', '=', trip.id)]))

    def test_05_pending_and_approved_stop_new_advance(self):
        trip = self._trip()
        advance = self._as(self.env['ps.te.trip.advance'], 'owner').create({
            'trip_id': trip.id, 'purpose': 'Synthetic pending funding', 'requested_amount': 100000,
        })
        self._request(trip)
        with self.assertRaises(ValidationError):
            advance.action_submit(1)
        self._approve(trip)
        advance.action_cancel('Cancel unexecuted funding', 1)
        with self.assertRaises(ValidationError):
            advance.action_revise('Cannot reopen funding after trip cancellation', 1)
        trip.action_no_advance()
        self.assertEqual(trip.advance_choice, 'not_requested')

    def test_06_paid_advance_and_expenses_are_retained_then_return_resolved(self):
        settlement, report, advance = TestSettlement._case(self.env, self.users, accepted=60000, funding=100000)
        trip = settlement.trip_id
        original_claim, cash_id = report.claimed_total, advance.cash_event_id.id
        self._request(trip)
        self._approve(trip)
        self.assertEqual(trip.state, 'approved')
        self.assertEqual(trip.case_status, 'open')
        self.assertEqual(report.claimed_total, original_claim)
        self.assertEqual(advance.cash_event_id.id, cash_id)
        self.assertEqual(settlement.difference_amount, -40000)
        with self.assertRaises(ValidationError):
            advance.action_cancel('Cannot erase paid advance', 1)
        settlement.action_submit(1)
        self._as(settlement, 'finance').action_approve('Costs retained after cancellation', 1)
        with self.assertRaises(ValidationError):
            self._as(settlement, 'finance').action_close('Return not recorded', 1)
        cash = self._as(settlement, 'cash')
        cash.action_start_cash('SYNTHETIC-CANCEL-RETURN', 'Prepare external return', 1)
        cash.action_record_cash(40000, 'SYNTHETIC-CANCEL-RETURN-RECORDED', fields.Date.today(), 1)
        self._as(settlement, 'finance').action_close('Retained obligation resolved', 1)
        self.assertEqual(trip.case_status, 'workflow_closed')
        self.assertEqual(settlement.accounting_status, 'not_verified')
        event = trip.event_ids.filtered(lambda e: e.event_type == 'cancellation_approved')
        self.assertEqual(json.loads(event.cancellation_snapshot)['advance_state'], 'disbursed')

    def test_07_uncertain_advance_can_reconcile_but_not_restart_after_cancel(self):
        settlement, report, advance = TestSettlement._case(self.env, self.users, pending=True)
        cash = self._as(advance, 'cash')
        cash.action_start_disbursement('SYNTHETIC-UNKNOWN-ADVANCE', 'External attempt', 1)
        self._request(settlement.trip_id)
        self._approve(settlement.trip_id)
        with self.assertRaises(ValidationError):
            advance.action_cancel('Cannot assume zero', 1)
        cash.action_record_disbursement(100000, 'SYNTHETIC-UNKNOWN-ADVANCE-PAID', fields.Date.today(), 1)
        self.assertTrue(advance.has_disbursement)
        settlement.action_refresh('Use reconciled actual funding', 1)
        self.assertTrue(settlement.funding_known)

    def test_08_pending_cancel_pauses_settlement_but_keeps_reconciliation(self):
        settlement, report, advance = TestSettlement._case(self.env, self.users, accepted=150000)
        settlement.action_submit(1)
        finance, cash = self._as(settlement, 'finance'), self._as(settlement, 'cash')
        finance.action_approve('Original costs', 1)
        cash.action_start_cash('SYNTHETIC-CANCEL-UNKNOWN', 'Prepare external topup', 1)
        self._request(settlement.trip_id)
        with self.assertRaises(ValidationError):
            finance.action_close('Cannot close pending cancellation', 1)
        cash.action_record_cash(50000, 'SYNTHETIC-CANCEL-UNKNOWN-PAID', fields.Date.today(), 1)
        self._approve(settlement.trip_id)
        finance.action_close('Existing exact obligation resolved', 1)
        with self.assertRaises(ValidationError):
            self._request(settlement.trip_id, 'Cannot retroactively cancel closed case')

    def test_09_new_settlement_approval_and_cash_start_wait_for_decision(self):
        settlement, report, advance = TestSettlement._case(self.env, self.users, accepted=150000)
        settlement.action_submit(1)
        self._request(settlement.trip_id)
        with self.assertRaises(ValidationError):
            self._as(settlement, 'finance').action_approve('Pending cancellation', 1)
        settlement.trip_id.action_withdraw_cancellation('Continue trip', 1)
        self._as(settlement, 'finance').action_approve('Original basis', 1)
        self._request(settlement.trip_id, 'Second cancellation request')
        with self.assertRaises(ValidationError):
            self._as(settlement, 'cash').action_start_cash('NO-START', 'Pending cancellation', 1)

    def test_10_native_wizard_and_print_summary_show_separate_axis(self):
        settlement, report, advance = TestSettlement._case(self.env, self.users)
        trip = settlement.trip_id
        model = self._as(self.env['ps.te.trip.cancellation.wizard'], 'owner').with_context(**trip.action_open_cancellation()['context'])
        with Form(model) as wizard:
            wizard.operation = 'request'
            wizard.reason = 'Synthetic wizard cancellation'
        wizard.record.action_apply()
        Form(self._as(trip, 'manager'))
        self._approve(trip)
        output, _ = self._as(self.env['ir.actions.report'], 'cash')._render_qweb_html(
            'ps_expenses.settlement_summary', [settlement.id])
        self.assertIn('Travel Cancelled', output.decode())
        self.assertEqual(trip.case_status, 'open')

    def test_11_competing_cancellation_and_new_funding_serialize(self):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            users = {role: env['res.users'].browse(uid) for role, uid in self.race_users.items()}
            trip = TestTripAdvance._new_trip(env, users)
            trip_id = trip.id
            cr.commit()
        context = {'allowed_company_ids': [self.race_company]}
        with self.registry.cursor() as cancel_cr, self.registry.cursor() as advance_cr:
            trip = api.Environment(cancel_cr, self.race_users['owner'], context)['ps.te.trip.request'].browse(trip_id)
            trip.action_request_cancellation('Competing cancellation', 1, 0)
            env2 = api.Environment(advance_cr, self.race_users['owner'], context)
            with self.assertRaises(LockError):
                env2['ps.te.trip.advance'].create({'trip_id': trip_id, 'purpose': 'Competing advance', 'requested_amount': 100000})
            advance_cr.rollback()
            cancel_cr.commit()
        with self.registry.cursor() as cr:
            env = api.Environment(cr, self.race_users['owner'], context)
            with self.assertRaises(ValidationError):
                env['ps.te.trip.advance'].create({'trip_id': trip_id, 'purpose': 'Late advance', 'requested_amount': 100000})

    def test_12_stale_revision_and_manager_revocation_do_not_approve(self):
        trip = self._trip()
        with self.assertRaises(ValidationError):
            trip.action_request_cancellation('Stale request', 99, 0)
        self._request(trip)
        self.users['manager'].group_ids -= self.env.ref('ps_expenses.group_ps_te_trip_manager')
        with self.assertRaises(AccessError):
            self._as(trip, 'manager').action_decide_cancellation('approved', 'Revoked actor', 1)
        self.assertEqual(trip.cancellation_status, 'requested')
