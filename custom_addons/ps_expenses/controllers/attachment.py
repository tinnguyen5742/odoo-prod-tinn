"""PDF preview được phép đọc; không sửa cache trên chứng từ PS bất biến."""
from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError
from odoo.addons.mail.controllers.attachment import AttachmentController


class PsProofAttachmentController(AttachmentController):
    def _ps_proof(self, attachment_id):
        attachment = request.env['ir.attachment'].browse(int(attachment_id)).exists()
        if attachment and attachment._protected_expense_proofs():
            try:
                attachment._check_expense_content_user()
            except AccessError:
                raise NotFound() from None
            return attachment
        return request.env['ir.attachment']

    @http.route()
    def mail_attachement_update_thumbnail(self, attachment_id, thumbnail=None, access_token=None):
        if self._ps_proof(attachment_id):
            # Native client generates a preview, then tries to persist its
            # thumbnail. Authorized read is not write authority. Ignore the
            # supplied derived cache, including forged content/context/tokens;
            # never call write/sudo-write or send a fake cached-thumbnail flag.
            return None
        return super().mail_attachement_update_thumbnail(attachment_id, thumbnail, access_token)

    @http.route()
    def mail_attachment_pdf_first_page(self, attachment_id, access_token=None):
        self._ps_proof(attachment_id)
        return super().mail_attachment_pdf_first_page(attachment_id, access_token)
