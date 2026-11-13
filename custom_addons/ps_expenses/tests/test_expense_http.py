import base64
import json

from odoo import fields
from odoo.tests.common import HttpCase, tagged

from .test_advance import TestTripAdvance
from .test_expenses import TestExpenseEvidence


@tagged('post_install', '-at_install')
class TestExpenseHttpDownload(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company_id, users = TestExpenseEvidence._fixture(cls.env)
        cls.company_id = company_id
        cls.owner = cls.env['res.users'].browse(users['owner'])
        cls.other = cls.env['res.users'].browse(users['other'])
        cls.finance = cls.env['res.users'].browse(users['finance'])
        cls.cash = cls.env['res.users'].browse(users['cash'])
        cls.manager = cls.env['res.users'].browse(users['manager'])
        # This password exists only on invented users in the isolated TEST DB.
        for user in (cls.owner, cls.other, cls.finance, cls.cash, cls.manager):
            user.password = 'synthetic-http-only'
        user_records = {role: cls.env['res.users'].browse(user_id) for role, user_id in users.items()}
        trip = TestTripAdvance._new_trip(cls.env, user_records)
        trip.action_no_advance()
        cls.report = cls.env['ps.te.expense.report'].with_user(cls.owner).with_context(allowed_company_ids=[company_id]).create({'trip_id': trip.id})
        line_id = cls.report.action_add_line('Synthetic HTTP evidence', 100000, fields.Date.today(), cls.report.revision)
        cls.raw = TestExpenseEvidence._pdf()
        proof_id = cls.report.action_upload_evidence(line_id, 'synthetic-http.pdf', base64.b64encode(cls.raw), cls.report.revision)
        cls.attachment_id = cls.env['ps.te.expense.evidence'].browse(proof_id).attachment_id.id

    def test_http_owner_and_finance_download_without_public_token(self):
        for user in (self.owner, self.finance):
            self.authenticate(user.login, 'synthetic-http-only')
            response = self.url_open('/web/content/%s?download=true&mimetype=text/html' % self.attachment_id)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, self.raw)
            self.assertTrue(response.headers['Content-Type'].startswith('application/octet-stream'))

    def test_http_other_user_and_forged_token_cannot_download(self):
        self.authenticate(self.other.login, 'synthetic-http-only')
        for suffix in ('?download=true', '?download=true&access_token=forged'):
            response = self.url_open('/web/content/%s%s' % (self.attachment_id, suffix))
            self.assertIn(response.status_code, (403, 404))
            self.assertNotEqual(response.content, self.raw)

    def _native_rpc(self, method, args, extra_context=None):
        payload = {'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {
            'model': 'hr.expense', 'method': method, 'args': args,
            'kwargs': {'context': {'allowed_company_ids': [self.report.company_id.id], **(extra_context or {})}}}}
        response = self.url_open('/web/dataset/call_kw/hr.expense/' + method,
            data=json.dumps(payload), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_native_jsonrpc_counterparts_and_no_context_approval_bypass(self):
        native_id = self.report.line_ids.native_expense_id.id
        for user in (self.owner, self.finance):
            self.authenticate(user.login, 'synthetic-http-only')
            data = self._native_rpc('read', [[native_id], ['total_amount_currency', 'ps_report_id']])
            self.assertEqual(data['result'][0]['total_amount_currency'], 100000)
            denied = self._native_rpc('write', [[native_id], {'approval_state': 'approved', 'ps_accepted_amount': 100000}],
                {'_ps_native': True, 'default_ps_decision': 'accepted'})
            self.assertIn('error', denied)
        self.authenticate(self.other.login, 'synthetic-http-only')
        self.assertIn('error', self._native_rpc('read', [[native_id], ['total_amount_currency']]))

    def test_native_jsonrpc_submission_requires_observed_ps_revision(self):
        native_id = self.report.line_ids.native_expense_id.id
        self.authenticate(self.owner.login, 'synthetic-http-only')
        result = self._native_rpc('action_submit', [[native_id]])
        self.assertIn('error', result)
        payload = {'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {
            'model': 'ps.te.expense.report', 'method': 'action_submit', 'args': [[self.report.id], self.report.revision],
            'kwargs': {'context': {'allowed_company_ids': [self.report.company_id.id]}}}}
        submitted = self.url_open('/web/dataset/call_kw/ps.te.expense.report/action_submit',
            data=json.dumps(payload), headers={'Content-Type': 'application/json'}).json()
        self.assertNotIn('error', submitted)
        data = self._native_rpc('read', [[native_id], ['state', 'ps_decision']])['result'][0]
        self.assertEqual((data['state'], data['ps_decision']), ('submitted', 'pending'))

    def test_r1_f02_public_onchange_and_default_get_authorization(self):
        spec = {key: {} for key in ('ps_revision', 'ps_basis_status', 'ps_trip_id', 'ps_owner_id',
            'ps_finance_id', 'ps_finance_valid')}
        native_id = self.report.line_ids.native_expense_id.id
        for actor in (self.other, self.cash):
            self.authenticate(actor.login, 'synthetic-http-only')
            self.assertIn('error', self._native_rpc('read', [[native_id], ['name']]))
            leaked = self._native_rpc('onchange', [[], {'ps_report_id': self.report.id}, ['ps_report_id'], spec])
            self.assertIn('error', leaked)
            self.assertEqual(leaked['error']['data']['name'], 'odoo.exceptions.AccessError')
            defaults = self._native_rpc('default_get', [list(spec)], {'default_ps_report_id': self.report.id})
            self.assertIn('error', defaults)
            # Persisted ID and context-default routes cannot evade the value guard.
            self.assertIn('error', self._native_rpc('onchange', [[native_id], {}, [], spec]))
            self.assertIn('error', self._native_rpc('onchange', [[], {}, [], spec],
                {'default_ps_report_id': self.report.id}))
        for actor in (self.owner, self.finance):
            self.authenticate(actor.login, 'synthetic-http-only')
            data = self._native_rpc('onchange', [[], {'ps_report_id': self.report.id}, ['ps_report_id'], spec])
            self.assertNotIn('error', data, data)
            self.assertEqual(data['result']['value']['ps_revision'], self.report.revision)

    def test_r1_f03_public_native_create_sanitizes_only_protected_ps_defaults(self):
        self.authenticate(self.owner.login, 'synthetic-http-only')
        defaults = {'default_name': 'Synthetic ordinary HTTP defaults',
            'default_product_id': self.env.ref('ps_expenses.product_ps_native_expense').id,
            'default_total_amount_currency': 100000,
            'default_ps_decision': 'accepted', 'default_ps_accepted_amount': 77777,
            'default_ps_reviewed_revision': 99, 'default_ps_reviewed_by_id': self.finance.id}
        result = self._native_rpc('create', [{}], defaults)
        self.assertNotIn('error', result, result)
        record_id = result['result']
        read = self._native_rpc('read', [[record_id], ['name', 'total_amount_currency', 'ps_report_id',
            'ps_decision', 'ps_accepted_amount', 'ps_reviewed_by_id', 'ps_reviewed_revision']])['result'][0]
        self.assertEqual((read['name'], read['total_amount_currency']), ('Synthetic ordinary HTTP defaults', 100000))
        self.assertFalse(read['ps_report_id'])
        self.assertEqual(read['ps_decision'], 'pending')
        self.assertEqual(read['ps_accepted_amount'], 0)
        self.assertFalse(read['ps_reviewed_by_id'])
        self.assertEqual(read['ps_reviewed_revision'], 0)

    def _thumbnail_rpc(self, attachment_id, thumbnail='Zm9yZ2VkLXByZXZpZXc=', extra=None):
        payload = {'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {
            'attachment_id': attachment_id, 'thumbnail': thumbnail, **(extra or {})}}
        return self.url_open('/mail/attachment/update_thumbnail', data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}).json()

    def test_r6_f03_protected_thumbnail_noop_keeps_original_and_denies_raw_writes(self):
        attachment = self.env['ir.attachment'].browse(self.attachment_id)
        before = attachment.read(['name', 'checksum', 'res_model', 'res_id', 'public', 'access_token', 'thumbnail'])
        for user in (self.owner, self.finance):
            self.authenticate(user.login, 'synthetic-http-only')
            for thumbnail in ('Zm9yZ2Vk', None):
                result = self._thumbnail_rpc(self.attachment_id, thumbnail)
                self.assertNotIn('error', result, result)
            payload = {'jsonrpc': '2.0', 'method': 'call', 'id': 2, 'params': {
                'model': 'ir.attachment', 'method': 'write', 'args': [[self.attachment_id], {'thumbnail': 'Zm9yZ2Vk'}],
                'kwargs': {'context': {'allowed_company_ids': [self.company_id], 'from_thumbnail': True,
                    'ps_thumbnail': True, '_ps_proof': True}}}}
            result = self.url_open('/web/dataset/call_kw/ir.attachment/write', data=json.dumps(payload),
                headers={'Content-Type': 'application/json'}).json()
            self.assertIn('error', result)
        attachment.invalidate_recordset()
        self.assertEqual(attachment.read(list(before[0].keys() - {'id'})), before)
        self.assertEqual(attachment.raw, self.raw)

    def test_r6_f03_thumbnail_wrong_role_and_forged_token_denied(self):
        for actor in (self.other, self.cash, self.manager):
            self.authenticate(actor.login, 'synthetic-http-only')
            result = self._thumbnail_rpc(self.attachment_id, extra={'access_token': 'forged'})
            self.assertIn('error', result)
            response = self.url_open('/mail/attachment/pdf_first_page/%s?access_token=forged' % self.attachment_id)
            self.assertIn(response.status_code, (403, 404))
        self.assertFalse(self.env['ir.attachment'].browse(self.attachment_id).thumbnail)

    def test_r6_f03_ordinary_native_attachment_thumbnail_behavior_preserved(self):
        from io import BytesIO
        from PIL import Image
        preview = BytesIO()
        Image.new('RGB', (8, 8), 'white').save(preview, format='PNG')
        ordinary = self.env['ir.attachment'].with_user(self.owner).create({
            'name': 'ordinary-synthetic.pdf', 'raw': self.raw, 'mimetype': 'application/pdf',
            'res_model': 'res.users', 'res_id': self.owner.id})
        self.authenticate(self.owner.login, 'synthetic-http-only')
        result = self._thumbnail_rpc(ordinary.id, base64.b64encode(preview.getvalue()).decode())
        self.assertNotIn('error', result, result)
        ordinary.invalidate_recordset()
        self.assertTrue(ordinary.thumbnail)
        self.assertFalse(ordinary.ps_te_evidence_id)

    def test_r6_f03_valid_pdf_first_page_authorized_hash_and_no_thumbnail_mutation(self):
        stream = b'BT /F1 12 Tf 20 700 Td (SYNTHETIC PS PDF NO REAL TRANSACTION) Tj ET'
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
            b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
            b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream']
        raw = b'%PDF-1.4\n'
        offsets = []
        for number, body in enumerate(objects, 1):
            offsets.append(len(raw))
            raw += b'%d 0 obj\n' % number + body + b'\nendobj\n'
        xref = len(raw)
        raw += b'xref\n0 6\n0000000000 65535 f \n' + b''.join(b'%010d 00000 n \n' % pos for pos in offsets)
        raw += b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % xref
        line = self.report.line_ids
        evidence_id = self.report.action_upload_evidence(line.id, 'valid-synthetic.pdf', base64.b64encode(raw), self.report.revision)
        attachment = self.env['ps.te.expense.evidence'].browse(evidence_id).attachment_id
        for actor in (self.owner, self.finance):
            self.authenticate(actor.login, 'synthetic-http-only')
            preview = self.url_open('/mail/attachment/pdf_first_page/%s' % attachment.id)
            self.assertEqual(preview.status_code, 200)
            self.assertTrue(preview.content.startswith(b'%PDF-'))
            self.assertNotIn('error', self._thumbnail_rpc(attachment.id))
            download = self.url_open('/web/content/%s?download=true' % attachment.id)
            self.assertEqual(download.content, raw)
        attachment.invalidate_recordset()
        self.assertFalse(attachment.thumbnail)
        self.assertEqual(attachment.raw, raw)
