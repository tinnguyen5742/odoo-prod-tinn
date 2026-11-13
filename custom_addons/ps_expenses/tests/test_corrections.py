import json

from odoo import SUPERUSER_ID, api, fields
from odoo.exceptions import AccessError, LockError, ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, HttpCase, tagged

from .test_settlement import TestSettlement


@tagged('post_install', '-at_install')
class TestCorrections(TransactionCase):
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

    def _case(self, accepted=150000):
        settlement, report, advance = TestSettlement._case(self.env, self.users, accepted=accepted)
        settlement.action_submit(1)
        self._as(settlement, 'finance').action_approve('Synthetic original approval', 1)
        return settlement, report, advance

    def _open(self, trip, category='basis'):
        return self._as(self.env['ps.te.correction'], 'owner').create({
            'trip_id': trip.id, 'category': category, 'description': 'Synthetic source issue',
            'expected_revision': trip.preparing_revision,
        })

    def _cash(self, settlement):
        cash = self._as(settlement, 'cash')
        cash.action_start_cash('COR-ATTEMPT', 'Synthetic external execution', settlement.revision)
        cash.action_record_cash(abs(settlement.difference_amount), 'COR-RECORDED', fields.Date.today(), settlement.revision)

    def _resolve(self, correction):
        self._as(correction, 'finance').action_propose_no_change('FIN-CHECK', 'No source correction needed', correction.revision)
        self._as(correction, 'cash').action_confirm_no_change('CASH-CHECK', 'Exact recorded facts checked', correction.revision)
        self._as(correction, 'finance').action_resolve_no_change('Investigation complete, sources unchanged', correction.revision)

    def test_01_hold_then_return_unexecuted_basis_for_owner_revision(self):
        settlement, report, advance = self._case()
        original_cash = advance.cash_event_id
        correction = self._open(settlement.trip_id)
        self.assertTrue(settlement.trip_id.correction_hold)
        with self.assertRaises(ValidationError):
            report.action_revise('Cannot bypass case', report.revision)
        with self.assertRaises(ValidationError):
            self._as(settlement, 'cash').action_start_cash('BYPASS', 'Cannot start new payment', 1)
        with self.assertRaises(ValidationError):
            self._as(settlement, 'finance').action_return('Cannot bypass linked correction', 1)
        self._as(correction, 'finance').action_return_for_revision('Re-review the employee facts', 1)
        self.assertFalse(settlement.trip_id.correction_hold)
        self.assertEqual(settlement.state, 'draft')
        self.assertFalse(report.basis_locked)
        report.action_revise('Owner makes explicit correction', report.revision)
        self.assertEqual(advance.cash_event_id, original_cash)
        self.assertTrue(settlement.event_ids.filtered(lambda e: e.event_type == 'approved'))

    def test_02_recorded_cash_cannot_reset_and_external_case_stays_open(self):
        settlement, report, advance = self._case()
        self._cash(settlement)
        recorded = settlement.cash_event_id
        correction = self._open(settlement.trip_id)
        with self.assertRaises(ValidationError):
            self._as(correction, 'finance').action_return_for_revision('Unsafe reset', 1)
        self._as(correction, 'finance').action_require_external('EXTERNAL-CASE', 'Actual adjustment needs separate authority', 1)
        self.assertEqual(correction.state, 'external_required')
        self.assertTrue(settlement.trip_id.correction_hold)
        self.assertEqual(settlement.cash_event_id, recorded)
        self.assertEqual(settlement.accepted_amount, 150000)
        with self.assertRaises(ValidationError):
            self._as(settlement, 'finance').action_close('Cannot ignore unresolved correction', 1)

    def test_03_no_change_requires_distinct_cash_check_then_finance_resolution(self):
        settlement, report, advance = self._case()
        self._cash(settlement)
        before = (settlement.revision, settlement.accepted_amount, settlement.cash_event_id.id)
        correction = self._open(settlement.trip_id)
        finance = self._as(correction, 'finance')
        finance.action_propose_no_change('FIN-FACTS', 'Facts already correct', 1)
        with self.assertRaises(ValidationError):
            finance.action_resolve_no_change('No cash check yet', correction.revision)
        with self.assertRaises(AccessError):
            finance.action_confirm_no_change('SELF-CHECK', 'Not independent', correction.revision)
        self._as(correction, 'cash').action_confirm_no_change('CASH-FACTS', 'Checked unchanged facts', correction.revision)
        finance.action_resolve_no_change('No changes required', correction.revision)
        events = len(correction.event_ids)
        finance.action_resolve_no_change('No changes required', correction.revision)
        self.assertEqual(len(correction.event_ids), events)
        self.assertEqual(before, (settlement.revision, settlement.accepted_amount, settlement.cash_event_id.id))
        self.assertEqual(settlement.trip_id.case_status, 'open')
        self._as(settlement, 'finance').action_close('Separate original workflow closure', settlement.revision)
        self.assertEqual(settlement.accounting_status, 'not_verified')

    def test_04_wrong_roles_cannot_read_decide_or_gain_proof_access(self):
        settlement, report, advance = self._case()
        correction = self._open(settlement.trip_id)
        for role in ('manager', 'other'):
            self.assertFalse(self._as(self.env['ps.te.correction'], role).search([('id', '=', correction.id)]))
            with self.assertRaises(AccessError):
                self._as(correction, role).read(['source_snapshot'])
        for role in ('owner', 'cash', 'manager', 'other'):
            with self.assertRaises(AccessError):
                self._as(correction, role).action_return_for_revision('Wrong officer', 1)
        cash = self._as(correction, 'cash')
        self.assertTrue(cash.read(['source_snapshot']))
        with self.assertRaises(AccessError):
            self._as(report.line_ids[0].evidence_ids.attachment_id, 'cash').read(['datas'])
        self.assertNotIn(report.line_ids[0].description, correction.source_snapshot)
        self.assertNotIn(report.line_ids[0].evidence_ids.filename, correction.source_snapshot)

    def test_05_policy_drift_invalidates_confirmation_and_refresh_clears_it(self):
        settlement, report, _ = self._case()
        correction = self._open(settlement.trip_id, 'authority')
        self._as(correction, 'finance').action_propose_no_change('OLD-POLICY-CHECK', 'Unchanged then', 1)
        self.env['res.company'].browse(self.company_id).ps_te_settlement_policy_reference = 'SYNTHETIC-NEW-POLICY'
        with self.assertRaises(ValidationError):
            self._as(correction, 'cash').action_confirm_no_change('STALE-CHECK', 'Cannot reuse old policy check', correction.revision)
        correction.action_refresh('Policy binding changed', correction.revision)
        self.assertFalse(correction.proposed_by_id)
        with self.assertRaises(ValidationError):
            self._as(correction, 'finance').action_propose_no_change('CANNOT-ADOPT-SILENTLY', 'Original policy is stale', correction.revision)
        self._as(correction, 'finance').action_return_for_revision('Prepare under current policy', correction.revision)
        self.assertFalse(report.basis_locked)
        settlement.action_refresh('Owner explicitly prepares new policy', settlement.revision)
        self.assertEqual(settlement.policy_reference, 'SYNTHETIC-NEW-POLICY')

    def test_06_changed_staff_return_unexecuted_basis_without_impersonation(self):
        settlement, report, advance = self._case(accepted=100000)
        cash_id = advance.cash_event_id.id
        correction = self._open(settlement.trip_id, 'authority')
        self.users['other'].group_ids += self.env.ref('ps_expenses.group_ps_te_finance')
        self.users['manager'].group_ids += self.env.ref('ps_expenses.group_ps_te_cash')
        self.env['res.company'].browse(self.company_id).write({
            'ps_te_finance_reviewer_id': self.users['other'].id, 'ps_te_cash_operator_id': self.users['manager'].id,
        })
        correction.action_refresh('Current officers appointed', 1)
        with self.assertRaises(AccessError):
            self._as(correction, 'finance').action_return_for_revision('Former officer', correction.revision)
        self._as(correction, 'other').action_return_for_revision('Current officer requires fresh review', correction.revision)
        report.action_revise('Owner resubmits to new finance', report.revision)
        report.action_submit(report.revision)
        self._as(report, 'other').action_review_line(report.line_ids.id, 'accepted', 'Fresh current-officer decision', 100000, report.revision)
        settlement.action_refresh('Refresh exact re-reviewed basis', settlement.revision)
        settlement.action_submit(settlement.revision)
        self._as(settlement, 'other').action_approve('New exact approval', settlement.revision)
        self.assertEqual(advance.cash_event_id.id, cash_id)
        self.assertEqual(advance.disbursed_by_id, self.users['cash'])
        self.assertEqual(settlement.finance_reviewer_id, self.users['other'])

    def test_07_uncertain_cash_reconciliation_is_allowed_but_snapshot_must_refresh(self):
        settlement, report, _ = self._case()
        cash = self._as(settlement, 'cash')
        cash.action_start_cash('UNCERTAIN-COR', 'External attempt exists', 1)
        correction = self._open(settlement.trip_id)
        with self.assertRaises(ValidationError):
            self._as(correction, 'finance').action_propose_no_change('UNSAFE-UNKNOWN', 'Cannot assert unchanged outcome', 1)
        cash.action_record_cash(50000, 'COR-RECONCILED', fields.Date.today(), 1)
        with self.assertRaises(ValidationError):
            self._as(correction, 'finance').action_require_external('STALE-SNAPSHOT', 'Old source', 1)
        correction.action_refresh('Use reconciled actual event', 1)
        self._resolve(correction)
        self.assertEqual(settlement.cash_event_id.external_reference, 'COR-RECONCILED')

    def test_08_direct_context_and_history_forgery_and_mixed_batch(self):
        settlement, report, _ = self._case()
        model = self._as(self.env['ps.te.correction'], 'owner')
        data = {'trip_id': settlement.trip_id.id, 'category': 'basis', 'description': 'Synthetic safe creation', 'expected_revision': 1}
        with self.assertRaises(AccessError):
            model.create({**data, 'state': 'resolved'})
        with self.assertRaises(AccessError):
            model.create([data, {**data, 'owner_id': self.users['other'].id}])
        self.assertFalse(settlement.trip_id.correction_case_id)
        correction = model.with_context(default_cash_confirmed_by_id=self.users['owner'].id, default_state='resolved').create(data)
        self.assertEqual(correction.state, 'submitted')
        self.assertFalse(correction.cash_confirmed_by_id)
        with self.assertRaises(AccessError):
            correction.write({'source_digest': 'forged'})
        with self.assertRaises(AccessError):
            correction.event_ids.write({'snapshot': '{}'})
        with self.assertRaises(AccessError):
            correction.unlink()

    def test_09_one_active_case_and_strict_proposal_revision(self):
        settlement, _, _ = self._case()
        correction = self._open(settlement.trip_id)
        with self.assertRaises(ValidationError):
            self._open(settlement.trip_id)
        self._as(correction, 'finance').action_propose_no_change('REV-PROPOSAL', 'Exact snapshot', 1)
        with self.assertRaises(ValidationError):
            self._as(correction, 'cash').action_confirm_no_change('STALE-UI', 'Old revision', 1)
        self._as(correction, 'cash').action_confirm_no_change('CURRENT-UI', 'Current revision', correction.revision)

    def test_10_closed_workflow_is_historical_while_correction_is_active(self):
        settlement, _, _ = self._case()
        self._cash(settlement)
        self._as(settlement, 'finance').action_close('Original closed workflow', 1)
        closed_at = settlement.closed_at
        correction = self._open(settlement.trip_id)
        self.assertEqual(settlement.trip_id.case_status, 'workflow_closed')
        renderer = self._as(self.env['ir.actions.report'], 'cash')
        output, _ = renderer._render_qweb_html('ps_expenses.settlement_summary', [settlement.id])
        self.assertIn('Active correction hold', output.decode())
        self.assertNotIn('id="current-comparison"', output.decode())
        self._resolve(correction)
        self.assertEqual(settlement.closed_at, closed_at)
        self.assertFalse(settlement.trip_id.correction_hold)

    def test_11_funding_case_never_resets_recorded_advance(self):
        settlement, _, advance = self._case()
        correction = self._open(settlement.trip_id, 'funding')
        with self.assertRaises(ValidationError):
            self._as(correction, 'finance').action_return_for_revision('Cannot rewrite advance', 1)
        self._as(correction, 'finance').action_require_external('FUNDING-RECONCILIATION', 'Keep actual cash fact, investigate separately', 1)
        self.assertTrue(advance.has_disbursement)
        self.assertTrue(correction.active_trip_id)

    def test_12_native_creation_and_operation_wizard(self):
        settlement, _, _ = self._case()
        trip = settlement.trip_id
        model = self._as(self.env['ps.te.correction.wizard'], 'owner').with_context(**trip.action_open_correction()['context'])
        with Form(model) as wizard:
            wizard.operation = 'create'
            wizard.category = 'basis'
            wizard.reason = 'Synthetic native wizard issue'
        result = wizard.record.action_apply()
        correction = self.env['ps.te.correction'].browse(result['res_id'])
        Form(self._as(correction, 'finance'))
        self.assertEqual(correction.trip_id, trip)

    def test_13_changed_policy_after_cash_cannot_silently_revalidate_or_reset(self):
        settlement, _, _ = self._case()
        self._cash(settlement)
        event = settlement.cash_event_id
        correction = self._open(settlement.trip_id, 'authority')
        self.env['res.company'].browse(self.company_id).ps_te_expense_policy_reference = 'SYNTHETIC-POST-CASH-POLICY'
        correction.action_refresh('Policy changed after recorded cash', correction.revision)
        with self.assertRaises(ValidationError):
            self._as(correction, 'finance').action_propose_no_change('CANNOT-CERTIFY', 'Original expense policy is no longer current', correction.revision)
        with self.assertRaises(ValidationError):
            self._as(correction, 'finance').action_return_for_revision('Cannot reset recorded movement', correction.revision)
        self._as(correction, 'finance').action_require_external('SPECIALIST-REVIEW-NEEDED', 'No financial adjustment invented', correction.revision)
        self.assertEqual(settlement.cash_event_id, event)
        self.assertTrue(correction.active_trip_id)

    def test_14_foreign_company_and_mixed_source_batch_are_denied(self):
        settlement, _, _ = self._case()
        company, users = TestSettlement._fixture(self.env)
        foreign_users = {role: self.env['res.users'].browse(uid) for role, uid in users.items()}
        foreign, _, _ = TestSettlement._case(self.env, foreign_users)
        data = {'trip_id': settlement.trip_id.id, 'category': 'basis', 'description': 'Own issue', 'expected_revision': 1}
        with self.assertRaises(AccessError):
            self._as(self.env['ps.te.correction'], 'owner').create([data, {**data, 'trip_id': foreign.trip_id.id}])
        self.assertFalse(settlement.trip_id.correction_case_id)
        correction = self._open(settlement.trip_id)
        with self.assertRaises(AccessError):
            self._as(correction, 'owner').with_context(allowed_company_ids=[company]).read(['source_snapshot'])

    def test_15_competing_cases_keep_one_active_trip_slot(self):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            users = {role: env['res.users'].browse(uid) for role, uid in self.race_users.items()}
            settlement, _, _ = TestSettlement._case(env, users)
            trip_id = settlement.trip_id.id
            cr.commit()
        context = {'allowed_company_ids': [self.race_company]}
        data = {'trip_id': trip_id, 'category': 'basis', 'description': 'Competing issue', 'expected_revision': 1}
        with self.registry.cursor() as first_cr, self.registry.cursor() as second_cr:
            first = api.Environment(first_cr, self.race_users['owner'], context)['ps.te.correction']
            second = api.Environment(second_cr, self.race_users['owner'], context)['ps.te.correction']
            first.create(data)
            with self.assertRaises(LockError):
                second.create(data)
            second_cr.rollback()
            first_cr.commit()
        with self.registry.cursor() as cr:
            model = api.Environment(cr, self.race_users['owner'], context)['ps.te.correction']
            self.assertEqual(model.search_count([('active_trip_id', '=', trip_id)]), 1)


@tagged('post_install', '-at_install')
class TestCorrectionHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company, users = TestSettlement._fixture(cls.env)
        cls.company_id = company
        cls.users = {role: cls.env['res.users'].browse(uid) for role, uid in users.items()}
        for user in cls.users.values():
            user.password = 'synthetic-correction-only'
        settlement, _, _ = TestSettlement._case(cls.env, cls.users)
        cls.case = cls.env['ps.te.correction'].with_user(cls.users['owner']).with_context(allowed_company_ids=[company]).create({
            'trip_id': settlement.trip_id.id, 'category': 'basis', 'description': 'Synthetic RPC correction', 'expected_revision': 1,
        })

    def _rpc(self, method, args):
        response = self.url_open('/web/dataset/call_kw/ps.te.correction/' + method,
                                 data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'id': 1,
                                                  'params': {'model': 'ps.te.correction', 'method': method, 'args': args,
                                                             'kwargs': {'context': {'allowed_company_ids': [self.company_id]}}}}),
                                 headers={'Content-Type': 'application/json'})
        return response.json()

    def test_native_rpc_respects_case_access_and_direct_field_guards(self):
        for role in ('owner', 'finance', 'cash', 'manager', 'other'):
            self.authenticate(self.users[role].login, 'synthetic-correction-only')
            result = self._rpc('read', [[self.case.id], ['reference', 'source_snapshot']])
            if role in ('owner', 'finance', 'cash'):
                self.assertEqual(result['result'][0]['reference'], self.case.reference)
                forged = self._rpc('write', [[self.case.id], {'state': 'resolved'}])
                self.assertIn('error', forged)
            else:
                self.assertIn('error', result)
                self.assertNotIn(self.case.source_snapshot, json.dumps(result))
                self.assertNotIn(self.case.source_digest, json.dumps(result))
