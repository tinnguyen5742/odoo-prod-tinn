from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from .test_settlement import TestSettlement


@tagged('post_install', '-at_install')
class TestVietnameseWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['res.lang']._activate_lang('vi_VN')
        cls.env['ir.module.module'].search([('name', '=', 'ps_te_trip_request')])._update_translations(['vi_VN'], overwrite=True)
        company, users = TestSettlement._fixture(cls.env)
        cls.company_id = company
        cls.users = {role: cls.env['res.users'].browse(uid) for role, uid in users.items()}

    def _vi(self, record):
        return record.with_user(self.users['owner']).with_context(lang='vi_VN', allowed_company_ids=[self.company_id])

    def test_01_menu_field_selection_and_operation_translation(self):
        menu = self.env.ref('ps_expenses.menu_ps_te_settlements').with_context(lang='vi_VN')
        self.assertEqual(menu.name, 'Quyết toán')
        model = self._vi(self.env['ps.te.settlement'])
        metadata = model.fields_get(['remaining_amount', 'state', 'accounting_status'])
        self.assertEqual(metadata['remaining_amount']['string'], 'Nghĩa vụ tiền còn lại')
        self.assertIn(('closed', 'Đã đóng quy trình — kế toán riêng biệt'), metadata['state']['selection'])
        self.assertEqual(metadata['accounting_status']['selection'][0][1], 'Kế toán bên ngoài chưa được xác minh')
        choices = self._vi(self.env['ps.te.settlement.wizard']).fields_get(['operation'])['operation']['selection']
        self.assertIn(('record', 'Ghi nhận thu chi bên ngoài'), choices)

    def test_02_native_errors_use_request_language_without_changing_rules(self):
        advance = self._vi(self.env['ps.te.trip.advance'])
        with self.assertRaises(ValidationError) as failure:
            advance._amount(-1)
        self.assertIn('Nhập số nguyên VND dương', str(failure.exception))
        with self.assertRaises(ValidationError) as failure:
            advance._text('', 'tham chiếu')
        self.assertEqual(str(failure.exception), 'Cần nhập tham chiếu.')
        with self.assertRaises(ValidationError) as failure:
            self._vi(self.env['ps.te.cash.event'])._amount('bad')
        self.assertIn('Nhập số thu chi nguyên VND dương', str(failure.exception))

    def test_03_vietnamese_html_preserves_unknown_and_finance_warning(self):
        settlement, report, _ = TestSettlement._case(self.env, self.users, funding=None)
        renderer = self._vi(self.env['ir.actions.report'])
        rendered, _ = renderer._render_qweb_html('ps_expenses.settlement_summary', [settlement.id])
        text = rendered.decode()
        self.assertIn('Tổng hợp quyết toán đã ghi nhận', text)
        self.assertIn('Cơ sở so sánh chưa xác nhận hoặc đã cũ', text)
        self.assertIn('Kế toán bên ngoài chưa được xác minh', text)
        self.assertNotIn('id="current-comparison"', text)
        expense, _ = renderer._render_qweb_html('ps_expenses.expense_summary', [report.id])
        self.assertIn('Tổng hợp duyệt chi phí', expense.decode())

    def test_04_cancellation_labels_errors_and_summary_are_vietnamese(self):
        settlement, report, _ = TestSettlement._case(self.env, self.users)
        trip = self._vi(settlement.trip_id)
        trip.action_request_cancellation('Synthetic Vietnamese cancellation', trip.preparing_revision, 0)
        self.assertIn('Quản lý được phân công', trip.cancellation_next_step)
        with self.assertRaises(ValidationError) as failure:
            trip.action_submit(trip.preparing_revision)
        self.assertIn('Yêu cầu hủy đang chờ', str(failure.exception))
        output, _ = self._vi(self.env['ir.actions.report'])._render_qweb_html(
            'ps_expenses.settlement_summary', [settlement.id])
        self.assertIn('Yêu cầu hủy chờ quản lý duyệt', output.decode())

    def test_05_zero_expense_review_and_saved_kind_are_vietnamese(self):
        from .test_zero_expenses import TestCancelledZeroExpenses
        trip, report, _ = TestCancelledZeroExpenses._case(self.env, self.users, preparing=True)
        report = self._vi(report)
        report.action_declare_zero_expenses('Synthetic no costs', report.revision)
        report.action_submit(report.revision)
        report.with_user(self.users['finance']).action_review_zero_expenses('accepted', 'Synthetic finance check', report.revision)
        renderer = self._vi(self.env['ir.actions.report'])
        result, _ = renderer._render_qweb_html('ps_expenses.expense_summary', [report.id])
        self.assertIn('Đã duyệt khai báo không phát sinh chi phí', result.decode())
        self.assertEqual(report.fields_get(['state'])['state']['selection'][-1][1], 'Đã duyệt cơ sở chi phí')
        settlement = self._vi(self.env['ps.te.settlement']).create({'trip_id': trip.id})
        saved, _ = renderer._render_qweb_html('ps_expenses.settlement_summary', [settlement.id])
        self.assertIn('Duyệt khai báo rõ không phát sinh chi phí', saved.decode())
        self.assertFalse(report.line_ids)

    def test_06_correction_hold_and_no_change_workflow_are_vietnamese(self):
        settlement, report, _ = TestSettlement._case(self.env, self.users)
        trip = self._vi(settlement.trip_id)
        correction = self._vi(self.env['ps.te.correction']).create({
            'trip_id': trip.id, 'category': 'basis', 'description': 'Synthetic Vietnamese investigation',
            'expected_revision': trip.preparing_revision,
        })
        self.assertTrue(trip.correction_hold)
        with self.assertRaises(ValidationError) as failure:
            self._vi(report).action_revise('Synthetic hold check', report.revision)
        self.assertIn('Hồ sơ sửa sai đang mở', str(failure.exception))
        rendered, _ = self._vi(self.env['ir.actions.report'])._render_qweb_html(
            'ps_expenses.settlement_summary', [settlement.id])
        self.assertIn('Đang tạm giữ để xử lý sửa sai', rendered.decode())
        for model in ('ps.te.expense.report', 'ps.te.settlement'):
            self.assertEqual(self._vi(self.env[model]).fields_get(['correction_hold'])['correction_hold']['string'],
                             'Đang tạm giữ để xử lý sửa sai')
        finance = correction.with_user(self.users['finance'])
        finance.action_propose_no_change('SYNTHETIC-VI-FINANCE', 'No change needed', correction.revision)
        correction.with_user(self.users['cash']).action_confirm_no_change('SYNTHETIC-VI-CASH', 'Confirmed same source', correction.revision)
        finance.action_resolve_no_change('No source data changed', correction.revision)
        label = dict(correction.fields_get(['state'])['state']['selection'])[correction.state]
        self.assertEqual(label, 'Đã giải quyết việc kiểm tra — không đổi nguồn')

    def test_07_catalog_covers_native_exported_addon_terms(self):
        from odoo.tools import file_open
        from odoo.tools.translate import TranslationModuleReader
        import polib
        with file_open('ps_expenses/i18n/vi.po', 'rb') as stream:
            entries = polib.pofile(stream.read().decode('utf-8'))
        translations = {item.msgid: item.msgstr for item in entries if not item.obsolete}
        sources = {row[4] for row in TranslationModuleReader(self.env.cr, modules=['ps_te_trip_request'], lang=None)}
        self.assertTrue(sources)
        self.assertFalse([source for source in sources if not translations.get(source)])
        # Accounting labels must not translate an unverified fact into completion.
        self.assertIn('chưa được xác minh', translations['External Accounting Not Verified'])

    def test_08_catalog_binds_every_native_entity_occurrence_not_only_source_words(self):
        from odoo.tools import file_open
        from odoo.tools.translate import TranslationModuleReader
        import polib
        with file_open('ps_expenses/i18n/vi.po', 'rb') as stream:
            entries = {entry.msgid: entry for entry in polib.pofile(stream.read().decode('utf-8')) if not entry.obsolete}
        for module, kind, name, record, source, translated, comments in TranslationModuleReader(
                self.env.cr, modules=['ps_te_trip_request'], lang=None):
            ref = f'code:{name}:{record}' if kind == 'code' else f'{kind}:{name}:{record}'
            entry = entries[source]
            refs = {name + (':' + line if line else '') for name, line in entry.occurrences}
            if kind == 'code':
                # Dòng Python thay đổi khi thêm code; Odoo bind theo tệp/term,
                # không theo số dòng. Entity model/view thì phải khớp đầy đủ.
                self.assertIn('code:' + name, {path for path, line in entry.occurrences}, source)
                self.assertIn('odoo-python', entry.comment)
            else:
                self.assertIn(ref, refs, source)

    def test_09_all_native_operation_wizards_share_vietnamese_fields_and_buttons(self):
        from lxml import etree
        for model, xmlid in (
            ('ps.te.trip.cancellation.wizard', 'view_trip_cancellation_wizard'),
            ('ps.te.correction.wizard', 'view_correction_wizard'),
            ('ps.te.advance.wizard', 'view_ps_te_advance_wizard'),
            ('ps.te.expense.wizard', 'view_ps_te_expense_wizard'),
            ('ps.te.settlement.wizard', 'view_ps_te_settlement_wizard'),
            ('ps.te.cash.rectification.wizard', 'view_cash_rectification_wizard'),
            ('ps.te.adjustment.wizard', 'view_financial_adjustment_wizard'),
        ):
            wizard = self._vi(self.env[model])
            metadata = wizard.fields_get(['operation', 'reason', 'expected_revision'])
            self.assertEqual(metadata['operation']['string'], 'Thao tác', model)
            self.assertEqual(metadata['reason']['string'], 'Lý do', model)
            self.assertEqual(metadata['expected_revision']['string'], 'Phiên bản đang thao tác', model)
            view = wizard.get_view(self.env.ref('ps_expenses.' + xmlid).id, 'form')
            arch = etree.fromstring(view['arch'])
            self.assertEqual(arch.xpath('//button[@name="action_apply"]')[0].get('string'), 'Thực hiện', model)
            self.assertEqual(arch.xpath('//button[@special="cancel"]')[0].get('string'), 'Hủy', model)
