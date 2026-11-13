import hashlib

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


PROTECTED_MODELS = frozenset({
    'ps.te.expense.report', 'ps.te.expense.line', 'ps.te.expense.evidence', 'ps.te.expense.event',
    'ps.te.expense.proof.link', 'ps.te.adjustment',
})


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    ps_te_evidence_id = fields.Many2one('ps.te.expense.evidence', readonly=True, ondelete='restrict', index=True)

    def _protected_expense_proofs(self):
        return self.sudo().filtered(lambda attachment: attachment.ps_te_evidence_id or attachment.res_model in PROTECTED_MODELS)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            target_model = vals.get('res_model', self.env.context.get('default_res_model'))
            target_id = vals.get('res_id', self.env.context.get('default_res_id'))
            native_ps = (target_model == 'hr.expense' and target_id
                and self.env['hr.expense'].sudo().browse(target_id).exists().ps_report_id)
            if native_ps or target_model in PROTECTED_MODELS or 'ps_te_evidence_id' in vals or self.env.context.get('default_ps_te_evidence_id'):
                raise AccessError(_('Use the expense proof upload action.'))
        return super().create(vals_list)

    @api.model
    def _create_expense_proof(self, evidence, raw):
        attachment = super(IrAttachment, self.sudo()).create({
            'name': evidence.filename, 'raw': raw, 'mimetype': evidence.mimetype,
            'type': 'binary', 'res_model': 'hr.expense', 'res_id': evidence.line_id.native_expense_id.id,
            'company_id': evidence.company_id.id, 'ps_te_evidence_id': evidence.id,
            'public': False, 'access_token': False,
        })
        if hashlib.sha256(attachment.raw).hexdigest() != evidence.sha256:
            raise ValidationError(_('The server changed this file during processing; upload an unchanged supported proof.'))
        evidence.line_id.native_expense_id._ps_main_proof(attachment)
        return attachment

    def write(self, vals):
        if self._protected_expense_proofs() or 'ps_te_evidence_id' in vals or vals.get('res_model') in PROTECTED_MODELS:
            raise AccessError(_('Protected expense proofs cannot be changed, shared or reparented.'))
        for attachment in self.sudo():
            target_model = vals.get('res_model', attachment.res_model)
            target_id = vals.get('res_id', attachment.res_id)
            if (target_model == 'hr.expense' and target_id
                    and self.env['hr.expense'].sudo().browse(target_id).exists().ps_report_id):
                raise AccessError(_('Không chuyển tệp vào khoản chi PS ngoài thao tác chứng từ có kiểm soát.'))
        return super().write(vals)

    def unlink(self):
        if self._protected_expense_proofs():
            raise AccessError(_('Protected expense proofs must be retained.'))
        return super().unlink()

    def generate_access_token(self):
        if self._protected_expense_proofs():
            raise AccessError(_('Expense proofs require the current authorized session, not a sharing token.'))
        return super().generate_access_token()

    def _check_expense_content_user(self):
        for attachment in self._protected_expense_proofs():
            evidence = attachment.ps_te_evidence_id
            if not evidence:
                raise AccessError(_('This attachment has no controlled expense evidence binding.'))
            # Do not use the sudo record's access-rule bypass as authorization.
            evidence.with_user(self.env.uid)._assert_viewer()

    def _inaccessible_comodel_records(self, model_and_ids, operation):
        # A reused proof authorizes this exact immutable file, not its former
        # expense/other claims. Never waive the parent check for a mixed set
        # containing an ordinary/uncontrolled attachment to the same resource.
        allowed = set()
        if operation == 'read' and not self.env.su:
            native = self.sudo().filtered(lambda attachment: attachment.res_model == 'hr.expense' and attachment.res_id)
            for record_id in model_and_ids.get('hr.expense', ()):
                candidates = native.filtered(lambda attachment: attachment.res_id == record_id)
                if candidates and all(attachment.ps_te_evidence_id for attachment in candidates):
                    try:
                        candidates.with_user(self.env.uid)._check_expense_content_user()
                        allowed.add(record_id)
                    except AccessError:
                        pass
        for model_name, record_id in super()._inaccessible_comodel_records(model_and_ids, operation):
            if model_name != 'hr.expense' or record_id not in allowed:
                yield model_name, record_id

    def _can_return_content(self, field_name=None, access_token=None):
        if self._protected_expense_proofs():
            self._check_expense_content_user()
            return False
        return super()._can_return_content(field_name, access_token)

    def _to_http_stream(self):
        self._check_expense_content_user()
        stream = super()._to_http_stream()
        if self._protected_expense_proofs():
            stream.public = False
            stream.mimetype = 'application/octet-stream'
        return stream


class IrBinary(models.AbstractModel):
    _inherit = 'ir.binary'

    def _get_stream_from(self, record, field_name='raw', filename=None, filename_field='name',
                         mimetype=None, default_mimetype='application/octet-stream'):
        stream = super()._get_stream_from(record, field_name, filename, filename_field, mimetype, default_mimetype)
        if record._name == 'ir.attachment' and record._protected_expense_proofs():
            record._check_expense_content_user()
            # The binary URL's mimetype parameter cannot turn a proof into
            # same-origin executable HTML, even for an otherwise allowed user.
            stream.mimetype = 'application/octet-stream'
            stream.public = False
        return stream
