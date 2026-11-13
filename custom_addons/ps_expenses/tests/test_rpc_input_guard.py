"""R3-F01: actual-user authorization before pseudo-record related resolution."""
import json

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import Form
from odoo.tests.common import HttpCase, tagged

from .test_settlement import TestSettlement
from .test_trip_amendment import TestTripAmendment


@tagged('post_install', '-at_install')
class TestPsRpcInputGuard(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_id, actors = TestSettlement._fixture(cls.env)
        cls.company = cls.company_id
        cls.users = {role: cls.env['res.users'].browse(uid) for role, uid in actors.items()}
        cls.env['hr.employee'].create({'name': 'R4 synthetic other employee',
            'user_id': cls.users['other'].id, 'company_id': cls.company_id})
        for user in cls.users.values():
            user.password = 'synthetic-r3-only'
        cls.settlement, cls.report, cls.advance = TestSettlement._case(cls.env, cls.users)
        cls.line = cls.report.line_ids
        # Exact reviewed100/80/20 fixture, independent of browser/reviewer DBs.
        cls.report.action_revise('Synthetic R3 exact partial acceptance', cls.report.revision)
        cls.report.action_submit(cls.report.revision)
        cls.report.with_user(cls.users['finance']).action_review_line(
            cls.line.id, 'accepted', 'Synthetic accepted80', 80000, cls.report.revision)
        cls.amendment = TestTripAmendment._request(cls, cls.settlement.trip_id)
        cls.root = cls.advance.cash_event_id
        cls.other_company_id, actors2 = TestSettlement._fixture(cls.env)
        cls.users2 = {role: cls.env['res.users'].browse(uid) for role, uid in actors2.items()}
        _, cls.report2, _ = TestSettlement._case(cls.env, cls.users2)

    def _rpc(self, role, model, method, args, context=None):
        user = self.users[role]
        self.authenticate(user.login, 'synthetic-r3-only')
        payload = {'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {
            'model': model, 'method': method, 'args': args,
            'kwargs': {'context': {'allowed_company_ids': [self.company_id], **(context or {})}}}}
        response = self.url_open('/web/dataset/call_kw/' + model + '/' + method,
            data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _denied(self, response):
        self.assertIn('error', response, response)
        self.assertEqual(response['error']['data']['name'], 'odoo.exceptions.AccessError', response)
        self.assertNotIn('result', response)

    def _amount_spec(self):
        return {'line_ids': {'fields': {}}, **{name: {} for name in
            ('revision', 'claimed_total', 'accepted_total', 'refused_total', 'unresolved_total')}}

    def test_r3_exact_public_report_payload_and_denied_read_counterparts(self):
        for role in ('other', 'cash', 'manager'):
            for model, record_id in (('ps.te.expense.report', self.report.id),
                    ('ps.te.expense.line', self.line.id), ('hr.expense', self.line.native_expense_id.id)):
                self._denied(self._rpc(role, model, 'read', [[record_id], ['id']]))
            for values in ({'line_ids': [[6, 0, [self.line.id]]]},
                    {'line_ids': [[6, 0, [self.line.id]]], 'revision': self.report.revision}):
                self._denied(self._rpc(role, 'ps.te.expense.report', 'onchange',
                    [[], values, list(values), self._amount_spec()]))

    def test_r3_report_owner_finance_positive_and_persisted_form(self):
        for role in ('owner', 'finance'):
            response = self._rpc(role, 'ps.te.expense.report', 'onchange',
                [[], {'line_ids': [[6, 0, [self.line.id]]], 'revision': self.report.revision},
                 ['line_ids', 'revision'], self._amount_spec()])
            self.assertNotIn('error', response, response)
            value = response['result']['value']
            self.assertEqual((value['claimed_total'], value['accepted_total'], value['refused_total']),
                             (100000, 80000, 20000))
            form = Form(self.report.with_user(self.users[role]).with_context(allowed_company_ids=[self.company_id]),
                        view='ps_expenses.view_ps_te_expense_form')
            self.assertEqual(form.claimed_total, 100000)

    def test_r3_defaults_persisted_id_and_initial_empty_field_names(self):
        for role in ('other', 'cash', 'manager'):
            for context in ({'default_line_ids': [[6, 0, [self.line.id]]]},
                            {'default_trip_id': {'id': self.settlement.trip_id.id,
                                'expense_report_id': self.report.id}}):
                self._denied(self._rpc(role, 'ps.te.expense.report', 'default_get',
                    [['line_ids', 'trip_id']], context))
            self._denied(self._rpc(role, 'ps.te.expense.report', 'onchange',
                [[self.report.id], {}, [], self._amount_spec()]))
            self._denied(self._rpc(role, 'ps.te.expense.report', 'onchange',
                [[], {'line_ids': [[6, 0, [self.line.id]]]}, [], self._amount_spec()]))

    def test_r3_nested_command_and_many2one_dict_inputs(self):
        commands = ([[4, self.line.id]], [[1, self.line.id, {}]], [self.line.id], [{'id': self.line.id}],
            [[0, 'virtual_r3', {'native_expense_id': self.line.native_expense_id.id}]],
            [[0, 'virtual_r3', {'report_id': {'id': self.report.id}}]])
        for command in commands:
            self._denied(self._rpc('other', 'ps.te.expense.report', 'onchange',
                [[], {'line_ids': command}, ['line_ids'], self._amount_spec()]))
        self._denied(self._rpc('other', 'ps.te.expense.wizard', 'onchange',
            [[], {'report_id': {'id': self.report.id}}, ['report_id'], {'currency_id': {}}]))

    def test_r3_mixed_visible_hidden_and_company_graph_fails_as_a_whole(self):
        for command in ([[6, 0, [self.line.id, self.report2.line_ids.id]]],
                        [[4, self.line.id], [4, self.report2.line_ids.id]]):
            self._denied(self._rpc('owner', 'ps.te.expense.report', 'onchange',
                [[], {'line_ids': command}, ['line_ids'], self._amount_spec()]))
        self._denied(self._rpc('owner', 'ps.te.expense.wizard', 'default_get',
            [['report_id']], {'default_report_id': self.report2.id}))

    def test_r3_adjustment_amendment_related_metadata_counterparts(self):
        spec = {name: {} for name in ('amended_purpose', 'amended_destination',
            'amended_start_date', 'amended_end_date', 'amendment_manager_id')}
        self._denied(self._rpc('other', 'ps.te.trip.amendment', 'read', [[self.amendment.id], ['purpose']]))
        for context, values in (({}, {'amendment_id': self.amendment.id}),
                ({'default_amendment_id': self.amendment.id}, {})):
            self._denied(self._rpc('other', 'ps.te.adjustment', 'onchange',
                [[], values, list(values), spec], context))
        result = self._rpc('owner', 'ps.te.adjustment', 'onchange',
            [[], {'amendment_id': self.amendment.id}, ['amendment_id'], spec])
        self.assertNotIn('error', result, result)
        self.assertEqual(result['result']['value']['amended_purpose'], self.amendment.purpose)

    def test_r3_cash_root_related_metadata_and_correct_cash_scope(self):
        spec = {name: {} for name in ('trip_id', 'owner_id', 'company_id', 'currency_id')}
        self._denied(self._rpc('other', 'ps.te.cash.event', 'read', [[self.root.id], ['amount']]))
        for context, values in (({}, {'root_event_id': self.root.id}),
                ({'default_root_event_id': self.root.id}, {})):
            self._denied(self._rpc('other', 'ps.te.cash.rectification', 'onchange',
                [[], values, list(values), spec], context))
        for role in ('owner', 'finance', 'cash'):
            result = self._rpc(role, 'ps.te.cash.rectification', 'onchange',
                [[], {'root_event_id': self.root.id}, ['root_event_id'], spec])
            self.assertNotIn('error', result, result)
            self.assertEqual(result['result']['value']['owner_id'], self.users['owner'].id)
        # Chặn private claim không được làm hỏng wizard thu/chi đúng phạm vi.
        form = Form(self.env['ps.te.settlement.wizard'].with_user(self.users['cash']).with_context(
                allowed_company_ids=[self.company_id], default_settlement_id=self.settlement.id,
                default_expected_revision=self.settlement.revision),
                view='ps_expenses.view_ps_te_settlement_wizard')
        form.operation = 'none'
        self.assertEqual(form.settlement_id, self.settlement)

    def test_r3_malformed_links_never_resolve_private_sources(self):
        for value in ([[6, 0, [True]]], [[6, 0, [-1]]], [[6, 0, ['1']]],
                      [[6]], [[1, self.line.id]], [[99, 0, []]]):
            self._denied(self._rpc('other', 'ps.te.expense.report', 'onchange',
                [[], {'line_ids': value}, ['line_ids'], self._amount_spec()]))

    def _split_spec(self):
        return {name: {} for name in ('expense_id', 'total_amount_currency_original', 'currency_id', 'split_possible')}

    def test_r4_exact_split_wizard_public_read_denied_and_three_leak_routes(self):
        native_id = self.line.native_expense_id.id
        for role in ('other', 'manager', 'cash'):
            self._denied(self._rpc(role, 'hr.expense', 'read', [[native_id], ['total_amount_currency']]))
            for values, names, context in (
                    ({'expense_id': native_id}, ['expense_id'], {}),
                    ({'expense_id': native_id}, [], {}),
                    ({}, [], {'default_expense_id': native_id})):
                self._denied(self._rpc(role, 'hr.expense.split.wizard', 'onchange',
                    [[], values, names, self._split_spec()], context))

    def test_r4_split_default_get_and_nested_native_origins(self):
        native_id = self.line.native_expense_id.id
        for role in ('other', 'manager', 'cash'):
            self._denied(self._rpc(role, 'hr.expense.split.wizard', 'default_get',
                [['expense_id', 'total_amount_currency_original']], {'default_expense_id': native_id}))
            self._denied(self._rpc(role, 'hr.expense.split', 'default_get',
                [['expense_id', 'name', 'product_id']], {'default_expense_id': native_id}))
            for values in ({'expense_id': {'id': native_id}},
                    {'expense_split_line_ids': [[0, 'r4_virtual', {'expense_id': native_id}]]},
                    {'expense_split_line_ids': [{'expense_id': {'id': native_id}}]}):
                self._denied(self._rpc(role, 'hr.expense.split.wizard', 'onchange',
                    [[], values, list(values), self._split_spec()]))
            self._denied(self._rpc(role, 'hr.expense.split', 'onchange', [[],
                {'wizard_id': {'expense_id': native_id}}, ['wizard_id'], {'wizard_id': {'fields': {
                    'total_amount_currency_original': {}}}}]))

    def test_r4_owner_finance_ps_amount_positive_without_split_authority(self):
        native_id = self.line.native_expense_id.id
        for role in ('owner', 'finance'):
            result = self._rpc(role, 'hr.expense.split.wizard', 'onchange',
                [[], {'expense_id': native_id}, ['expense_id'], self._split_spec()])
            self.assertNotIn('error', result, result)
            self.assertEqual(result['result']['value']['total_amount_currency_original'], 100000)
            self._denied(self._rpc(role, 'hr.expense.split.wizard', 'create', [{'expense_id': native_id}]))
            action = self._rpc(role, 'hr.expense', 'action_split_wizard', [[native_id]])
            self.assertIn('error', action)
        self.assertEqual(self.line.native_expense_id.total_amount_currency, 100000)
        self.assertEqual(self.line.native_expense_id.ps_accepted_amount, 80000)

    def test_r4_ordinary_native_split_onchange_defaults_preserved(self):
        ordinary = self.env['hr.expense'].with_user(self.users['other']).with_context(
            allowed_company_ids=[self.company_id]).create({'name': 'R4 ordinary native claim',
                'product_id': self.env.ref('ps_expenses.product_ps_native_expense').id,
                'total_amount_currency': 65432, 'date': fields.Date.today()})
        self.assertFalse(ordinary.ps_report_id)
        for values, names, context in (({'expense_id': ordinary.id}, ['expense_id'], {}),
                                     ({}, [], {'default_expense_id': ordinary.id})):
            result = self._rpc('other', 'hr.expense.split.wizard', 'onchange',
                [[], values, names, self._split_spec()], context)
            self.assertNotIn('error', result, result)
            self.assertEqual(result['result']['value']['total_amount_currency_original'], 65432)
        defaults = self._rpc('other', 'hr.expense.split', 'default_get',
            [['expense_id', 'name']], {'default_expense_id': ordinary.id})
        self.assertNotIn('error', defaults, defaults)
        self.assertEqual(defaults['result']['name'], 'R4 ordinary native claim')

    def test_r4_adjacent_native_mixed_expenses_and_active_defaults(self):
        native_id = self.line.native_expense_id.id
        for model in ('hr.expense.approve.duplicate', 'hr.expense.refuse.wizard'):
            for value in ([[6, 0, [native_id]]], [native_id]):
                self._denied(self._rpc('other', model, 'default_get', [['expense_ids']],
                    {'default_expense_ids': value}))
            self._denied(self._rpc('other', model, 'default_get', [['expense_ids']],
                {'active_model': 'hr.expense', 'active_ids': [native_id]}))
            self._denied(self._rpc('other', model, 'onchange', [[],
                {'expense_ids': [[6, 0, [native_id, self.report2.line_ids.native_expense_id.id]]]}, ['expense_ids'],
                {'expense_ids': {'fields': {'total_amount_currency': {}}}}]))
        self._denied(self._rpc('other', 'hr.expense.post.wizard', 'default_get', [[]],
            {'active_ids': [native_id]}))
        self._denied(self._rpc('other', 'hr.expense.refuse.wizard', 'default_get', [['expense_ids']],
            {'active_ids': [native_id], 'active_model': 'res.partner'}))

    def test_r4_foreign_company_source_and_mixed_ps_ordinary_sources(self):
        foreign_id = self.report2.line_ids.native_expense_id.id
        for role in ('owner', 'finance'):
            self._denied(self._rpc(role, 'hr.expense.split.wizard', 'onchange',
                [[], {'expense_id': foreign_id}, ['expense_id'], self._split_spec()]))
        ordinary = self.env['hr.expense'].with_user(self.users['other']).with_context(
            allowed_company_ids=[self.company_id]).create({'name': 'R4 visible mixed counterpart',
                'product_id': self.env.ref('ps_expenses.product_ps_native_expense').id,
                'total_amount_currency': 10, 'date': fields.Date.today()})
        for commands in ([[6, 0, [ordinary.id, self.line.native_expense_id.id]]],
                         [[4, ordinary.id], [4, self.line.native_expense_id.id]]):
            self._denied(self._rpc('other', 'hr.expense.approve.duplicate', 'onchange', [[],
                {'expense_ids': commands}, ['expense_ids'], {'expense_ids': {'fields': {'total_amount_currency': {}}}}]))

    def test_r4_protected_relation_on_model_outside_ps_native_namespace(self):
        # account.move is native accounting, not hr.expense.* or ps.te.*.
        self.assertEqual(self.env['account.move']._fields['expense_ids'].comodel_name, 'hr.expense')
        self._denied(self._rpc('other', 'account.move', 'default_get', [['expense_ids']],
            {'default_expense_ids': [[6, 0, [self.line.native_expense_id.id]]]}))
        self._denied(self._rpc('other', 'account.move', 'onchange', [[],
            {'expense_ids': [[0, 'r4_nested', {'split_expense_origin_id': self.line.native_expense_id.id}]]},
            ['expense_ids'], {'expense_ids': {'fields': {'total_amount_currency': {}}}}]))

    def test_r4_persisted_wizard_origin_rechecks_expense_and_empty_native_input(self):
        # Fixture only: superuser creates transient the actual actor could not
        # create. This is NOT a claimed public create exploit or ACL grant.
        wizard = self.env['hr.expense.split.wizard'].with_user(self.users['other']).sudo().create(
            {'expense_id': self.line.native_expense_id.id})
        self._denied(self._rpc('other', 'hr.expense.split.wizard', 'onchange',
            [[wizard.id], {}, [], self._split_spec()]))
        self._denied(self._rpc('other', 'hr.expense.split.wizard', 'onchange',
            [[], {'id': wizard.id}, [], self._split_spec()]))
        result = self._rpc('other', 'hr.expense.split.wizard', 'onchange', [[], {}, [], self._split_spec()])
        self.assertNotIn('error', result, result)
        self.assertFalse(result['result']['value'].get('total_amount_currency_original', 0))
