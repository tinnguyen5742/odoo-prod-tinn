import base64
import binascii
import hashlib

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class PsTeExpenseEvidence(models.Model):
    _name = 'ps.te.expense.evidence'
    _description = 'PS T&E Expense Evidence'
    _rec_name = 'filename'
    _fingerprint_unique = models.Constraint(
        'UNIQUE(company_id, sha256)', 'This proof is already recorded in the company; do not claim it twice.',
    )

    line_id = fields.Many2one('ps.te.expense.line', required=True, readonly=True, ondelete='restrict', index=True)
    report_id = fields.Many2one(related='line_id.report_id', store=True, readonly=True)
    company_id = fields.Many2one(related='report_id.company_id', store=True, readonly=True)
    attachment_id = fields.Many2one('ir.attachment', readonly=True, ondelete='restrict')
    filename = fields.Char(required=True, readonly=True)
    sha256 = fields.Char(required=True, readonly=True, index=True)
    mimetype = fields.Char(required=True, readonly=True)
    file_size = fields.Integer(required=True, readonly=True)
    uploaded_revision = fields.Integer(required=True, readonly=True)
    uploaded_by_id = fields.Many2one('res.users', required=True, readonly=True)
    uploaded_at = fields.Datetime(required=True, readonly=True)
    superseded = fields.Boolean(default=False, readonly=True)
    superseded_reason = fields.Text(readonly=True)
    reuse_link_ids = fields.One2many('ps.te.expense.proof.link', 'evidence_id', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Upload expense proof through the controlled evidence action.'))

    @api.model
    def _upload(self, line, filename, payload, expected_revision):
        report = line.report_id
        report._lock()
        report._assert_actor('owner')
        report._revision(expected_revision)
        report._draft()
        filename = self.env['ps.te.trip.advance']._text(filename, _('Filename'))
        if any(character in filename for character in ('/', '\\', '\r', '\n', '\0')) or len(filename) > 150:
            raise ValidationError(_('Use a filename without paths/control characters, up to 150 characters.'))
        if len(line._active_proofs()) >= 5:
            raise ValidationError(_('At most five active proofs are supported per expense line.'))
        if not isinstance(payload, (bytes, str)) or len(payload) > ((5 * 1024 * 1024 + 2) // 3) * 4:
            raise ValidationError(_('Upload a PDF/PNG/JPEG proof up to five MiB.'))
        try:
            raw = base64.b64decode(payload, validate=True)
        except (ValueError, binascii.Error, UnicodeEncodeError):
            raise ValidationError(_('Invalid binary upload.'))
        suffix = filename.rsplit('.', 1)[-1].lower()
        valid_type = (
            ('application/pdf' if suffix == 'pdf' and raw.startswith(b'%PDF-') else None)
            or ('image/png' if suffix == 'png' and raw.startswith(b'\x89PNG\r\n\x1a\n') else None)
            or ('image/jpeg' if suffix in ('jpg', 'jpeg') and raw.startswith(b'\xff\xd8\xff') else None)
        )
        if not raw or len(raw) > 5 * 1024 * 1024 or not valid_type:
            raise ValidationError(_('Upload a PDF/PNG/JPEG with a matching file header and extension.'))
        digest = hashlib.sha256(raw).hexdigest()
        if self.sudo().search_count([('company_id', '=', report.company_id.id), ('sha256', '=', digest)]):
            raise ValidationError(_('This proof is already recorded in the company.'))
        evidence = super(PsTeExpenseEvidence, self.sudo()).create({
            'line_id': line.id, 'filename': filename, 'sha256': digest,
            'mimetype': valid_type, 'file_size': len(raw), 'uploaded_revision': report.revision + 1,
            'uploaded_by_id': self.env.uid, 'uploaded_at': fields.Datetime.now(),
        })
        attachment = self.env['ir.attachment']._create_expense_proof(evidence, raw)
        super(PsTeExpenseEvidence, evidence).write({'attachment_id': attachment.id})
        # This action has observed the exact revision under the report lock.
        report._advance_revision()
        report._event('evidence_uploaded', _('Employee proof uploaded'), line)
        return evidence.id

    def write(self, vals):
        raise AccessError(_('Expense proofs cannot be overwritten or reparented.'))

    def unlink(self):
        raise AccessError(_('Expense proofs must be retained.'))

    def action_supersede(self, reason, expected_revision):
        self.ensure_one()
        self.check_access('read')
        report = self.report_id
        report._lock()
        report._assert_actor('owner')
        report._revision(expected_revision)
        report._draft()
        reason = self.env['ps.te.trip.advance']._text(reason, _('Supersession reason'))
        if self.superseded:
            raise ValidationError(_('This proof has already been superseded.'))
        super(PsTeExpenseEvidence, self.sudo()).write({'superseded': True, 'superseded_reason': reason})
        report._advance_revision()
        report._event('evidence_superseded', reason, self.line_id)
        return True

    def action_download(self):
        self.ensure_one()
        self.check_access('read')
        self._assert_viewer()
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': '/web/content/%s?download=true' % self.attachment_id.id}

    def _assert_viewer(self):
        self.ensure_one()
        try:
            self.report_id._assert_viewer()
            return
        except AccessError:
            # A controlled reference authorizes only this specific proof, not
            # access to the old report, other evidence or the old finance role.
            for link in self.sudo().reuse_link_ids.filtered(lambda item: not item.superseded):
                try:
                    link.report_id.with_user(self.env.uid)._assert_viewer()
                    return
                except AccessError:
                    continue
        raise AccessError(_('Expense access is not permitted.'))
