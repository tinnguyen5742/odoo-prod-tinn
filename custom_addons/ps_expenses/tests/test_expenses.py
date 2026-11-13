import base64
import json
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from odoo import Command, SUPERUSER_ID, api, fields
from odoo.exceptions import AccessError, LockError, ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged

from .test_advance import TestTripAdvance


@tagged('post_install', '-at_install')
class TestExpenseEvidence(TransactionCase):

    @staticmethod
    def _fixture(env):
        company_id, users = TestTripAdvance._build_fixture(env)
        env['res.company'].browse(company_id).ps_te_expense_policy_reference = 'SYNTHETIC-EXPENSE-V1-' + uuid.uuid4().hex
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

    def _report(self, intent=True):
        trip = TestTripAdvance._new_trip(self.env, {'owner': self.owner, 'manager': self.manager})
        if intent:
            trip.action_no_advance()
        return self._as(self.env['ps.te.expense.report'], self.owner).create({'trip_id': trip.id})

    @staticmethod
    def _pdf():
        return b'%PDF-1.4\n% Synthetic fixture ' + uuid.uuid4().hex.encode() + b'\n%%EOF'

    def _line(self, report, amount=100000, proof=True):
        line_id = report.action_add_line('Synthetic employee expense', amount, fields.Date.today(), report.revision)
        line = self._as(self.env['ps.te.expense.line'].browse(line_id), self.owner)
        if proof:
            report.action_upload_evidence(line.id, 'synthetic.pdf', base64.b64encode(self._pdf()), report.revision)
        return line

    def _review(self, report, line, decision='accepted', amount=80000, reason='Synthetic policy review'):
        return self._as(report, self.finance).action_review_line(line.id, decision, reason, amount, report.revision)

    def test_01_claim_and_acceptance_totals_are_distinct(self):
        report = self._report()
        first = self._line(report)
        second = self._line(report, 70000, proof=False)
        report.action_submit(report.revision)
        report.action_submit(report.revision)
        self._review(report, first)
        self.assertEqual(first.claimed_amount, 100000)
        self.assertFalse(report.accepted_basis_ready)
        self.assertEqual(report.unresolved_total, 70000)
        self._review(report, second, 'refused', 0, 'Unsupported claim refused')
        self.assertEqual(report.state, 'reviewed')
        self.assertTrue(report.accepted_basis_ready)
        self.assertEqual((report.claimed_total, report.accepted_total, report.refused_total), (170000, 80000, 90000))
        self.assertEqual(report.reviewed_revision, report.revision)

    def test_02_missing_proof_cannot_be_accepted_but_can_be_returned(self):
        report = self._report()
        line = self._line(report, proof=False)
        report.action_submit(report.revision)
        with self.assertRaises(ValidationError):
            self._review(report, line)
        self._review(report, line, 'returned', 0, 'Please provide evidence')
        self.assertEqual(report.state, 'returned')
        self.assertFalse(report.accepted_basis_ready)
        report.action_revise('Evidence supplied', report.revision)
        report.action_upload_evidence(line.id, 'proof.pdf', base64.b64encode(self._pdf()), report.revision)
        report.action_submit(report.revision)
        self._review(report, line)
        self.assertTrue(report.accepted_basis_ready)

    def test_03_revision_invalidates_approval_but_preserves_history(self):
        report = self._report()
        line = self._line(report)
        report.action_submit(report.revision)
        revision = report.revision
        self._review(report, line)
        with self.assertRaises(ValidationError):
            report.action_edit_line(line.id, 'Silent edit', 90000, fields.Date.today(), revision)
        report.action_revise('Employee correction', revision)
        self.assertFalse(report.accepted_basis_ready)
        self.assertEqual(line.decision, 'pending')
        report.action_edit_line(line.id, 'Corrected description', 90000, fields.Date.today(), report.revision)
        report.action_submit(report.revision)
        with self.assertRaises(ValidationError):
            self._as(report, self.finance).action_review_line(line.id, 'accepted', 'Stale', 80000, revision)
        history = report.event_ids.filtered(lambda event: event.event_type == 'line_accepted')
        self.assertEqual(json.loads(history.snapshot)[0]['claimed'], 100000)
        self.assertEqual(json.loads(history.snapshot)[0]['accepted'], 80000)

    def test_04_wrong_roles_cannot_read_or_replace_claims(self):
        report = self._report()
        line = self._line(report)
        report.action_submit(report.revision)
        for user in (self.owner, self.cash, self.manager, self.other):
            with self.assertRaises(AccessError):
                self._as(report, user).action_review_line(line.id, 'accepted', 'Unauthorized', 80000, report.revision)
        for user in (self.cash, self.manager, self.other):
            self.assertFalse(self._as(self.env[report._name], user).search([('id', '=', report.id)]))
            self.assertFalse(self._as(self.env['ps.te.expense.evidence'], user).search([('report_id', '=', report.id)]))
        with self.assertRaises(AccessError):
            self._as(line, self.finance).write({'claimed_amount': 1})
        self.assertEqual(line.claimed_amount, 100000)

    def test_05_direct_crud_and_history_forgery_are_denied(self):
        report = self._report()
        line = self._line(report)
        event = report.event_ids[:1]
        for action in (
            lambda: report.write({'state': 'reviewed'}), lambda: report.unlink(), lambda: report.copy(),
            lambda: line.write({'accepted_amount': 100000}), lambda: line.unlink(),
            lambda: self._as(self.env['ps.te.expense.line'], self.owner).create({'report_id': report.id}),
            lambda: event.write({'snapshot': '[]'}), lambda: event.unlink(),
            lambda: self._as(self.env['ps.te.expense.event'], self.owner).create({'report_id': report.id}),
        ):
            with self.assertRaises(AccessError):
                action()

    def test_06_attachment_read_search_export_and_binary_lookup_boundaries(self):
        report = self._report()
        line = self._line(report)
        evidence = line.evidence_ids
        attachment = evidence.attachment_id
        self.assertTrue(attachment.read(['datas'])[0]['datas'])
        self.assertTrue(self._as(attachment, self.finance).read(['datas'])[0]['datas'])
        export_group = self.env.ref('base.group_allow_export')
        self.owner.write({'group_ids': [Command.link(export_group.id)]})
        self.assertTrue(attachment.export_data(['name', 'datas'])['datas'][0][1])
        for user in (self.other, self.manager, self.cash):
            user.write({'group_ids': [Command.link(export_group.id)]})
            protected = self._as(attachment, user)
            with self.assertRaises(AccessError):
                protected.read(['datas'])
            with self.assertRaises(AccessError):
                protected.export_data(['name', 'datas'])
            self.assertFalse(self._as(self.env['ir.attachment'], user).search([('id', '=', attachment.id)]))
            with self.assertRaises(AccessError):
                self._as(self.env['ir.binary'], user)._find_record(res_model='ir.attachment', res_id=attachment.id, access_token='forged')
            with self.assertRaises(AccessError):
                protected.sudo()._to_http_stream()
        with self.assertRaises(AccessError):
            attachment.generate_access_token()
        self.assertNotIn('access_token', evidence.action_download()['url'])

    def test_07_protected_attachment_cannot_be_shared_reparented_or_overwritten(self):
        report = self._report()
        evidence = self._line(report).evidence_ids
        attachment = evidence.attachment_id
        for vals in ({'public': True}, {'access_token': 'forged'}, {'raw': b'changed'}, {'res_id': False}, {'ps_te_evidence_id': False}, {'type': 'url', 'url': 'https://example.invalid'}):
            with self.assertRaises(AccessError):
                attachment.write(vals)
        with self.assertRaises(AccessError):
            attachment.unlink()
        with self.assertRaises(AccessError):
            evidence.write({'sha256': 'forged'})
        with self.assertRaises(AccessError):
            self._as(self.env['ir.attachment'], self.owner).create({
                'name': 'forged.pdf', 'res_model': report._name, 'res_id': report.id, 'public': True,
            })

    def test_08_duplicate_proof_and_invalid_uploads_are_refused(self):
        report = self._report()
        line = self._line(report, proof=False)
        payload = base64.b64encode(self._pdf())
        report.action_upload_evidence(line.id, 'proof.pdf', payload, report.revision)
        other_report = self._report()
        other_line = self._line(other_report, proof=False)
        with self.assertRaises(ValidationError):
            other_report.action_upload_evidence(other_line.id, 'renamed.pdf', payload, other_report.revision)
        for name, data in (
            ('script.html', base64.b64encode(b'<script>alert(1)</script>')),
            ('spoof.pdf', base64.b64encode(b'<html>not a PDF</html>')),
            ('../proof.pdf', base64.b64encode(self._pdf())),
            ('bad.pdf', b'not valid base64!'),
            ('large.pdf', base64.b64encode(b'%PDF-' + b'x' * (5 * 1024 * 1024))),
        ):
            with self.assertRaises(ValidationError):
                report.action_upload_evidence(line.id, name, data, report.revision)

    def test_09_superseded_proof_is_retained_and_cannot_be_changed_after_submission(self):
        report = self._report()
        line = self._line(report)
        evidence = line.evidence_ids
        raw = evidence.attachment_id.raw
        evidence.action_supersede('Wrong proof replaced', report.revision)
        self.assertEqual(evidence.attachment_id.raw, raw)
        self.assertTrue(evidence.superseded)
        report.action_upload_evidence(line.id, 'replacement.pdf', base64.b64encode(self._pdf()), report.revision)
        report.action_submit(report.revision)
        active = line.evidence_ids.filtered(lambda proof: not proof.superseded)
        with self.assertRaises(ValidationError):
            active.action_supersede('After submission', report.revision)
        self._review(report, line)
        self.assertEqual(len(line.evidence_ids), 2)

    def test_10_stale_mutations_and_conflicting_review_replay_fail(self):
        report = self._report()
        revision = report.revision
        line = self._line(report)
        with self.assertRaises(ValidationError):
            report.action_edit_line(line.id, 'Stale', 100, fields.Date.today(), revision)
        report.action_submit(report.revision)
        self._review(report, line)
        count = len(report.event_ids)
        self._review(report, line)
        self.assertEqual(len(report.event_ids), count)
        with self.assertRaises(ValidationError):
            self._review(report, line, 'refused', 0, 'Contradictory retry')

    def test_11_policy_and_assignment_changes_block_review_and_old_download_access(self):
        report = self._report()
        line = self._line(report)
        report.action_submit(report.revision)
        self.company.ps_te_expense_policy_reference = 'SYNTHETIC-EXPENSE-V2'
        with self.assertRaises(ValidationError):
            self._review(report, line)
        self.company.ps_te_finance_reviewer_id = False
        with self.assertRaises(AccessError):
            self._as(line.evidence_ids.attachment_id, self.finance)._can_return_content()
        self.assertFalse(self._as(self.env['ps.te.expense.evidence'], self.finance).search([('report_id', '=', report.id)]))

    def test_12_report_requires_approved_trip_and_declared_advance_intent(self):
        trip = self._as(self.env['ps.te.trip.request'], self.owner).create({'purpose': 'Unapproved'})
        with self.assertRaises(ValidationError):
            self._as(self.env['ps.te.expense.report'], self.owner).create({'trip_id': trip.id})
        report = self._report(intent=False)
        self._line(report)
        with self.assertRaises(ValidationError):
            report.action_submit(report.revision)
        report.trip_id.action_no_advance()
        report.action_submit(report.revision)
        with self.assertRaises(ValidationError):
            self._as(self.env['ps.te.expense.report'], self.owner).create({'trip_id': report.trip_id.id})

    def test_13_native_wizard_and_download_stream_force_private_nonexecutable_content(self):
        report = self._report()
        model = self._as(self.env['ps.te.expense.wizard'], self.owner).with_context(**report.action_open_operation()['context'])
        with Form(model) as wizard:
            wizard.operation = 'add'
            wizard.description = 'Expense through native wizard'
            wizard.amount = 100000
            wizard.expense_date = fields.Date.today()
        wizard.record.action_apply()
        line = report.line_ids
        report.action_upload_evidence(line.id, 'proof.pdf', base64.b64encode(self._pdf()), report.revision)
        attachment = line.evidence_ids.attachment_id
        with patch('odoo.addons.base.models.ir_attachment.request', SimpleNamespace(db=self.cr.dbname)):
            stream = self._as(self.env['ir.binary'], self.owner)._get_stream_from(attachment, mimetype='text/html')
        self.assertFalse(stream.public)
        self.assertEqual(stream.mimetype, 'application/octet-stream')
        Form(report)

    def test_14_current_company_and_membership_revocation_deny_proof(self):
        report = self._report()
        attachment = self._line(report).evidence_ids.attachment_id
        employee = self.env['hr.employee'].search([('user_id', '=', self.owner.id)])
        employee.active = False
        with self.assertRaises(AccessError):
            attachment.read(['datas'])
        with self.assertRaises(AccessError):
            attachment.sudo()._can_return_content()
        self.assertFalse(self._as(self.env['ps.te.expense.report'], self.owner).search([('id', '=', report.id)]))

    def test_15_wrong_report_line_and_malformed_amount_do_not_mutate(self):
        first = self._report()
        second = self._report()
        line = self._line(second)
        with self.assertRaises(AccessError):
            first.action_edit_line(line.id, 'Wrong report', 100, fields.Date.today(), first.revision)
        for amount in (0, -1, 1.5, float('nan'), True):
            with self.assertRaises(ValidationError):
                first.action_add_line('Invalid', amount, fields.Date.today(), first.revision)
        self.assertFalse(first.line_ids)

    def test_16_competing_review_and_withdrawal_preserve_exact_basis(self):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            users = {key: env['res.users'].browse(value) for key, value in self.race_users.items()}
            trip = TestTripAdvance._new_trip(env, users)
            trip.action_no_advance()
            report = env['ps.te.expense.report'].with_user(users['owner']).with_context(allowed_company_ids=[self.race_company]).create({'trip_id': trip.id})
            line_id = report.action_add_line('Synthetic race expense', 100000, fields.Date.today(), report.revision)
            revision = report.revision
            report.action_submit(revision)
            report_id = report.id
            cr.commit()
        context = {'allowed_company_ids': [self.race_company]}
        with self.registry.cursor() as finance_cr, self.registry.cursor() as owner_cr:
            finance = api.Environment(finance_cr, self.race_users['finance'], context)['ps.te.expense.report'].browse(report_id)
            owner = api.Environment(owner_cr, self.race_users['owner'], context)['ps.te.expense.report'].browse(report_id)
            finance._lock()
            with self.assertRaises(LockError):
                owner.action_revise('Concurrent withdrawal', revision)
            owner_cr.rollback()
            finance.action_review_line(line_id, 'refused', 'Missing proof refused', 0, revision)
            finance_cr.commit()
        with self.registry.cursor() as cr:
            owner = api.Environment(cr, self.race_users['owner'], context)['ps.te.expense.report'].browse(report_id)
            self.assertTrue(owner.accepted_basis_ready)
            owner.action_revise('New evidence', revision)
            self.assertFalse(owner.accepted_basis_ready)

    def test_17_active_proof_limit_and_foreign_company_session(self):
        report = self._report()
        line = self._line(report, proof=False)
        for index in range(5):
            report.action_upload_evidence(line.id, 'proof%s.pdf' % index, base64.b64encode(self._pdf()), report.revision)
        revision = report.revision
        with self.assertRaises(ValidationError):
            report.action_upload_evidence(line.id, 'sixth.pdf', base64.b64encode(self._pdf()), revision)
        self.assertEqual(report.revision, revision)
        self.assertEqual(len(line.evidence_ids), 5)
        foreign = self.env['res.company'].create({'name': 'Synthetic foreign evidence company'})
        with self.assertRaises(AccessError):
            line.evidence_ids[:1].attachment_id.with_context(allowed_company_ids=[foreign.id]).read(['datas'])

    def test_18_basis_readiness_tracks_policy_and_authority_without_erasing_history(self):
        report = self._report()
        line = self._line(report)
        report.action_submit(report.revision)
        self._review(report, line)
        self.assertTrue(report.accepted_basis_ready)
        policy = self.company.ps_te_expense_policy_reference
        self.company.ps_te_expense_policy_reference = 'SYNTHETIC-NEW-POLICY'
        self.assertFalse(report.accepted_basis_ready)
        self.assertEqual(report.accepted_total, 80000)
        self.company.ps_te_expense_policy_reference = policy
        self.assertTrue(report.accepted_basis_ready)
        self.finance.write({'group_ids': [Command.unlink(self.env.ref('ps_expenses.group_ps_te_finance').id)]})
        self.assertFalse(report.accepted_basis_ready)
        self.assertEqual(line.decision, 'accepted')

    def test_19_unrelated_attachments_keep_native_behavior_and_public_proof_is_denied(self):
        model = self._as(self.env['ir.attachment'], self.owner)
        ordinary = model.create({'name': 'synthetic-unrelated.txt', 'raw': b'Synthetic unrelated file'})
        ordinary.write({'name': 'synthetic-renamed.txt'})
        self.assertEqual(ordinary.name, 'synthetic-renamed.txt')
        self.assertTrue(ordinary.generate_access_token()[0])
        ordinary.unlink()
        self.assertFalse(ordinary.exists())
        report = self._report()
        attachment = self._line(report).evidence_ids.attachment_id
        public = self.env.ref('base.public_user')
        with self.assertRaises(AccessError):
            self._as(attachment, public)._can_return_content(access_token='forged')
