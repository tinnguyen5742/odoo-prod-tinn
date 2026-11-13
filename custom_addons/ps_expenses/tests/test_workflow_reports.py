from lxml import html

from odoo import api, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, HttpCase, tagged

from .test_settlement import TestSettlement


@tagged('post_install', '-at_install')
class TestWorkflowReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company_id, users = TestSettlement._fixture(cls.env)
        cls.company_id = company_id
        cls.users = {role: cls.env['res.users'].browse(uid) for role, uid in users.items()}

    def _new(self, funding=100000):
        return TestSettlement._case(self.env, self.users, accepted=150000, funding=funding)

    def _render(self, template, record, role='owner', data=None):
        result, kind = self.env['ir.actions.report'].with_user(self.users[role]).with_context(
            allowed_company_ids=[self.company_id],
        )._render_qweb_html('ps_expenses.' + template, [record.id], data=data)
        self.assertEqual(kind, 'html')
        return result.decode()

    def test_01_summary_allowed_roles_and_no_proof_leak(self):
        settlement, report, advance = self._new()
        for role in ('owner', 'finance', 'cash'):
            rendered = self._render('settlement_summary', settlement, role)
            self.assertIn(settlement.reference, rendered)
            self.assertNotIn(report.line_ids[0].description, rendered)
            self.assertNotIn(report.line_ids[0].evidence_ids.filename, rendered)
        for role in ('owner', 'finance'):
            self.assertIn(report.line_ids[0].description, self._render('expense_summary', report, role))
        for role in ('other', 'manager'):
            with self.assertRaises(AccessError):
                self._render('settlement_summary', settlement, role)
        with self.assertRaises(AccessError):
            self._render('expense_summary', report, 'cash')

    def test_02_unknown_and_stale_basis_do_not_print_final_zero(self):
        settlement, report, advance = self._new(funding=None)
        doc = html.fromstring(self._render('settlement_summary', settlement))
        self.assertFalse(doc.xpath('//*[@id="current-comparison"]'))
        self.assertIn('Unconfirmed or stale comparison basis', doc.text_content())
        settlement2, report2, advance2 = self._new()
        report2.action_revise('Synthetic changed basis', report2.revision)
        self.assertNotIn('id="current-comparison"', self._render('settlement_summary', settlement2))
        self.assertIn('Not a final accepted basis', self._render('expense_summary', report2))

    def test_03_input_escape_and_no_attachment_side_effect(self):
        settlement, report, advance = self._new()
        settlement.action_submit(1)
        settlement.with_user(self.users['finance']).action_approve('<script>bad()</script>', 1)
        before = self.env['ir.attachment'].search_count([])
        rendered = self._render('settlement_summary', settlement)
        self.assertNotIn('<script>bad()</script>', rendered)
        self.assertIn('&lt;script&gt;bad()', rendered)
        self.assertEqual(self.env['ir.attachment'].search_count([]), before)
        self.assertEqual(settlement.state, 'approved')
        self.assertFalse(self.env.ref('ps_expenses.action_settlement_summary').attachment_use)

    def test_04_mixed_batch_and_forged_data_cannot_replace_scope(self):
        settlement, report, advance = self._new()
        company, users = TestSettlement._fixture(self.env)
        foreign_users = {role: self.env['res.users'].browse(uid) for role, uid in users.items()}
        foreign, foreign_report, _ = TestSettlement._case(self.env, foreign_users)
        renderer = self.env['report.ps_expenses.settlement_summary'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id],
        )
        with self.assertRaises(AccessError):
            renderer._get_report_values([settlement.id, foreign.id])
        for invalid in ([], [True], [-1], ['1'], list(range(1, 102))):
            with self.assertRaises(ValidationError):
                renderer._get_report_values(invalid)
        values = renderer._get_report_values([settlement.id], {'docs': foreign, 'basis_current': {settlement.id: False}})
        self.assertEqual(values['docs'], settlement.with_env(renderer.env))
        self.assertTrue(values['basis_current'][settlement.id])

    def test_05_recorded_cash_and_accounting_remain_separate(self):
        settlement, report, advance = self._new()
        settlement.action_submit(1)
        settlement.with_user(self.users['finance']).action_approve('Synthetic approval', 1)
        cash = settlement.with_user(self.users['cash'])
        cash.action_start_cash('SYNTHETIC-REPORT-ATTEMPT', 'Prepare externally', 1)
        cash.action_record_cash(50000, 'SYNTHETIC-REPORT-TOPUP', fields.Date.today(), 1)
        settlement.with_user(self.users['finance']).action_close('Synthetic explicit closure', 1)
        rendered = self._render('settlement_summary', settlement, 'cash')
        self.assertIn('SYNTHETIC-REPORT-TOPUP', rendered)
        self.assertIn('External Accounting Not Verified', rendered)
        self.assertIn('Workflow Closed', rendered)


@tagged('post_install', '-at_install')
class TestWorkflowReportHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company, users = TestSettlement._fixture(cls.env)
        cls.users = {role: cls.env['res.users'].browse(uid) for role, uid in users.items()}
        for role in ('owner', 'cash', 'other'):
            cls.users[role].password = 'synthetic-report-only'
        cls.settlement, cls.report, _ = TestSettlement._case(cls.env, cls.users)

    def test_http_summary_requires_role_and_expense_report_remains_private(self):
        for role, allowed in (('owner', True), ('cash', True), ('other', False)):
            user = self.users[role]
            self.authenticate(user.login, 'synthetic-report-only')
            response = self.url_open('/report/html/ps_expenses.settlement_summary/%s' % self.settlement.id)
            if allowed:
                self.assertEqual(response.status_code, 200)
                self.assertIn(self.settlement.reference, response.text)
            else:
                self.assertIn(response.status_code, (403, 404))
                self.assertNotIn(self.settlement.reference, response.text)
        self.authenticate(self.users['cash'].login, 'synthetic-report-only')
        response = self.url_open('/report/html/ps_expenses.expense_summary/%s' % self.report.id)
        self.assertIn(response.status_code, (403, 404))
        self.assertNotIn(self.report.line_ids[0].description, response.text)
