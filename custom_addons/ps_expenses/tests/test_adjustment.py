"""Original financial closure is history; adjustment versions are separate."""
import base64
from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged

from .test_settlement import TestSettlement
from .test_advance import TestTripAdvance
from .test_expenses import TestExpenseEvidence


@tagged('post_install', '-at_install')
class TestFinancialAdjustment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_id, actors = TestSettlement._fixture(cls.env)
        cls.users = {role: cls.env['res.users'].browse(uid) for role, uid in actors.items()}

    def _original(self):
        settlement, report, advance = TestSettlement._case(self.env, self.users)
        settlement.action_submit(settlement.revision)
        settlement.with_user(self.users['finance']).action_approve('Synthetic original approval', settlement.revision)
        settlement.with_user(self.users['finance']).action_close('Synthetic original closure', settlement.revision)
        return settlement, report, advance

    def _adjust(self, trip):
        case = self.env['ps.te.correction'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'trip_id': trip.id, 'category': 'basis',
                'description': 'Synthetic versioned correction', 'expected_revision': trip.preparing_revision})
        adjustment = self.env['ps.te.adjustment'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'correction_id': case.id,
                'reason': 'Synthetic new full expense basis', 'expected_revision': case.revision})
        return adjustment

    def _review(self, adjustment, amount):
        adjustment.action_copy_previous_basis('Synthetic owner carries previous complete claims', adjustment.revision)
        report = adjustment.report_id
        line = report.line_ids
        report.action_edit_line(line.id, line.description, amount, line.expense_date, report.revision)
        report.action_submit(report.revision)
        report.with_user(self.users['finance']).action_review_line(
            line.id, 'accepted', 'Synthetic fresh expense decision', amount, report.revision)

    def _authorize(self, adjustment):
        finance = adjustment.with_user(self.users['finance'])
        finance.action_propose_basis('Synthetic exact cumulative difference', adjustment.revision)
        adjustment.with_user(self.users['cash']).action_confirm_cash(
            'SYNTHETIC-CUMULATIVE-CHECK', 'Synthetic independent check of external facts', adjustment.revision)
        finance.action_authorize('Synthetic final authorization', adjustment.revision)

    def _pay(self, adjustment):
        cash = adjustment.with_user(self.users['cash'])
        cash.action_start_cash('SYNTHETIC-ADJUSTMENT-ATTEMPT-' + str(adjustment.id), 'Synthetic prepared movement', adjustment.revision)
        reference = 'SYNTHETIC-ADJUSTMENT-CASH-' + str(adjustment.id)
        cash.action_record_cash(abs(adjustment.difference_amount), reference, fields.Date.today(), adjustment.revision)
        return reference

    def test_01_separate_report_retains_original_and_reuses_bytes_without_duplicates(self):
        settlement, original, advance = self._original()
        before = (original.revision, original.line_ids.ids, original.accepted_total, original.event_ids.ids)
        count = self.env['ps.te.expense.evidence'].search_count([])
        adjustment = self._adjust(settlement.trip_id)
        self.assertNotEqual(adjustment.report_id, original)
        self.assertFalse(adjustment.report_id.original_trip_id)
        self.assertEqual(original.original_trip_id, settlement.trip_id)
        adjustment.action_copy_previous_basis('Synthetic explicit carry-forward', adjustment.revision)
        new_line = adjustment.report_id.line_ids
        self.assertFalse(new_line.evidence_ids)
        self.assertEqual(new_line._active_proofs(), original.line_ids._active_proofs())
        self.assertEqual(self.env['ps.te.expense.evidence'].search_count([]), count)
        self.assertEqual((original.revision, original.line_ids.ids, original.accepted_total, original.event_ids.ids), before)
        self.assertEqual(settlement.trip_id.expense_report_id, original)
        self.assertEqual(settlement.state, 'closed')
        with self.assertRaises(ValidationError):
            original.action_revise('Must not reopen original closure', original.revision)

    def test_02_topup_requires_new_basis_independent_cash_and_explicit_closure(self):
        settlement, original, advance = self._original()
        adjustment = self._adjust(settlement.trip_id)
        self._review(adjustment, 150000)
        with self.assertRaises(ValidationError):
            adjustment.with_user(self.users['finance']).action_authorize('No independent check yet', adjustment.revision)
        self._authorize(adjustment)
        self.assertEqual(adjustment.difference_amount, 50000)
        self.assertTrue(settlement.trip_id.correction_hold)
        with self.assertRaises(ValidationError):
            adjustment.with_user(self.users['finance']).action_close('No actual money recorded', adjustment.revision)
        reference = self._pay(adjustment)
        adjustment.with_user(self.users['cash']).action_record_cash(50000, reference, fields.Date.today(), adjustment.revision)
        self.assertEqual(adjustment.cash_event_id.kind, 'topup')
        self.assertEqual(adjustment.cash_event_id.adjustment_id, adjustment)
        adjustment.with_user(self.users['finance']).action_close('Synthetic full resolution', adjustment.revision)
        self.assertEqual(adjustment.state, 'closed')
        self.assertEqual(settlement.trip_id.effective_expense_report_id, adjustment.report_id)
        self.assertEqual(settlement.trip_id.expense_report_id, original)
        self.assertEqual(original.accepted_total, 100000)
        self.assertFalse(settlement.trip_id.correction_hold)
        self.assertEqual(adjustment.accounting_status, 'not_verified')

    def test_03_second_round_returns_only_difference_from_cumulative_cash(self):
        settlement, original, advance = self._original()
        first = self._adjust(settlement.trip_id)
        self._review(first, 150000)
        self._authorize(first)
        self._pay(first)
        first.with_user(self.users['finance']).action_close('Synthetic round one', first.revision)
        second = self._adjust(settlement.trip_id)
        self.assertEqual(second.previous_report_id, first.report_id)
        self._review(second, 120000)
        self._authorize(second)
        self.assertEqual(second.retained_amount, 150000)
        self.assertEqual(second.difference_amount, -30000)
        self._pay(second)
        second.with_user(self.users['finance']).action_close('Synthetic round two', second.revision)
        self.assertEqual(second.cash_event_id.kind, 'return')
        self.assertEqual(self.env['ps.te.cash.event']._verified_net(settlement.trip_id)['amount'], 120000)
        self.assertEqual(first.cash_event_id.amount, 50000)
        self.assertEqual(advance.cash_event_id.amount, 100000)
        self.assertEqual(original.accepted_total, 100000)

    def test_04_equal_adjustment_closes_without_fake_cash(self):
        settlement, original, advance = self._original()
        adjustment = self._adjust(settlement.trip_id)
        self._review(adjustment, 100000)
        self._authorize(adjustment)
        with self.assertRaises(ValidationError):
            adjustment.with_user(self.users['cash']).action_start_cash('FALSE-ZERO-CASH', 'No movement needed', adjustment.revision)
        adjustment.with_user(self.users['finance']).action_close('Synthetic explicit equal closure', adjustment.revision)
        self.assertFalse(adjustment.cash_event_id)
        self.assertEqual(adjustment.correction_id.state, 'adjusted')

    def test_05_proof_references_respect_role_and_source_boundaries(self):
        settlement, original, advance = self._original()
        adjustment = self._adjust(settlement.trip_id)
        adjustment.action_copy_previous_basis('Synthetic carry forward', adjustment.revision)
        report = adjustment.report_id
        link = report.line_ids.proof_link_ids
        for role in ('cash', 'manager', 'other'):
            with self.assertRaises(AccessError):
                link.with_user(self.users[role]).read(['filename'])
            with self.assertRaises(AccessError):
                original.line_ids._active_proofs().with_user(self.users[role]).action_download()
        other_settlement, other_report, _ = TestSettlement._case(self.env, self.users)
        with self.assertRaises(ValidationError):
            report.action_reuse_evidence(report.line_ids.id, other_report.line_ids._active_proofs().id, report.revision)
        with self.assertRaises(AccessError):
            link.write({'evidence_id': other_report.line_ids._active_proofs().id})
        with self.assertRaises(AccessError):
            self.env['ps.te.expense.proof.link'].with_user(self.users['owner']).create({'line_id': report.line_ids.id})
        link.action_supersede('Synthetic remove new-version reference only', report.revision)
        self.assertTrue(link.superseded)
        self.assertFalse(original.line_ids._active_proofs().superseded)
        self.assertFalse(report.line_ids._active_proofs())

    def test_06_uncertain_cash_cannot_withdraw_or_pay_partial(self):
        settlement, original, advance = self._original()
        adjustment = self._adjust(settlement.trip_id)
        self._review(adjustment, 150000)
        self._authorize(adjustment)
        cash = adjustment.with_user(self.users['cash'])
        cash.action_start_cash('SYNTHETIC-UNCERTAIN-ATTEMPT', 'Synthetic uncertain execution', adjustment.revision)
        with self.assertRaises(ValidationError):
            adjustment.action_withdraw('Cannot discard uncertainty', adjustment.revision)
        with self.assertRaises(ValidationError):
            cash.action_record_cash(10000, 'SYNTHETIC-PARTIAL', fields.Date.today(), adjustment.revision)
        with self.assertRaises(ValidationError):
            cash.action_start_cash('BLIND-NEW-ATTEMPT', 'Do not resend blindly', adjustment.revision)
        cash.action_confirm_not_executed('SYNTHETIC-NO-EXECUTION', 'Synthetic checked external system', adjustment.revision)
        self._pay(adjustment)
        adjustment.with_user(self.users['finance']).action_close('Synthetic resolved uncertainty', adjustment.revision)

    def test_07_unexecuted_withdrawal_preserves_history_and_hold(self):
        settlement, original, advance = self._original()
        adjustment = self._adjust(settlement.trip_id)
        adjustment.action_withdraw('Synthetic withdraw before execution', adjustment.revision)
        self.assertEqual(adjustment.state, 'withdrawn')
        self.assertTrue(adjustment.report_id.basis_locked)
        self.assertTrue(adjustment.correction_id.active_trip_id)
        self.assertTrue(settlement.trip_id.correction_hold)
        with self.assertRaises(AccessError):
            adjustment.write({'state': 'closed', 'accepted_amount': 1})
        with self.assertRaises(AccessError):
            adjustment.unlink()

    def test_08_context_cannot_create_or_approve_an_adjustment_report(self):
        settlement, original, advance = self._original()
        adjustment = self._adjust(settlement.trip_id)
        with self.assertRaises(AccessError):
            self.env['ps.te.expense.report'].with_user(self.users['owner']).create({
                'trip_id': settlement.trip_id.id, 'adjustment_id': adjustment.id})
        with self.assertRaises(AccessError):
            adjustment.with_user(self.users['cash']).action_propose_basis('Wrong role', adjustment.revision)
        with self.assertRaises(AccessError):
            adjustment.with_user(self.users['owner']).action_authorize('Self approval', adjustment.revision)
        with self.assertRaises(ValidationError):
            adjustment.correction_id.action_refresh('Must explicitly withdraw the unexecuted adjustment', adjustment.correction_id.revision)

    def test_09_reassigned_finance_sees_only_specifically_linked_original_proof(self):
        settlement, original, advance = self._original()
        unrelated, unrelated_report, _ = TestSettlement._case(self.env, self.users)
        new_finance = self.users['other']
        new_finance.write({'group_ids': [Command.link(self.env.ref('ps_expenses.group_ps_te_finance').id)]})
        self.env['res.company'].browse(self.company_id).ps_te_finance_reviewer_id = new_finance
        self.assertFalse(original.accepted_basis_ready)
        adjustment = self._adjust(settlement.trip_id)
        adjustment.action_copy_previous_basis('Synthetic explicit controlled proof reuse', adjustment.revision)
        source = original.line_ids._active_proofs()
        self.assertTrue(source.with_user(new_finance).read(['filename']))
        self.assertTrue(source.with_user(new_finance).action_download()['url'])
        source.attachment_id.with_user(new_finance)._check_expense_content_user()
        for record in (source, unrelated_report.line_ids._active_proofs()):
            with self.assertRaises(AccessError):
                record.with_user(self.users['finance']).read(['filename'])
        with self.assertRaises(AccessError):
            unrelated_report.line_ids._active_proofs().with_user(new_finance).read(['filename'])
        with self.assertRaises(AccessError):
            original.with_user(new_finance).read(['claimed_total'])

    def test_10_completed_adjustment_marks_old_reports_historical(self):
        settlement, original, advance = self._original()
        adjustment = self._adjust(settlement.trip_id)
        self._review(adjustment, 150000)
        self._authorize(adjustment)
        self._pay(adjustment)
        adjustment.with_user(self.users['finance']).action_close('Synthetic final outcome', adjustment.revision)
        renderer = self.env['ir.actions.report'].with_user(self.users['owner']).with_context(allowed_company_ids=[self.company_id])
        old, _ = renderer._render_qweb_html('ps_expenses.settlement_summary', [settlement.id])
        self.assertIn('Historical settlement', old.decode())
        self.assertNotIn('id="current-comparison"', old.decode())
        expense, _ = renderer._render_qweb_html('ps_expenses.expense_summary', [original.id])
        self.assertIn('Historical expense version', expense.decode())

    def test_11_verified_cash_entry_correction_requires_only_remaining_real_movement(self):
        settlement, original, advance = self._original()
        case = self.env['ps.te.correction'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'trip_id': settlement.trip_id.id, 'category': 'funding',
                'description': 'Synthetic mis-entered funding data', 'expected_revision': settlement.trip_id.preparing_revision})
        record = self.env['ps.te.cash.rectification'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'correction_id': case.id, 'root_event_id': advance.cash_event_id.id,
                'amount': 75000, 'reference': advance.cash_reference, 'date': fields.Date.today(),
                'reason': 'Synthetic actual advance was 75000, not another payment', 'expected_revision': case.revision})
        record.with_user(self.users['finance']).action_review('approved', 'Synthetic corrected entry approved')
        record.with_user(self.users['cash']).action_verify('SYNTHETIC-ACTUAL-ADVANCE-FACT', 'Synthetic independent fact check')
        adjustment = self.env['ps.te.adjustment'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'correction_id': case.id,
                'reason': 'Synthetic complete the remaining obligation', 'expected_revision': case.revision})
        self._review(adjustment, 100000)
        self._authorize(adjustment)
        self.assertEqual(adjustment.retained_amount, 75000)
        self.assertEqual(adjustment.difference_amount, 25000)
        self._pay(adjustment)
        adjustment.with_user(self.users['finance']).action_close('Synthetic fact correction and difference completed', adjustment.revision)
        self.assertEqual(self.env['ps.te.cash.event'].search_count([('trip_id', '=', settlement.trip_id.id)]), 2)
        self.assertEqual(self.env['ps.te.cash.event']._verified_net(settlement.trip_id)['amount'], 100000)
        self.assertEqual(advance.cash_event_id.amount, 100000)
        self.assertEqual(record.proposed_amount, 75000)
        self.assertFalse(case.active_trip_id)

    def test_12_native_adjustment_wizard_keeps_exact_parent_and_revision(self):
        settlement, original, advance = self._original()
        adjustment = self._adjust(settlement.trip_id)
        action = adjustment.action_open_operation()
        model = self.env[action['res_model']].with_user(self.users['owner']).with_context(
            **action['context'], allowed_company_ids=[self.company_id])
        with Form(model, view='ps_expenses.view_financial_adjustment_wizard') as form:
            form.operation = 'copy'
            form.reason = 'Synthetic native form carries claims, not prior approval'
        form.record.action_apply()
        self.assertTrue(adjustment.report_id.line_ids)
        self.assertEqual(adjustment.report_id.state, 'draft')
        self.assertEqual(adjustment.report_id.line_ids.decision, 'pending')
        self.assertTrue(settlement.trip_id.correction_hold)

    def _new_first_basis(self, paid=True):
        trip = TestTripAdvance._new_trip(self.env, self.users)
        advance = self.env['ps.te.trip.advance'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'trip_id': trip.id, 'purpose': 'Synthetic first basis',
                'requested_amount': 100000})
        advance.action_submit(advance.revision)
        advance.with_user(self.users['finance']).action_review('approved', 'Synthetic advance approval', advance.revision, 100000)
        if paid:
            cash = advance.with_user(self.users['cash'])
            cash.action_start_disbursement('SYNTHETIC-FIRST-BASIS-ATTEMPT', 'Synthetic prepared advance', advance.revision)
            cash.action_record_disbursement(100000, 'SYNTHETIC-FIRST-BASIS-CASH', fields.Date.today(), advance.revision)
        return trip, advance, self._adjust(trip)

    def _author_first_basis(self, adjustment, amount):
        report = adjustment.report_id
        line = report.action_add_line('Synthetic newly authored expense', amount, fields.Date.today(), report.revision)
        report.action_upload_evidence(line, 'synthetic-new-basis.pdf', base64.b64encode(TestExpenseEvidence._pdf()), report.revision)
        report.action_submit(report.revision)
        report.with_user(self.users['finance']).action_review_line(line, 'accepted', 'Synthetic fresh first review', amount, report.revision)

    def test_13_paid_advance_without_original_expense_report_has_a_full_adjustment_path(self):
        trip, advance, adjustment = self._new_first_basis()
        self.assertFalse(trip.expense_report_id)
        self.assertFalse(adjustment.previous_report_id)
        with self.assertRaises(ValidationError):
            adjustment.action_copy_previous_basis('No source report exists', adjustment.revision)
        self._author_first_basis(adjustment, 100000)
        self._authorize(adjustment)
        adjustment.with_user(self.users['finance']).action_close('Synthetic first basis completed', adjustment.revision)
        self.assertEqual(trip.case_status, 'workflow_closed')
        self.assertFalse(trip.expense_report_id)
        self.assertEqual(trip.effective_expense_report_id, adjustment.report_id)
        self.assertEqual(trip.action_open_expenses()['res_model'], 'hr.expense')
        self.assertEqual(trip.action_open_expenses()['domain'], [('ps_report_id', '=', adjustment.report_id.id)])
        self.assertEqual(trip.action_open_settlement()['res_model'], 'ps.te.adjustment')

    def test_14_unexecuted_advance_requires_owner_declaration_and_independent_no_funding(self):
        trip, advance, adjustment = self._new_first_basis(paid=False)
        cash = adjustment.with_user(self.users['cash'])
        with self.assertRaises(ValidationError):
            cash.action_confirm_no_funding('FALSE-NO-FUNDING', 'Advance still executable', adjustment.revision)
        adjustment.action_declare_no_advance('Synthetic owner cancels unexecuted advance under exact held case', adjustment.revision)
        self.assertEqual(advance.state, 'cancelled')
        self.assertEqual(trip.advance_choice, 'not_requested')
        self.assertIsNone(self.env['ps.te.cash.event']._verified_net(trip)['amount'])
        cash.action_confirm_no_funding('SYNTHETIC-ADJUSTMENT-NO-FUNDING', 'Synthetic independently checked no payment', adjustment.revision)
        self.assertEqual(self.env['ps.te.cash.event']._verified_net(trip)['amount'], 0)
        self._author_first_basis(adjustment, 100000)
        self._authorize(adjustment)
        self.assertEqual(adjustment.difference_amount, 100000)
        self._pay(adjustment)
        adjustment.with_user(self.users['finance']).action_close('Synthetic exact reimbursement', adjustment.revision)
        self.assertFalse(advance.cash_event_id)
        self.assertEqual(self.env['ps.te.cash.event'].search_count([('trip_id', '=', trip.id)]), 1)
        with self.assertRaises(ValidationError):
            advance.action_revise('Must not reopen old funding after completed adjustment', advance.revision)

    def test_15_paid_advance_cannot_be_declared_or_verified_as_no_funding(self):
        trip, advance, adjustment = self._new_first_basis()
        with self.assertRaises(ValidationError):
            adjustment.action_declare_no_advance('Cannot erase recorded disbursement', adjustment.revision)
        with self.assertRaises(ValidationError):
            adjustment.with_user(self.users['cash']).action_confirm_no_funding(
                'FALSE-ZERO', 'Cannot zero a recorded advance', adjustment.revision)
        self.assertEqual(advance.cash_event_id.amount, 100000)
        self.assertEqual(self.env['ps.te.cash.event']._verified_net(trip)['amount'], 100000)

    def _amend(self, trip):
        amendment = self.env['ps.te.trip.amendment'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'trip_id': trip.id, 'purpose': trip.purpose + ' corrected',
                'destination': trip.destination + ' revised', 'start_date': trip.start_date, 'end_date': trip.end_date,
                'reason': 'Synthetic changed trip facts', 'expected_revision': trip.preparing_revision})
        amendment.with_user(self.users['manager']).action_decide('approved', 'Synthetic fresh manager decision', amendment.revision)
        return amendment

    def _amendment_adjustment(self, amendment):
        action = amendment.action_start_financial_adjustment('Synthetic financial revalidation after manager review', amendment.revision)
        return self.env['ps.te.adjustment'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).browse(action['res_id'])

    def test_16_closed_trip_changes_need_manager_and_new_financial_basis(self):
        settlement, original, advance = self._original()
        trip = settlement.trip_id
        old = (trip.purpose, trip.destination, trip.preparing_revision, trip.event_ids.ids, trip.submission_receipt)
        amendment = self._amend(trip)
        self.assertEqual(amendment.state, 'finance')
        self.assertEqual(trip.purpose, old[0])
        adjustment = self._amendment_adjustment(amendment)
        self.assertEqual(adjustment.amendment_id, amendment)
        self._review(adjustment, 100000)
        self.assertEqual(trip.purpose, old[0])
        self._authorize(adjustment)
        self.assertEqual(trip.purpose, amendment.purpose)
        self.assertEqual(trip.preparing_revision, old[2] + 1)
        self.assertEqual(trip.decision_by_id, self.users['manager'])
        self.assertEqual(amendment.financial_applied_by_id, self.users['finance'])
        self.assertNotEqual(trip.submission_receipt, old[4])
        self.assertTrue(set(old[3]).issubset(trip.event_ids.ids))
        self.assertTrue(trip.correction_hold)
        adjustment.with_user(self.users['finance']).action_close('Synthetic fully revalidated amended trip', adjustment.revision)
        self.assertFalse(trip.correction_hold)
        self.assertEqual(settlement.state, 'closed')
        self.assertEqual(original.accepted_total, 100000)
        self.assertEqual(advance.cash_event_id.amount, 100000)
        with self.assertRaises(AccessError):
            adjustment.with_user(self.users['manager']).read(['accepted_amount'])
        with self.assertRaises(AccessError):
            adjustment.report_id.line_ids._active_proofs().with_user(self.users['manager']).action_download()

    def test_17_financial_amendment_without_old_expenses_still_gets_fresh_review(self):
        trip = TestTripAdvance._new_trip(self.env, self.users)
        advance = self.env['ps.te.trip.advance'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company_id]).create({'trip_id': trip.id, 'purpose': 'Synthetic unexecuted advance', 'requested_amount': 100000})
        advance.action_submit(advance.revision)
        advance.with_user(self.users['finance']).action_review('approved', 'Synthetic prior advance approval', advance.revision, 100000)
        amendment = self._amend(trip)
        adjustment = self._amendment_adjustment(amendment)
        old_purpose = trip.purpose
        adjustment.action_declare_no_advance('Synthetic owner withdraws obsolete unexecuted advance', adjustment.revision)
        adjustment.with_user(self.users['cash']).action_confirm_no_funding(
            'SYNTHETIC-AMEND-NO-FUNDING', 'Synthetic independent no-payment check', adjustment.revision)
        self._author_first_basis(adjustment, 100000)
        self._authorize(adjustment)
        self.assertNotEqual(trip.purpose, old_purpose)
        self.assertEqual(amendment.state, 'applied')
        self.assertEqual(advance.state, 'cancelled')
        self._pay(adjustment)
        adjustment.with_user(self.users['finance']).action_close('Synthetic completed first amended basis', adjustment.revision)
        with self.assertRaises(ValidationError):
            advance.with_user(self.users['cash']).action_start_disbursement('OLD-APPROVAL', 'Cannot reuse old authority', advance.revision)

    def test_18_revoked_manager_blocks_financial_application_without_changing_trip(self):
        settlement, original, advance = self._original()
        amendment = self._amend(settlement.trip_id)
        adjustment = self._amendment_adjustment(amendment)
        self._review(adjustment, 100000)
        old = (settlement.trip_id.purpose, settlement.trip_id.preparing_revision)
        self.users['manager'].active = False
        with self.assertRaises(ValidationError):
            adjustment.with_user(self.users['finance']).action_propose_basis('Revoked manager is not current authorization', adjustment.revision)
        self.assertEqual((settlement.trip_id.purpose, settlement.trip_id.preparing_revision), old)
        self.assertTrue(settlement.trip_id.correction_hold)

    def test_19_unapplied_amendment_has_explicit_owner_withdrawal(self):
        settlement, original, advance = self._original()
        trip = settlement.trip_id
        old = (trip.purpose, trip.preparing_revision)
        amendment = self._amend(trip)
        amendment.action_withdraw_unapplied('Synthetic owner abandons unapplied proposal', amendment.revision)
        self.assertEqual(amendment.state, 'withdrawn')
        self.assertEqual(amendment.decided_by_id, self.users['manager'])
        self.assertEqual(amendment.withdrawn_by_id, self.users['owner'])
        self.assertFalse(trip.correction_hold)
        self.assertEqual((trip.purpose, trip.preparing_revision), old)

    def test_20_adjustment_aggregate_report_never_exposes_private_claim_or_proof(self):
        settlement, original, advance = self._original()
        adjustment = self._adjust(settlement.trip_id)
        self._review(adjustment, 150000)
        self._authorize(adjustment)
        self.assertTrue(adjustment.money_comparison_current)
        self.assertEqual(adjustment.current_remaining_amount, 50000)
        renderer = self.env['ir.actions.report'].with_user(self.users['cash']).with_context(allowed_company_ids=[self.company_id])
        rendered, _ = renderer._render_qweb_html('ps_expenses.adjustment_summary', [adjustment.id])
        text = rendered.decode()
        self.assertIn('Recorded Financial Adjustment Summary', text)
        self.assertNotIn(original.line_ids.description, text)
        self.assertNotIn(original.line_ids._active_proofs().filename, text)
        self.assertNotIn('/web/content/', text)
        for role in ('manager', 'other'):
            with self.assertRaises(AccessError):
                renderer.with_user(self.users[role])._render_qweb_html('ps_expenses.adjustment_summary', [adjustment.id])
        self._pay(adjustment)
        adjustment.with_user(self.users['finance']).action_close('Synthetic current adjusted outcome', adjustment.revision)
        self.assertTrue(adjustment.money_comparison_current)
        self.assertEqual(adjustment.current_remaining_amount, 0)
        next_case = self._adjust(settlement.trip_id)
        adjustment.invalidate_recordset()
        self.assertFalse(adjustment.money_comparison_current)
        older, _ = renderer._render_qweb_html('ps_expenses.adjustment_summary', [adjustment.id])
        self.assertNotIn('id="current-adjustment-comparison"', older.decode())
        self.assertTrue(next_case.active_trip_id)
