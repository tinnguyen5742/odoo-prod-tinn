import json
import uuid

from odoo import SUPERUSER_ID, api, fields
from odoo.exceptions import AccessError, LockError, ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged

from .test_settlement import TestSettlement
from .test_advance import TestTripAdvance


@tagged('post_install', '-at_install')
class TestCancelledZeroExpenses(TransactionCase):
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

    @staticmethod
    def _case(env, users, funding=None, uncertain=False, preparing=False):
        context = {'allowed_company_ids': [users['owner'].company_id.id]}
        if preparing:
            trip = env['ps.te.trip.request'].with_user(users['owner']).with_context(**context).create({'purpose': 'Synthetic unstarted trip'})
        else:
            trip = TestTripAdvance._new_trip(env, users)
        advance = env['ps.te.trip.advance'].browse()
        if funding is not None:
            advance = env['ps.te.trip.advance'].with_user(users['owner']).with_context(**context).create({
                'trip_id': trip.id, 'requested_amount': funding, 'purpose': 'Synthetic zero-expense advance',
            })
            advance.action_submit(1)
            advance.with_user(users['finance']).action_review('approved', 'Synthetic funding approval', 1, funding)
            cash = advance.with_user(users['cash'])
            cash.action_start_disbursement('ZERO-ATTEMPT-' + uuid.uuid4().hex, 'Synthetic external preparation', 1)
            if not uncertain:
                cash.action_record_disbursement(funding, 'ZERO-ADV-' + uuid.uuid4().hex, fields.Date.today(), 1)
        trip.action_request_cancellation('Synthetic cancelled before expenses', trip.preparing_revision, 0)
        trip.with_user(users['manager']).action_decide_cancellation('approved', 'Synthetic manager cancellation', 1)
        if funding is None:
            trip.action_no_advance()
        report = env['ps.te.expense.report'].with_user(users['owner']).with_context(**context).create({'trip_id': trip.id})
        return trip, report, advance

    def _new(self, **kwargs):
        return self._case(self.env, self.users, **kwargs)

    def _ready(self, report):
        report.action_declare_zero_expenses('No employee-paid costs were incurred', report.revision)
        report.action_submit(report.revision)
        self._as(report, 'finance').action_review_zero_expenses('accepted', 'Checked explicit zero declaration', report.revision)

    def test_14_cancelled_empty_trip_normal_expenses_route_opens_report_control(self):
        for funding in (None, 100000):
            trip, report, advance = self._new(funding=funding, preparing=funding is None)
            before = (report.revision, trip.preparing_revision, advance.disbursed_amount)
            action = trip.action_open_expenses()
            self.assertEqual((action['res_model'], action['res_id']), ('ps.te.expense.report', report.id))
            self.assertEqual(action['views'][0][0], self.env.ref('ps_expenses.view_ps_te_expense_form').id)
            for role in ('owner', 'finance'):
                viewed = self._as(report, role)
                self.assertEqual(viewed._entry_action()['res_id'], report.id)
                form = Form(viewed, view='ps_expenses.view_ps_te_expense_form')
                self.assertFalse(form.zero_expense_declared)
                self.assertEqual(viewed.action_open_operation()['context']['default_expected_revision'], report.revision)
            for role in ('other', 'manager', 'cash'):
                with self.assertRaises(AccessError):
                    self._as(report, role)._entry_action()
            self.assertFalse(report.line_ids)
            self.assertFalse(self.env['hr.expense'].search([('ps_report_id', '=', report.id)]))
            self.assertFalse(report.zero_expense_declared)
            self.assertFalse(report.accepted_basis_ready)
            self.assertEqual((report.revision, trip.preparing_revision, advance.disbursed_amount), before)
            with self.assertRaises(ValidationError):
                report.action_submit(report.revision)

    def test_15_report_menu_includes_empty_assigned_finance_basis(self):
        trip, report, _ = self._new(preparing=True)
        menu = self.env.ref('ps_expenses.menu_ps_te_expenses')
        self.assertEqual(menu.action, self.env.ref('ps_expenses.action_ps_te_expenses'))
        self.assertEqual(menu.action.res_model, 'ps.te.expense.report')
        self.assertIn('list', menu.action.view_mode)
        for role in ('owner', 'finance'):
            self.assertEqual(self._as(self.env[menu.action.res_model], role).search([('id', '=', report.id)]).ids, report.ids)
        for role in ('other', 'manager', 'cash'):
            self.assertFalse(self._as(self.env[menu.action.res_model], role).search([('id', '=', report.id)]))
        wizard_model = self._as(self.env['ps.te.expense.wizard'], 'owner').with_context(
            **report.action_open_operation()['context'])
        with Form(wizard_model, view='ps_expenses.view_ps_te_expense_wizard') as wizard:
            wizard.operation = 'zero_declare'
            wizard.reason = 'R6 explicit declaration via ordinary report control'
        wizard.record.action_apply()
        report.action_submit(report.revision)
        finance = self._as(report, 'finance')
        with Form(self._as(self.env['ps.te.expense.wizard'], 'finance').with_context(
                **finance.action_open_operation()['context']), view='ps_expenses.view_ps_te_expense_wizard') as review:
            review.operation = 'zero_accept'
            review.reason = 'R6 independent finance zero check'
        review.record.action_apply()
        self.assertTrue(report.accepted_basis_ready)
        self.assertFalse(report.line_ids)
        self.assertFalse(self.env['hr.expense'].search([('ps_report_id', '=', report.id)]))

    def test_16_explicit_native_button_still_opens_native_without_auto_zero_or_funding(self):
        trip, report, _ = self._new(preparing=True)
        action = report.action_open_native_expenses()
        self.assertEqual(action['res_model'], 'hr.expense')
        self.assertEqual(action['context']['default_ps_report_id'], report.id)
        self.assertFalse(report.zero_expense_declared)
        self.assertFalse(report.accepted_basis_ready)
        with self.assertRaises(ValidationError):
            self._settlement(trip)

    def test_17_fresh_cancelled_trip_entry_creates_only_empty_report(self):
        trip = self._as(self.env['ps.te.trip.request'], 'owner').create({'purpose': 'R6 new cancelled UI entry'})
        trip.action_request_cancellation('R6 cancel before any costs', trip.preparing_revision, 0)
        self._as(trip, 'manager').action_decide_cancellation('approved', 'R6 manager cancels travel', 1)
        trip.action_no_advance()
        self.assertFalse(trip.expense_report_id)
        action = trip.action_open_expenses()
        report = trip.expense_report_id
        self.assertEqual((action['res_model'], action['res_id']), ('ps.te.expense.report', report.id))
        self.assertFalse(report.line_ids)
        self.assertFalse(report.zero_expense_declared)
        self.assertFalse(report.accepted_basis_ready)
        self.assertEqual(report.revision, 1)
        with self.assertRaises(ValidationError):
            report.action_submit(report.revision)

    def _settlement(self, trip):
        return self._as(self.env['ps.te.settlement'], 'owner').create({'trip_id': trip.id})

    def test_01_empty_report_is_not_zero_acceptance(self):
        trip, report, _ = self._new()
        self.assertFalse(report.accepted_basis_ready)
        with self.assertRaises(ValidationError):
            report.action_submit(1)
        with self.assertRaises(ValidationError):
            self._settlement(trip)
        report.action_declare_zero_expenses('No costs', 1)
        self.assertFalse(report.accepted_basis_ready)
        report.action_submit(report.revision)
        self.assertFalse(report.accepted_basis_ready)
        self._as(report, 'finance').action_review_zero_expenses('accepted', 'Checked', report.revision)
        self.assertTrue(report.accepted_basis_ready)
        self.assertFalse(report.line_ids)
        self.assertEqual(report.accepted_total, 0)

    def test_02_prebusiness_cancel_requires_both_zero_review_and_cash_confirmation(self):
        trip, report, _ = self._new(preparing=True)
        self.assertEqual(trip.state, 'preparing')
        self._ready(report)
        settlement = self._settlement(trip)
        self.assertEqual(settlement.expense_basis_kind, 'zero_declaration')
        settlement.action_submit(1)
        with self.assertRaises(ValidationError):
            self._as(settlement, 'finance').action_approve('Missing funding confirmation', 1)
        self._as(settlement, 'cash').action_confirm_no_funding('ZERO-NO-FUNDS', 'No external funding occurred', 1)
        self._as(settlement, 'finance').action_approve('Dual known bases', settlement.revision)
        self.assertEqual(trip.case_status, 'open')
        self._as(settlement, 'finance').action_close('Explicit no-obligation closure', settlement.revision)
        self.assertEqual(trip.case_status, 'workflow_closed')
        self.assertEqual(trip.state, 'preparing')
        self.assertFalse(settlement.cash_event_id)
        self.assertEqual(settlement.accounting_status, 'not_verified')
        with self.assertRaises(ValidationError):
            report.action_revise('Cannot erase the locked zero basis', report.revision)
        self.assertTrue(report.zero_expense_declared)

    def test_03_recorded_advance_requires_full_return_before_closure(self):
        trip, report, advance = self._new(funding=100000)
        original_cash = advance.cash_event_id
        self._ready(report)
        settlement = self._settlement(trip)
        self.assertEqual((settlement.direction, settlement.difference_amount), ('return', -100000))
        settlement.action_submit(1)
        self._as(settlement, 'finance').action_approve('Zero costs, recorded funding', 1)
        with self.assertRaises(ValidationError):
            self._as(settlement, 'finance').action_close('Cannot ignore advance', 1)
        cash = self._as(settlement, 'cash')
        cash.action_start_cash('ZERO-RETURN-ATTEMPT', 'Prepare full return', 1)
        cash.action_record_cash(100000, 'ZERO-RETURN-RECORDED', fields.Date.today(), 1)
        self._as(settlement, 'finance').action_close('Full advance returned', 1)
        self.assertEqual(advance.cash_event_id, original_cash)
        self.assertFalse(report.line_ids)
        self.assertEqual(settlement.remaining_amount, 0)

    def test_04_uncertain_advance_is_not_zero_until_reconciled(self):
        trip, report, advance = self._new(funding=100000, uncertain=True)
        self._ready(report)
        settlement = self._settlement(trip)
        self.assertFalse(settlement.funding_known)
        with self.assertRaises(ValidationError):
            self._as(settlement, 'cash').action_confirm_no_funding('UNKNOWN-NOT-ZERO', 'Cannot assume', 1)
        with self.assertRaises(ValidationError):
            advance.action_cancel('Unknown external payment', 1)
        self._as(advance, 'cash').action_confirm_no_payment('ZERO-NEGATIVE-RECONCILIATION', 'Checked no external execution', 1)
        advance.action_cancel('Known not executed', 1)
        trip.action_no_advance()
        self._as(settlement, 'cash').action_confirm_no_funding('ZERO-FUNDING-AFTER-RECONCILE', 'No funding confirmed', 1)
        self.assertTrue(settlement.funding_known)
        self.assertFalse(advance.cash_event_id)

    def test_05_existing_costs_cannot_be_hidden_by_zero(self):
        trip, report, _ = self._new()
        report.action_add_line('Actual synthetic cost', 1000, fields.Date.today(), 1)
        with self.assertRaises(ValidationError):
            report.action_declare_zero_expenses('Cannot hide a real row', report.revision)
        self.assertEqual(len(report.line_ids), 1)
        self.assertFalse(report.zero_expense_declared)

    def test_06_pending_or_no_cancellation_cannot_declare_zero(self):
        trip = TestTripAdvance._new_trip(self.env, self.users)
        report = self._as(self.env['ps.te.expense.report'], 'owner').create({'trip_id': trip.id})
        with self.assertRaises(ValidationError):
            report.action_declare_zero_expenses('No cancellation', 1)
        trip.action_request_cancellation('Pending manager decision', 1, 0)
        with self.assertRaises(ValidationError):
            report.action_declare_zero_expenses('Not yet cancelled', 1)

    def test_07_role_direct_field_and_default_context_forgery(self):
        trip, report, _ = self._new()
        for role in ('finance', 'manager', 'cash', 'other'):
            with self.assertRaises(AccessError):
                self._as(report, role).action_declare_zero_expenses('Wrong actor', 1)
        report.action_declare_zero_expenses('Owner declaration', 1)
        report.action_submit(report.revision)
        for role in ('owner', 'manager', 'cash', 'other'):
            with self.assertRaises(AccessError):
                self._as(report, role).action_review_zero_expenses('accepted', 'Wrong reviewer', report.revision)
        with self.assertRaises(AccessError):
            report.write({'zero_expense_reviewed_by_id': self.users['owner'].id})
        # Existing reports cannot be duplicated; create a separate cancelled root.
        root = self._as(self.env['ps.te.trip.request'], 'owner').create({'purpose': 'Synthetic forged defaults'})
        root.action_request_cancellation('Cancel', 1, 0)
        self._as(root, 'manager').action_decide_cancellation('approved', 'Cancel', 1)
        safe_report = self._as(self.env['ps.te.expense.report'], 'owner').with_context(
            default_zero_expense_declared=True, default_zero_expense_reviewed_by_id=self.users['finance'].id,
        ).create({'trip_id': root.id})
        self.assertFalse(safe_report.zero_expense_declared)
        self.assertFalse(safe_report.zero_expense_reviewed_by_id)

    def test_08_withdrawal_invalidates_prepared_settlement_and_retains_zero_history(self):
        trip, report, _ = self._new()
        self._ready(report)
        settlement = self._settlement(trip)
        settlement.action_submit(1)
        report.action_revise('Found an employee-paid cost', report.revision)
        self.assertFalse(report.zero_expense_declared)
        self.assertFalse(report.accepted_basis_ready)
        with self.assertRaises(ValidationError):
            self._as(settlement, 'finance').action_approve('Stale zero basis', 1)
        report.action_add_line('Retained actual cost', 1000, fields.Date.today(), report.revision)
        snapshots = report.event_ids.filtered(lambda e: e.event_type == 'zero_accepted')
        self.assertTrue(json.loads(snapshots.zero_expense_snapshot)['declared'])
        self.assertEqual(json.loads(snapshots.zero_expense_snapshot)['reviewed_by'], self.users['finance'].id)

    def test_09_policy_and_finance_revocation_invalidate_zero_readiness(self):
        trip, report, _ = self._new()
        self._ready(report)
        self.assertTrue(report.accepted_basis_ready)
        company = self.env['res.company'].browse(self.company_id)
        original_policy = company.ps_te_expense_policy_reference
        company.ps_te_expense_policy_reference = 'SYNTHETIC-CHANGED-ZERO-POLICY'
        self.assertFalse(report.accepted_basis_ready)
        with self.assertRaises(ValidationError):
            self._settlement(trip)
        self.assertTrue(report.zero_expense_reviewed_by_id)
        company.ps_te_expense_policy_reference = original_policy
        self.assertTrue(report.accepted_basis_ready)
        self.users['finance'].group_ids -= self.env.ref('ps_expenses.group_ps_te_finance')
        self.assertFalse(report.accepted_basis_ready)
        with self.assertRaises(ValidationError):
            self._settlement(trip)

    def test_10_finance_return_needs_fresh_owner_declaration_and_review(self):
        trip, report, _ = self._new()
        report.action_declare_zero_expenses('No costs claimed', 1)
        revision = report.revision
        report.action_submit(revision)
        self._as(report, 'finance').action_review_zero_expenses('returned', 'Clarify absence of costs', revision)
        self.assertFalse(report.accepted_basis_ready)
        report.action_revise('Corrected explanation', revision)
        with self.assertRaises(ValidationError):
            report.action_submit(report.revision)
        self._ready(report)
        self.assertTrue(report.accepted_basis_ready)
        self.assertGreater(report.revision, revision)

    def test_11_prebusiness_route_cannot_introduce_unapproved_costs(self):
        trip, report, _ = self._new(preparing=True)
        with self.assertRaises(ValidationError):
            report.action_add_line('Unapproved business cost', 1000, fields.Date.today(), 1)
        report.action_declare_zero_expenses('No costs', 1)
        with self.assertRaises(ValidationError):
            report.action_add_line('Cannot mix zero and costs', 1000, fields.Date.today(), report.revision)
        report.action_revise('Withdraw accidental draft declaration', report.revision)
        self.assertFalse(report.zero_expense_declared)

    def test_12_native_wizard_and_zero_summary_do_not_need_fake_rows(self):
        trip, report, _ = self._new()
        model = self._as(self.env['ps.te.expense.wizard'], 'owner').with_context(**report.action_open_operation()['context'])
        with Form(model) as wizard:
            wizard.operation = 'zero_declare'
            wizard.reason = 'Synthetic no costs through wizard'
        wizard.record.action_apply()
        report.action_submit(report.revision)
        self._as(report, 'finance').action_review_zero_expenses('accepted', 'Synthetic finance check', report.revision)
        self._as(report, 'finance').action_review_zero_expenses('accepted', 'Synthetic finance check', report.revision)
        result, _ = self._as(self.env['ir.actions.report'], 'finance')._render_qweb_html('ps_expenses.expense_summary', [report.id])
        self.assertIn('Explicit zero-expense declaration reviewed', result.decode())
        self.assertFalse(report.line_ids)

    def test_13_competing_zero_declaration_and_expense_insertion_cannot_mix(self):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            users = {role: env['res.users'].browse(uid) for role, uid in self.race_users.items()}
            trip, report, _ = self._case(env, users)
            report_id = report.id
            cr.commit()
        context = {'allowed_company_ids': [self.race_company]}
        with self.registry.cursor() as zero_cr, self.registry.cursor() as line_cr:
            zero_report = api.Environment(zero_cr, self.race_users['owner'], context)['ps.te.expense.report'].browse(report_id)
            line_report = api.Environment(line_cr, self.race_users['owner'], context)['ps.te.expense.report'].browse(report_id)
            zero_report.action_declare_zero_expenses('Concurrent zero declaration', 1)
            with self.assertRaises(LockError):
                line_report.action_add_line('Concurrent expense', 1000, fields.Date.today(), 1)
            line_cr.rollback()
            zero_cr.commit()
        with self.registry.cursor() as cr:
            report = api.Environment(cr, self.race_users['owner'], context)['ps.te.expense.report'].browse(report_id)
            self.assertFalse(report.line_ids)
            self.assertTrue(report.zero_expense_declared)
            with self.assertRaises(ValidationError):
                report.action_add_line('Cannot mix persisted states', 1000, fields.Date.today(), report.revision)
