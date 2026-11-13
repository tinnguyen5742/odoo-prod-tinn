"""Kiểm tra chỉ dẫn và đối soát; không thay bằng chứng UAT trên trình duyệt."""
from lxml import etree

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged

from .test_settlement import TestSettlement


@tagged('post_install', '-at_install')
class TestWorkflowGuidance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company, users = TestSettlement._fixture(cls.env)
        cls.users = {role: cls.env['res.users'].browse(uid) for role, uid in users.items()}

    def _trip(self):
        return self.env['ps.te.trip.request'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company]).create({
                'purpose': 'Synthetic guidance test', 'destination': 'Synthetic place',
                'start_date': '2026-11-01', 'end_date': '2026-11-02'})

    def test_01_displayed_revision_reconciliation_does_not_submit(self):
        trip = self._trip()
        before = (trip.state, trip.preparing_revision, trip.event_ids.ids)
        result = trip.with_context(expected_preparing_revision=trip.preparing_revision).action_reconcile()
        self.assertEqual(result['ps_te_trip_request_result']['status'], 'unconfirmed')
        self.assertEqual((trip.state, trip.preparing_revision, trip.event_ids.ids), before)
        self.assertIn('lost', trip.workflow_next_step)

    def test_02_reconciliation_preserves_receipt_and_manager_wait(self):
        trip = self._trip()
        trip.action_submit(1)
        before = trip.submission_receipt
        for _ in range(2):
            result = trip.with_context(expected_preparing_revision=1).action_reconcile()
            self.assertEqual(result['ps_te_trip_request_result']['receipt'], before)
        self.assertEqual(len(trip.event_ids.filtered(lambda e: e.event_type == 'submitted')), 1)
        self.assertIn('not approval', trip.workflow_next_step)

    def test_03_returned_revision_is_not_historical_submission(self):
        trip = self._trip()
        trip.action_submit(1)
        receipt = trip.submission_receipt
        trip.with_user(self.users['manager']).action_review('returned', 'Synthetic correction', 1)
        current = trip.with_context(expected_preparing_revision=trip.preparing_revision).action_reconcile()
        self.assertEqual(current['ps_te_trip_request_result']['status'], 'unconfirmed')
        previous = trip.action_reconcile(1)
        self.assertEqual(previous['ps_te_trip_request_result']['receipt'], receipt)
        self.assertEqual(previous['ps_te_trip_request_result']['expected_revision'], 1)

    def test_04_reconciliation_still_checks_current_owner_and_membership(self):
        trip = self._trip()
        with self.assertRaises(AccessError):
            trip.with_user(self.users['other']).action_reconcile(1)
        employee = trip.sudo().employee_id
        employee.active = False
        with self.assertRaises(AccessError):
            trip.action_reconcile(1)

    def test_05_guidance_prioritizes_uncertain_cash_and_hold(self):
        settlement, report, advance = TestSettlement._case(self.env, self.users, accepted=150000)
        settlement.action_submit(settlement.revision)
        settlement.with_user(self.users['finance']).action_approve('Synthetic approval', settlement.revision)
        settlement.with_user(self.users['cash']).action_start_cash('SYN-GUIDANCE-ATTEMPT', 'Synthetic preparation', settlement.revision)
        self.assertIn('lost response', settlement.workflow_next_step)
        self.assertIn('locked', report.workflow_next_step)
        case = self.env['ps.te.correction'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company]).create({
                'trip_id': settlement.trip_id.id, 'category': 'funding',
                'description': 'Synthetic uncertainty investigation',
                'expected_revision': settlement.trip_id.preparing_revision})
        self.assertTrue(case.active_trip_id)
        self.assertIn('reconcile the existing', settlement.workflow_next_step)
        self.assertIn('hold', settlement.trip_id.workflow_next_step)
        self.assertIn('held or cancelled', advance.workflow_next_step)

    def test_06_unknown_funding_and_balanced_closure_remain_explicit(self):
        unknown, _, _ = TestSettlement._case(self.env, self.users, funding=None)
        self.assertIn('No-advance intent alone is insufficient', unknown.workflow_next_step)
        balanced, _, _ = TestSettlement._case(self.env, self.users)
        balanced.action_submit(balanced.revision)
        finance = balanced.with_user(self.users['finance'])
        finance.action_approve('Synthetic approval', balanced.revision)
        self.assertIn('explicitly close', balanced.workflow_next_step)
        finance.action_close('Synthetic resolved obligations', balanced.revision)
        self.assertIn('not verified', balanced.workflow_next_step)
        self.assertIn('not verified', balanced.trip_id.workflow_next_step)

    def test_07_native_form_metadata_contains_guidance_and_exact_revision_button(self):
        forms = [('ps.te.trip.request', 'view_ps_te_trip_request_form', 'owner'),
                 ('ps.te.trip.advance', 'view_ps_te_advance_form', 'cash'),
                 ('ps.te.expense.report', 'view_ps_te_expense_form', 'finance'),
                 ('ps.te.settlement', 'view_ps_te_settlement_form', 'finance')]
        for model, view, role in forms:
            actor = self.users[role]
            metadata = self.env[model].with_user(actor).with_context(allowed_company_ids=[self.company]).get_view(
                self.env.ref('ps_expenses.' + view).id, 'form')
            arch = etree.fromstring(metadata['arch'])
            self.assertEqual(len(arch.xpath('//field[@name="workflow_next_step"]')), 1)
            if model == 'ps.te.trip.request':
                button = arch.xpath('//button[@name="action_reconcile"]')[0]
                self.assertIn('expected_preparing_revision', button.get('context'))
        # Native server-side form load, not a claim of browser rendering/UAT.
        with Form(self._trip()) as form:
            self.assertIn('Owner:', form.workflow_next_step)

    def test_08_vietnamese_guidance_and_button(self):
        self.env['res.lang']._activate_lang('vi_VN')
        self.env['ir.module.module'].search([('name', '=', 'ps_te_trip_request')])._update_translations(['vi_VN'], overwrite=True)
        trip = self._trip().with_context(lang='vi_VN')
        self.assertIn('mất phản hồi', trip.workflow_next_step)
        self.assertEqual(trip.fields_get(['workflow_next_step'])['workflow_next_step']['string'], 'Bước tiếp theo')
        view = trip.get_view(self.env.ref('ps_expenses.view_ps_te_trip_request_form').id, 'form')
        self.assertIn('Kiểm tra phiên gửi đang hiển thị', view['arch'])

    def test_09_open_actions_check_roles_and_reuse_existing_records(self):
        trip = self._trip()
        with self.assertRaises(ValidationError):
            trip.action_open_expenses()
        trip.action_submit(1)
        manager = trip.with_user(self.users['manager'])
        wizard = manager.action_open_review_wizard()
        self.assertEqual(wizard['context']['default_request_id'], trip.id)
        self.assertEqual(wizard['context']['default_expected_revision'], 1)
        with self.assertRaises(AccessError):
            trip.action_open_review_wizard()
        manager.action_review('approved', 'Synthetic UI entry', 1)
        action = trip.action_open_expenses()
        self.assertEqual(action['res_model'], 'hr.expense')
        self.assertEqual(trip.action_open_expenses()['domain'], action['domain'])
        with self.assertRaises(AccessError):
            trip.with_user(self.users['other']).action_open_expenses()
        settlement, _, _ = TestSettlement._case(self.env, self.users)
        owner_trip = settlement.trip_id.with_user(self.users['owner'])
        self.assertEqual(owner_trip.action_open_settlement()['res_id'], settlement.id)
        self.assertEqual(owner_trip.action_open_settlement()['res_id'], settlement.id)
        with self.assertRaises(AccessError):
            owner_trip.with_user(self.users['other']).action_open_settlement()

    def test_10_notification_refreshes_native_controller_without_changing_receipt_contract(self):
        trip = self._trip()
        uncertain = trip.action_reconcile(1)
        self.assertEqual(uncertain['params']['next'], {'type': 'ir.actions.client', 'tag': 'soft_reload'})
        self.assertEqual(trip.state, 'preparing')
        confirmed = trip.action_submit(1)
        self.assertEqual(confirmed['params']['next']['tag'], 'soft_reload')
        self.assertEqual(confirmed['ps_te_trip_request_result']['receipt'], trip.submission_receipt)
        for xmlid in ('view_ps_te_trip_request_form', 'view_ps_te_advance_form',
                      'view_ps_te_expense_form', 'view_ps_te_settlement_form'):
            view = self.env.ref('ps_expenses.' + xmlid)
            arch = etree.fromstring(view.arch_db)
            self.assertEqual(arch.xpath('//field[@name="workflow_next_step"]/..')[0].get('col'), '1')
        trip_view = etree.fromstring(self.env.ref('ps_expenses.view_ps_te_trip_request_form').arch_db)
        self.assertIn('not is_current_owner', trip_view.xpath('//button[@name="action_submit"]')[0].get('invisible'))
        for field in ('purpose', 'destination', 'start_date', 'end_date'):
            self.assertIn('not is_current_owner', trip_view.xpath('//field[@name="' + field + '"]')[0].get('readonly'))

    def test_11_history_labels_are_vietnamese_without_rewriting_audit_facts(self):
        self.env['res.lang']._activate_lang('vi_VN')
        self.env['ir.module.module'].search([('name', '=', 'ps_te_trip_request')])._update_translations(['vi_VN'], overwrite=True)
        settlement, report, _ = TestSettlement._case(self.env, self.users)
        event = settlement.event_ids[0]
        before = (event.event_type, event.reason, event.snapshot)
        self.assertEqual(event.with_context(lang='vi_VN').event_label, 'Đã chuẩn bị cơ sở quyết toán')
        self.assertEqual((event.event_type, event.reason, event.snapshot), before)
        self.assertIn('Đã', report.event_ids[0].with_context(lang='vi_VN').event_label)
        correction = self.env['ps.te.correction'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company]).create({'trip_id': settlement.trip_id.id,
                'category': 'basis', 'description': 'Synthetic event language check',
                'expected_revision': settlement.trip_id.preparing_revision})
        self.assertEqual(correction.event_ids[0].with_context(lang='vi_VN').event_label, 'Đã mở hồ sơ sửa sai')

    def test_12_history_display_is_not_an_authority_or_editable_audit_field(self):
        settlement, _, _ = TestSettlement._case(self.env, self.users)
        event = settlement.event_ids[0]
        with self.assertRaises(AccessError):
            event.with_user(self.users['finance']).write({'event_label': 'Approved'})
        unknown = self.env['ps.te.settlement.event'].new({'event_type': 'future_unknown_code'})
        self.assertEqual(unknown.event_label, 'Unrecognized history event; inspect the retained code.')
        self.assertFalse(unknown._fields['event_label'].store)

    def test_13_cancelled_prebusiness_case_exposes_native_obligation_entry_points(self):
        from .test_zero_expenses import TestCancelledZeroExpenses
        trip, report, _ = TestCancelledZeroExpenses._case(self.env, self.users, preparing=True)
        self.assertEqual(trip.state, 'preparing')
        self.assertEqual(trip.cancellation_status, 'approved')
        action = trip.action_open_expenses()
        self.assertEqual((action['res_model'], action['res_id']), ('ps.te.expense.report', report.id))
        self.assertFalse(report.zero_expense_declared)
        trip.action_no_advance()
        arch = etree.fromstring(self.env.ref('ps_expenses.view_ps_te_trip_request_form').arch_db)
        for name in ('action_open_expenses', 'action_open_settlement', 'action_no_advance'):
            condition = arch.xpath('//button[@name="' + name + '"]')[0].get('invisible')
            self.assertIn("cancellation_status != 'approved'", condition)
            self.assertIn('owner_id != uid', condition)
        # Exposing the entry does not manufacture a reviewed zero basis.
        with self.assertRaises(ValidationError):
            trip.action_open_settlement()
        merged = etree.fromstring(trip.get_view(
            self.env.ref('ps_expenses.view_ps_te_trip_request_form').id, 'form')['arch'])
        self.assertIn('not is_current_owner', merged.xpath('//button[@name="action_submit"]')[0].get('invisible'))
        for field in ('purpose', 'destination', 'start_date', 'end_date'):
            self.assertIn('not is_current_owner', merged.xpath('//field[@name="' + field + '"]')[0].get('readonly'))
        self.assertTrue(trip.is_current_owner)
        self.assertFalse(trip.with_user(self.users['manager']).is_current_owner)
