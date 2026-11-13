import base64
import uuid

from odoo import SUPERUSER_ID, api, fields
from odoo.exceptions import AccessError, LockError, ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged

from ..models.trip_advance import PsTeTripAdvance
from .test_advance import TestTripAdvance
from .test_expenses import TestExpenseEvidence


@tagged('post_install', '-at_install')
class TestSettlement(TransactionCase):

    @staticmethod
    def _fixture(env):
        company_id, users = TestExpenseEvidence._fixture(env)
        env['res.company'].browse(company_id).ps_te_settlement_policy_reference = 'SYNTHETIC-SETTLEMENT-V1-' + uuid.uuid4().hex
        return company_id, users

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with cls.registry.cursor() as cr:
            cls.race_company, cls.race_users = cls._fixture(api.Environment(cr, SUPERUSER_ID, {}))
            cr.commit()
        company_id, users = cls._fixture(cls.env)
        cls.company = cls.env['res.company'].browse(company_id)
        for role, user_id in users.items():
            setattr(cls, role, cls.env['res.users'].browse(user_id))

    def _as(self, record, user):
        return record.with_user(user).with_context(allowed_company_ids=[user.company_id.id])

    @staticmethod
    def _case(env, users, accepted=100000, funding=100000, pending=False):
        trip = TestTripAdvance._new_trip(env, users)
        advance = env['ps.te.trip.advance'].browse()
        if funding is None:
            trip.action_no_advance()
        else:
            advance = env['ps.te.trip.advance'].with_user(users['owner']).with_context(
                allowed_company_ids=[users['owner'].company_id.id],
            ).create({'trip_id': trip.id, 'purpose': 'Synthetic settlement advance', 'requested_amount': funding})
            advance.action_submit(1)
            advance.with_user(users['finance']).action_review('approved', 'Synthetic approval', 1, funding)
            if not pending:
                cash = advance.with_user(users['cash'])
                cash.action_start_disbursement('ATTEMPT-' + uuid.uuid4().hex, 'Prepare external payment', 1)
                cash.action_record_disbursement(funding, 'ADV-PAY-' + uuid.uuid4().hex, fields.Date.today(), 1)
        report = env['ps.te.expense.report'].with_user(users['owner']).with_context(
            allowed_company_ids=[users['owner'].company_id.id],
        ).create({'trip_id': trip.id})
        line_id = report.action_add_line('Synthetic settlement expense', max(accepted, 1000), fields.Date.today(), report.revision)
        report.action_upload_evidence(line_id, 'synthetic.pdf', base64.b64encode(TestExpenseEvidence._pdf()), report.revision)
        report.action_submit(report.revision)
        report.with_user(users['finance']).action_review_line(
            line_id, 'accepted' if accepted else 'refused', 'Synthetic expense decision', accepted, report.revision,
        )
        settlement = env['ps.te.settlement'].with_user(users['owner']).with_context(
            allowed_company_ids=[users['owner'].company_id.id],
        ).create({'trip_id': trip.id})
        return settlement, report, advance

    def _new(self, accepted=100000, funding=100000, pending=False):
        users = {role: getattr(self, role) for role in ('owner', 'manager', 'finance', 'cash')}
        return self._case(self.env, users, accepted, funding, pending)

    def _approve(self, settlement):
        settlement.action_submit(settlement.revision)
        self._as(settlement, self.finance).action_approve('Synthetic exact-basis approval', settlement.revision)

    def _record(self, settlement):
        cash = self._as(settlement, self.cash)
        cash.action_start_cash('SET-ATTEMPT-' + uuid.uuid4().hex, 'Prepare external settlement movement', settlement.revision)
        reference = 'SET-PAY-' + uuid.uuid4().hex
        cash.action_record_cash(abs(settlement.difference_amount), reference, fields.Date.today(), settlement.revision)
        return reference

    def test_01_equal_case_requires_explicit_finance_close(self):
        settlement, report, advance = self._new()
        self.assertTrue(settlement.funding_known)
        self.assertEqual(settlement.direction, 'balanced')
        self.assertEqual(settlement.state, 'draft')
        with self.assertRaises(ValidationError):
            self._as(settlement, self.finance).action_close('Arithmetic alone is insufficient', settlement.revision)
        self._approve(settlement)
        self.assertTrue(report.basis_locked)
        self.assertFalse(settlement.cash_event_id)
        self._as(settlement, self.finance).action_close('Recorded obligations resolved', settlement.revision)
        self.assertEqual(settlement.state, 'closed')
        self.assertEqual(settlement.trip_id.case_status, 'workflow_closed')
        self.assertEqual(settlement.accounting_status, 'not_verified')
        self.assertEqual(settlement.remaining_amount, 0)
        self.assertEqual(advance.cash_event_id.kind, 'advance')

    def test_02_deficit_requires_company_topup_then_close(self):
        settlement, report, advance = self._new(accepted=150000, funding=100000)
        self.assertEqual((settlement.direction, settlement.difference_amount), ('topup', 50000))
        self._approve(settlement)
        with self.assertRaises(ValidationError):
            self._as(settlement, self.finance).action_close('Still owes money', settlement.revision)
        reference = self._record(settlement)
        self._as(settlement, self.cash).action_record_cash(50000, reference, fields.Date.today(), settlement.revision)
        self.assertEqual(settlement.cash_event_id.kind, 'topup')
        self.assertEqual(settlement.remaining_amount, 0)
        self._as(settlement, self.finance).action_close('Top-up recorded', settlement.revision)
        self.assertEqual(settlement.state, 'closed')

    def test_03_surplus_requires_employee_return(self):
        settlement, report, advance = self._new(accepted=60000, funding=100000)
        self.assertEqual((settlement.direction, settlement.difference_amount), ('return', -40000))
        self._approve(settlement)
        self._record(settlement)
        self.assertEqual(settlement.cash_event_id.kind, 'return')
        self._as(settlement, self.finance).action_close('Employee return recorded', settlement.revision)
        self.assertEqual(settlement.state, 'closed')

    def test_04_no_advance_intent_does_not_prove_zero_funding(self):
        settlement, report, advance = self._new(funding=None)
        self.assertFalse(settlement.funding_known)
        self.assertEqual(settlement.direction, 'unknown')
        settlement.action_submit(settlement.revision)
        with self.assertRaises(ValidationError):
            self._as(settlement, self.finance).action_approve('Missing funding proof', settlement.revision)
        self._as(settlement, self.cash).action_confirm_no_funding('SYNTHETIC-NO-FUNDS', 'Reconciled no advance payment', settlement.revision)
        self._as(settlement, self.finance).action_approve('Known funding basis', settlement.revision)
        self.assertEqual(settlement.direction, 'topup')
        self.assertEqual(settlement.difference_amount, 100000)
        self._record(settlement)
        self._as(settlement, self.finance).action_close('Reimbursement recorded', settlement.revision)

    def test_05_pending_advance_cannot_be_assumed_zero(self):
        settlement, report, advance = self._new(pending=True)
        self.assertFalse(settlement.funding_known)
        with self.assertRaises(ValidationError):
            self._as(settlement, self.cash).action_confirm_no_funding('NO-PROOF', 'Still executable', settlement.revision)
        advance.action_cancel('Advance not needed', 1)
        settlement.trip_id.action_no_advance()
        self._as(settlement, self.cash).action_confirm_no_funding('CONFIRMED-NO-ADVANCE', 'No advance was paid', settlement.revision)
        self._approve(settlement)
        with self.assertRaises(ValidationError):
            advance.action_revise('Cannot reopen frozen funding', 1)

    def test_06_uncertain_advance_blocks_cancel_and_requires_reconciliation(self):
        settlement, report, advance = self._new(pending=True)
        cash = self._as(advance, self.cash)
        with self.assertRaises(ValidationError):
            cash.action_record_disbursement(100000, 'DIRECT-BYPASS', fields.Date.today(), 1)
        cash.action_start_disbursement('UNCERTAIN-ADVANCE', 'External operation being executed', 1)
        with self.assertRaises(ValidationError):
            advance.action_cancel('Unsafe cancel', 1)
        with self.assertRaises(ValidationError):
            advance.action_revise('Unsafe reset', 1)
        with self.assertRaises(ValidationError):
            cash.action_start_disbursement('BLIND-RETRY', 'Cannot resend', 1)
        cash.action_confirm_no_payment('EXTERNAL-NO-PAYMENT', 'Checked external outcome', 1)
        advance.action_cancel('Known no execution', 1)
        settlement.trip_id.action_no_advance()
        self._as(settlement, self.cash).action_confirm_no_funding('NO-FUNDS-AFTER-RECONCILE', 'No advance paid', settlement.revision)
        self._approve(settlement)

    def test_07_approved_settlement_locks_expense_and_new_advance(self):
        settlement, report, advance = self._new(funding=None)
        self._as(settlement, self.cash).action_confirm_no_funding('NO-FUNDS-LOCK', 'No advance paid', settlement.revision)
        self._approve(settlement)
        with self.assertRaises(ValidationError):
            report.action_revise('Cannot replace approved comparison', report.revision)
        with self.assertRaises(ValidationError):
            self._as(self.env['ps.te.trip.advance'], self.owner).create({
                'trip_id': settlement.trip_id.id, 'requested_amount': 10000, 'purpose': 'Late advance',
            })
        self._as(settlement, self.finance).action_return('Expense correction required', settlement.revision)
        self.assertFalse(report.basis_locked)
        self.assertFalse(settlement.trip_id.funding_lock_settlement_id)
        report.action_revise('Now correction is explicit', report.revision)

    def test_08_stale_expense_and_settlement_revisions_fail(self):
        settlement, report, advance = self._new()
        settlement.action_submit(1)
        report.action_revise('Changed employee facts', report.revision)
        with self.assertRaises(ValidationError):
            self._as(settlement, self.finance).action_approve('Old amount', 1)
        report.action_submit(report.revision)
        line = report.line_ids
        self._as(report, self.finance).action_review_line(line.id, 'accepted', 'Reviewed new version', 100000, report.revision)
        settlement.action_refresh('Update exact expense basis', 1)
        with self.assertRaises(ValidationError):
            settlement.action_submit(1)
        self._approve(settlement)

    def test_09_cash_uncertainty_blocks_close_and_reset(self):
        settlement, report, advance = self._new(accepted=150000)
        self._approve(settlement)
        cash = self._as(settlement, self.cash)
        cash.action_start_cash('UNCERTAIN-SETTLEMENT', 'Possible external movement', settlement.revision)
        with self.assertRaises(ValidationError):
            self._as(settlement, self.finance).action_close('Unknown result', settlement.revision)
        with self.assertRaises(ValidationError):
            self._as(settlement, self.finance).action_return('Unsafe reset', settlement.revision)
        with self.assertRaises(ValidationError):
            cash.action_start_cash('BLIND-SETTLEMENT-RETRY', 'Retry', settlement.revision)
        cash.action_confirm_cash_not_executed('CHECKED-NONE', 'Verified no external execution', settlement.revision)
        self.assertEqual(settlement.cash_outcome, 'not_started')
        self._record(settlement)
        with self.assertRaises(ValidationError):
            self._as(settlement, self.finance).action_return('Cannot erase payment', settlement.revision)

    def test_10_reference_uniqueness_spans_advance_and_settlement(self):
        settlement, report, advance = self._new(accepted=150000)
        self._approve(settlement)
        cash = self._as(settlement, self.cash)
        cash.action_start_cash('CROSS-FLOW-ATTEMPT', 'Prepare', settlement.revision)
        with self.assertRaises(ValidationError):
            cash.action_record_cash(50000, advance.cash_reference, fields.Date.today(), settlement.revision)
        self.assertFalse(settlement.cash_event_id)
        self.assertEqual(settlement.cash_outcome, 'uncertain')

    def test_11_roles_and_company_isolation(self):
        settlement, report, advance = self._new(accepted=150000)
        settlement.action_submit(1)
        for user in (self.owner, self.cash, self.manager, self.other):
            with self.assertRaises(AccessError):
                self._as(settlement, user).action_approve('Wrong role', 1)
        self._as(settlement, self.finance).action_approve('Correct role', 1)
        for user in (self.owner, self.finance, self.manager, self.other):
            with self.assertRaises(AccessError):
                self._as(settlement, user).action_start_cash('WRONG', 'Wrong role', 1)
        self.assertFalse(self._as(self.env['ps.te.settlement'], self.other).search([('id', '=', settlement.id)]))
        with self.assertRaises(AccessError):
            self._as(report.line_ids[0].evidence_ids.attachment_id, self.cash).read(['datas'])

    def test_12_direct_forgery_and_closed_immutability(self):
        settlement, report, advance = self._new()
        with self.assertRaises(AccessError):
            settlement.write({'state': 'closed', 'funding_amount': 0})
        with self.assertRaises(AccessError):
            self._as(self.env['ps.te.cash.event'], self.owner).create({'amount': 1})
        self._approve(settlement)
        self._as(settlement, self.finance).action_close('Explicit closure', settlement.revision)
        with self.assertRaises(AccessError):
            settlement.unlink()
        with self.assertRaises(AccessError):
            settlement.event_ids[:1].write({'snapshot': '{}'})
        with self.assertRaises(AccessError):
            advance.cash_event_id.write({'amount': 1})
        with self.assertRaises(ValidationError):
            self._as(settlement, self.finance).action_return('Cannot reopen closed', settlement.revision)

    def test_13_context_defaults_cannot_forge_workflow_or_cash(self):
        draft = self._as(self.env['ps.te.trip.request'], self.owner).with_context(
            default_case_status='workflow_closed', default_case_closed_by_id=self.owner.id,
            default_funding_lock_settlement_id=123456,
        ).create({'purpose': 'Synthetic forged defaults', 'destination': 'Synthetic location',
                  'start_date': '2026-11-01', 'end_date': '2026-11-03'})
        self.assertEqual(draft.case_status, 'open')
        self.assertFalse(draft.case_closed_by_id)
        self.assertFalse(draft.funding_lock_settlement_id)
        trip = TestTripAdvance._new_trip(self.env, {'owner': self.owner, 'manager': self.manager})
        trip.action_no_advance()
        report = self._as(self.env['ps.te.expense.report'], self.owner).with_context(
            default_basis_locked=True, default_reviewed_revision=999, default_reviewed_at=fields.Datetime.now(),
        ).create({'trip_id': trip.id})
        self.assertFalse(report.basis_locked)
        self.assertFalse(report.reviewed_revision)
        line = report.action_add_line('Synthetic expense', 100000, fields.Date.today(), report.revision)
        report.action_upload_evidence(line, 'synthetic.pdf', base64.b64encode(TestExpenseEvidence._pdf()), report.revision)
        report.action_submit(report.revision)
        self._as(report, self.finance).action_review_line(line, 'accepted', 'Reviewed', 100000, report.revision)
        settlement = self._as(self.env['ps.te.settlement'], self.owner).with_context(
            default_cash_event_id=123456, default_closed_by_id=self.owner.id,
            default_cash_outcome='recorded', default_accounting_status='forged',
        ).create({'trip_id': trip.id})
        self.assertFalse(settlement.cash_event_id)
        self.assertEqual(settlement.cash_outcome, 'not_started')
        self.assertFalse(settlement.closed_by_id)
        self.assertEqual(settlement.accounting_status, 'not_verified')

    def test_14_zero_expense_no_funding_still_requires_confirmation_and_close(self):
        settlement, report, advance = self._new(accepted=0, funding=None)
        self.assertFalse(settlement.funding_known)
        self._as(settlement, self.cash).action_confirm_no_funding('ZERO-CASE-NO-FUNDING', 'No payment occurred', settlement.revision)
        self.assertEqual(settlement.direction, 'balanced')
        self._approve(settlement)
        self.assertEqual(settlement.state, 'approved')
        self._as(settlement, self.finance).action_close('Explicit zero-obligation closure', settlement.revision)
        self.assertFalse(settlement.cash_event_id)

    def test_15_native_settlement_wizard_and_forms(self):
        settlement, report, advance = self._new()
        model = self._as(self.env['ps.te.settlement.wizard'], self.owner).with_context(**settlement.action_open_operation()['context'])
        with Form(model) as wizard:
            wizard.operation = 'submit'
        wizard.record.action_apply()
        Form(self._as(settlement, self.finance))
        self.assertEqual(settlement.state, 'submitted')

    def test_16_competing_expense_revision_and_approval_cannot_mix_bases(self):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            users = {role: env['res.users'].browse(uid) for role, uid in self.race_users.items()}
            settlement, report, advance = self._case(env, users)
            settlement.action_submit(1)
            settlement_id, report_id, report_revision = settlement.id, report.id, report.revision
            cr.commit()
        context = {'allowed_company_ids': [self.race_company]}
        with self.registry.cursor() as finance_cr, self.registry.cursor() as owner_cr:
            finance = api.Environment(finance_cr, self.race_users['finance'], context)['ps.te.settlement'].browse(settlement_id)
            owner_report = api.Environment(owner_cr, self.race_users['owner'], context)['ps.te.expense.report'].browse(report_id)
            finance._lock()
            with self.assertRaises(LockError):
                owner_report.action_revise('Concurrent change', report_revision)
            owner_cr.rollback()
            finance.action_approve('Exact frozen comparison', 1)
            finance_cr.commit()
        with self.registry.cursor() as cr:
            report = api.Environment(cr, self.race_users['owner'], context)['ps.te.expense.report'].browse(report_id)
            with self.assertRaises(ValidationError):
                report.action_revise('Locked', report_revision)

    def test_17_legacy_funding_index_preserves_original_facts(self):
        settlement, report, advance = self._new(pending=True)
        original_time = fields.Datetime.subtract(fields.Datetime.now(), hours=1)
        reference = 'SYNTHETIC-LEGACY-' + uuid.uuid4().hex
        # Trusted test seeding emulates the pre-registry installed schema, not
        # an exposed workflow action or permission to rewrite actual payments.
        super(PsTeTripAdvance, advance.sudo()).write({
            'state': 'disbursed', 'disbursed_amount': 100000,
            'disbursed_by_id': self.cash.id, 'disbursed_at': original_time,
            'disbursement_date': fields.Date.today(), 'cash_reference': reference,
        })
        self.assertFalse(advance.cash_event_id)
        settlement.action_refresh('Index attributed legacy funding', settlement.revision)
        event = advance.cash_event_id
        self.assertTrue(event)
        self.assertEqual(event.actor_id, self.cash)
        self.assertEqual(event.recorded_at, original_time)
        self.assertEqual(event.external_reference, reference)
        self.assertEqual(event.amount, 100000)
        self.assertTrue(settlement.funding_known)
        settlement.action_refresh('Repeat indexing without a second movement', settlement.revision)
        self.assertEqual(advance.cash_event_id, event)
        self.assertEqual(self.env['ps.te.cash.event'].sudo().search_count([
            ('advance_id', '=', advance.id),
        ]), 1)
