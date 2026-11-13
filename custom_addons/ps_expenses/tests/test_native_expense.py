import base64
import uuid

from odoo import fields, Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged

from .test_settlement import TestSettlement
from .test_advance import TestTripAdvance


@tagged('post_install', '-at_install')
class TestNativeExpenseIntegration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company, actors = TestSettlement._fixture(cls.env)
        cls.company = cls.env['res.company'].browse(company)
        cls.users = {role: cls.env['res.users'].browse(uid) for role, uid in actors.items()}

    def _draft(self):
        trip = TestTripAdvance._new_trip(self.env, self.users)
        trip.action_no_advance()
        report = self.env['ps.te.expense.report'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company.id]).create({'trip_id': trip.id})
        return trip, report

    def _line(self, report, amount=100000, proof=True):
        line = self.env['ps.te.expense.line'].with_user(self.users['owner']).browse(
            report.action_add_line('Native integration claim', amount, fields.Date.today(), report.revision))
        if proof:
            raw = b'%PDF-1.4\n' + uuid.uuid4().hex.encode() + b'\n%%EOF'
            report.action_upload_evidence(line.id, 'native.pdf', base64.b64encode(raw), report.revision)
        return line

    def test_01_one_native_source_projection_and_actual_native_states(self):
        trip, report = self._draft()
        line = self._line(report)
        native = line.native_expense_id
        self.assertEqual(native._table, 'hr_expense')
        self.assertEqual((native.ps_report_id, native.ps_line_id, native.ps_trip_id), (report, line, trip))
        for name in ('description', 'expense_date', 'claimed_amount', 'decision', 'accepted_amount'):
            self.assertTrue(line._fields[name].related)
            self.assertFalse(line._fields[name].store)
        report.action_submit(report.revision)
        self.assertEqual(native.state, 'submitted')
        report.with_user(self.users['finance']).action_review_line(line.id, 'accepted', 'Native accepted80', 80000, report.revision)
        self.assertEqual((native.state, native.total_amount_currency, native.ps_accepted_amount,
            native.ps_refused_amount, report.accepted_total), ('approved', 100000, 80000, 20000, 80000))
        self.assertTrue(report.accepted_basis_ready)
        self.assertEqual(line.evidence_ids.attachment_id.res_model, 'hr.expense')
        self.assertEqual(line.evidence_ids.attachment_id.res_id, native.id)

    def test_02_native_form_creation_and_canonical_trip_entry(self):
        trip, report = self._draft()
        action = trip.action_open_expenses()
        self.assertEqual(action['res_model'], 'hr.expense')
        model = self.env['hr.expense'].with_user(self.users['owner']).with_context(
            **action['context'], allowed_company_ids=[self.company.id])
        with Form(model, view='hr_expense.hr_expense_view_form') as form:
            form.name = 'Created in actual inherited Expenses form'
            form.total_amount_currency = 100000
        native = form.record
        self.assertEqual(native.ps_report_id, report)
        self.assertEqual(report.line_ids.native_expense_id, native)
        self.assertEqual(native.manager_id, self.users['finance'])
        view = native.get_view(self.env.ref('hr_expense.hr_expense_view_form').id, 'form')
        self.assertIn('hr_expense_form_view', view['arch'])
        self.assertIn('action_ps_operation', view['arch'])

    def test_03_native_default_and_direct_forgery_are_not_capabilities(self):
        trip, report = self._draft()
        line = self._line(report)
        native = line.native_expense_id
        for values in ({'ps_accepted_amount': 999999}, {'ps_report_id': False}, {'approval_state': 'approved'},
                       {'account_move_id': 1}, {'total_amount_currency': 1}, {'name': 'Unversioned edit'}):
            with self.assertRaises(AccessError):
                native.with_context(_ps_native=True, default_ps_decision='accepted').write(values)
        self.assertEqual(native.total_amount_currency, 100000)
        with self.assertRaises(AccessError):
            self.env['hr.expense'].with_user(self.users['owner']).with_context(
                default_ps_report_id=report.id).create({'name': 'Forged approved claim',
                    'date': fields.Date.today(), 'total_amount_currency': 100000, 'approval_state': 'approved'})

    def test_04_native_generic_approve_post_pay_copy_delete_and_upload_are_held(self):
        trip, report = self._draft()
        native = self._line(report).native_expense_id
        for action in (native.action_approve, native.action_pay, native.action_post,
                       native.action_reset, native.action_refuse, native.action_split_wizard):
            with self.assertRaises(ValidationError):
                action()
        for action in (native.copy, native.unlink):
            with self.assertRaises(AccessError):
                action()
        with self.assertRaises(AccessError):
            native.attach_document(attachment_ids=[])
        self.assertFalse(native.account_move_id)

    def test_05_ps_native_privacy_survives_broad_native_manager_group(self):
        trip, report = self._draft()
        native = self._line(report).native_expense_id
        self.users['manager'].group_ids += self.env.ref('hr_expense.group_hr_expense_manager')
        for role in ('manager', 'cash', 'other'):
            with self.assertRaises(AccessError):
                native.with_user(self.users[role]).read(['total_amount_currency', 'ps_accepted_amount'])
        for role in ('owner', 'finance'):
            self.assertEqual(native.with_user(self.users[role]).read(['total_amount_currency'])[0]['total_amount_currency'], 100000)

    def test_06_revision_resets_native_approval_without_erasing_ps_history(self):
        trip, report = self._draft()
        line = self._line(report)
        report.action_submit(report.revision)
        report.with_user(self.users['finance']).action_review_line(line.id, 'accepted', 'Before revision', 80000, report.revision)
        old_revision = report.revision
        report.action_revise('Owner withdraws reviewed basis', report.revision)
        self.assertEqual((line.native_expense_id.state, line.accepted_amount, line.decision), ('draft', 0, 'pending'))
        self.assertTrue(report.event_ids.filtered(lambda event: event.event_type == 'line_accepted'))
        with self.assertRaises(ValidationError):
            report.action_edit_line(line.id, 'Old window', 1, fields.Date.today(), old_revision)
        report.action_edit_line(line.id, 'Native corrected description', 90000, fields.Date.today(), report.revision)
        self.assertEqual(line.native_expense_id.total_amount_currency, 90000)
        self.assertEqual(line.native_expense_id.name, 'Native corrected description')

    def test_07_legacy_unbound_claim_never_becomes_zero_ready_basis(self):
        trip, report = self._draft()
        line = self._line(report)
        self.env.cr.execute('UPDATE ps_te_expense_line SET native_expense_id=NULL WHERE id=%s', [line.id])
        self.env.invalidate_all()
        self.assertFalse(report.native_source_ready)
        self.assertFalse(report.accepted_basis_ready)
        with self.assertRaises(ValidationError):
            report.action_submit(report.revision)

    def test_08_unrelated_native_create_defaults_and_autoapproval_unchanged(self):
        native = self.env['hr.expense'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company.id], default_name='Ordinary native claim',
            default_product_id=self.env.ref('ps_expenses.product_ps_native_expense').id,
            default_total_amount_currency=100000).create({})
        self.assertFalse(native.ps_report_id)
        self.assertEqual(native.name, 'Ordinary native claim')
        native.write({'name': 'Ordinary editable claim'})
        self.assertEqual(native.name, 'Ordinary editable claim')
        with Form(native, view='hr_expense.hr_expense_view_form') as form:
            form.name = 'Ordinary native form edit'
        self.assertEqual(native.name, 'Ordinary native form edit')

    def test_09_settlement_uses_native_acceptance_not_native_claim_or_paid_flag(self):
        settlement, report, _ = TestSettlement._case(self.env, self.users)
        native = report.line_ids.native_expense_id
        self.assertTrue(native)
        self.assertEqual(sum(native.mapped('total_amount_currency')), report.claimed_total)
        self.assertEqual(sum(native.mapped('ps_accepted_amount')), settlement.accepted_amount)
        self.assertFalse(native.account_move_id)
        self.assertNotIn('paid', native.mapped('state'))

    def test_10_native_creation_rejects_stale_or_missing_observed_revision(self):
        trip, report = self._draft()
        seen = report.revision
        self._line(report, proof=False)
        before = self.env['hr.expense'].search_count([('ps_report_id', '=', report.id)])
        native = self.env['hr.expense'].with_user(self.users['owner']).with_context(
            default_ps_report_id=report.id, allowed_company_ids=[self.company.id])
        for revision in (None, seen, str(report.revision), True):
            with self.assertRaises(ValidationError):
                native.create({'name': 'Stale native draft', 'date': fields.Date.today(),
                    'total_amount_currency': 100000, 'ps_expected_revision': revision})
        self.assertEqual(self.env['hr.expense'].search_count([('ps_report_id', '=', report.id)]), before)

    def test_11_all_duplicated_native_mutation_buttons_are_hidden_for_ps(self):
        from lxml import etree
        trip, report = self._draft()
        native = self._line(report).native_expense_id
        for role in ('owner', 'finance'):
            view = native.with_user(self.users[role]).get_view(self.env.ref('hr_expense.hr_expense_view_form').id, 'form')
            arch = etree.fromstring(view['arch'])
            for name in ('action_submit', 'action_approve', 'action_post', 'action_reset', 'action_refuse', 'action_split_wizard'):
                for button in arch.xpath('//button[@name="' + name + '"]'):
                    self.assertIn('ps_report_id', button.get('invisible', ''), (role, name))
            for widget in arch.xpath('//widget[@name="attach_document"]'):
                self.assertIn('ps_report_id', widget.get('invisible', ''))

    def test_12_r1_f01_reassigned_finance_opens_exact_historical_duplicate(self):
        trip, report = self._draft()
        old = self._line(report).native_expense_id
        report.action_submit(report.revision)
        replacement = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Synthetic replacement finance', 'login': 'replacement.' + uuid.uuid4().hex + '@example.invalid',
            'company_id': self.company.id, 'company_ids': [Command.set(self.company.ids)],
            'group_ids': [Command.set([self.env.ref('base.group_user').id,
                self.env.ref('ps_expenses.group_ps_te_finance').id])]})
        self.company.ps_te_finance_reviewer_id = replacement
        owner_ctx = {'allowed_company_ids': self.company.ids}
        correction = self.env['ps.te.correction'].with_user(self.users['owner']).with_context(**owner_ctx).create({
            'trip_id': trip.id, 'category': 'authority', 'description': 'Synthetic finance replacement',
            'expected_revision': trip.preparing_revision})
        adjustment = self.env['ps.te.adjustment'].with_user(self.users['owner']).with_context(**owner_ctx).create({
            'correction_id': correction.id, 'reason': 'Synthetic current finance basis',
            'expected_revision': correction.revision})
        adjustment.action_copy_previous_basis('Synthetic exact carry, no amount workaround', adjustment.revision)
        current = adjustment.report_id.line_ids.native_expense_id.with_user(replacement).with_context(**owner_ctx)
        self.assertEqual(current.total_amount_currency, old.total_amount_currency)
        self.assertFalse(current.duplicate_expense_ids)
        self.assertFalse(current.same_receipt_expense_ids)
        with Form(current, view='hr_expense.hr_expense_view_form') as form:
            self.assertEqual(form.total_amount_currency, 100000)
        with self.assertRaises(AccessError):
            old.with_user(replacement).with_context(**owner_ctx).read(['name'])
        self.assertEqual(old.sudo().total_amount_currency, 100000)

    def test_13_r1_f01_ordinary_native_collision_hides_private_claim_and_keeps_visible_duplicates(self):
        trip, report = self._draft()
        private = self._line(report).native_expense_id
        manager = self.users['manager']
        manager.group_ids += self.env.ref('hr_expense.group_hr_expense_manager')
        model = self.env['hr.expense'].with_user(manager).with_context(allowed_company_ids=self.company.ids)
        vals = {'name': 'Synthetic ordinary collision', 'product_id': private.product_id.id,
            'employee_id': private.employee_id.id, 'company_id': self.company.id,
            'date': private.date, 'currency_id': private.currency_id.id, 'total_amount_currency': 100000}
        first = model.create(vals)
        self.assertFalse(first.duplicate_expense_ids)
        with Form(first, view='hr_expense.hr_expense_view_form') as form:
            self.assertEqual(form.total_amount_currency, 100000)
        second = model.create({**vals, 'name': 'Second visible ordinary collision'})
        first.invalidate_recordset(['duplicate_expense_ids'])
        self.assertEqual(set(first.duplicate_expense_ids.ids), {first.id, second.id})
        self.assertNotIn(private.id, second.duplicate_expense_ids.ids)
        # Equal receipt bytes may exist on ordinary native expenses. Preserve
        # visible duplicate warnings while not revealing the private PS parent.
        raw = private.sudo().attachment_ids.raw
        for ordinary in (first, second):
            self.env['ir.attachment'].with_user(manager).with_context(allowed_company_ids=self.company.ids).create({
                'name': 'ordinary-same-receipt.pdf', 'raw': raw,
                'res_model': 'hr.expense', 'res_id': ordinary.id})
        first.invalidate_recordset(['same_receipt_expense_ids'])
        self.assertEqual(first.same_receipt_expense_ids, second)
        self.assertEqual(second.same_receipt_expense_ids, first)
        with self.assertRaises(AccessError):
            private.with_user(manager).read(['name'])

    def test_14_r1_f02_onchange_and_defaults_check_actual_report_viewer(self):
        trip, report = self._draft()
        self._line(report)
        spec = {key: {} for key in ('ps_revision', 'ps_basis_status', 'ps_trip_id', 'ps_owner_id',
            'ps_finance_id', 'ps_finance_valid')}
        for role in ('other', 'cash', 'manager'):
            model = self.env['hr.expense'].with_user(self.users[role]).with_context(allowed_company_ids=self.company.ids)
            with self.assertRaises(AccessError):
                model.onchange({'ps_report_id': report.id}, ['ps_report_id'], spec)
            with self.assertRaises(AccessError):
                model.with_context(default_ps_report_id=report.id).default_get(list(spec))
            with self.assertRaises(AccessError):
                model.onchange({'ps_report_id': report.id}, ['ps_report_id'],
                    {'ps_report_id': {'fields': {'revision': {}, 'claimed_total': {}}}})
        for role in ('owner', 'finance'):
            model = self.env['hr.expense'].with_user(self.users[role]).with_context(allowed_company_ids=self.company.ids)
            data = model.onchange({'ps_report_id': report.id}, ['ps_report_id'], spec)['value']
            self.assertEqual(data['ps_revision'], report.revision)
        foreign, _ = TestSettlement._fixture(self.env)
        actor = self.users['owner']
        actor.company_ids += self.env['res.company'].browse(foreign)
        with self.assertRaises(AccessError):
            self.env['hr.expense'].with_user(actor).with_context(allowed_company_ids=[foreign]).onchange(
                {'ps_report_id': report.id}, ['ps_report_id'], spec)

    def test_15_r1_f03_ordinary_defaults_cannot_attribute_ps_decision(self):
        native = self.env['hr.expense'].with_user(self.users['owner']).with_context(
            allowed_company_ids=self.company.ids, default_name='Valid ordinary native defaults',
            default_product_id=self.env.ref('ps_expenses.product_ps_native_expense').id,
            default_total_amount_currency=100000, default_ps_decision='accepted', default_ps_accepted_amount=77777,
            default_ps_reviewed_revision=99, default_ps_reviewed_by_id=self.users['finance'].id,
            default_ps_expected_revision=999, default_ps_line_id=1)
        defaults = native.default_get(['name', 'ps_decision', 'ps_accepted_amount', 'ps_reviewed_by_id', 'ps_reviewed_revision'])
        self.assertNotEqual(defaults.get('ps_decision'), 'accepted')
        records = native.create([{}, {'name': 'Second ordinary batch expense'}])
        for record in records:
            self.assertFalse(record.ps_report_id)
            self.assertEqual(record.ps_decision, 'pending')
            self.assertEqual(record.total_amount_currency, 100000)
            self.assertEqual(record.ps_accepted_amount, 0)
            self.assertEqual(record.ps_reviewed_revision, 0)
            self.assertFalse(record.ps_reviewed_by_id)
            self.assertFalse(record.ps_line_id)
        self.assertEqual(records[0].name, 'Valid ordinary native defaults')
        with self.assertRaises(AccessError):
            native.create({'name': 'Direct protected field', 'ps_decision': 'accepted'})
        imported = native.load(['name', 'product_id/.id', 'total_amount_currency', 'ps_decision'],
            [['Synthetic protected import', str(self.env.ref('ps_expenses.product_ps_native_expense').id), '100000', 'accepted']])
        self.assertFalse(imported.get('ids'))
        self.assertTrue(any(message['type'] == 'error' for message in imported['messages']))
