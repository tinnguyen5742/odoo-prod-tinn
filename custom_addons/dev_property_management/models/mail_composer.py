# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import models, api


class MailComposer(models.TransientModel):
    _inherit = 'mail.compose.message'

    @api.onchange('template_id')
    def _compute_lang(self):
        res = super(MailComposer, self)._compute_lang()
        rec_id = self._context.get('active_id')
        if rec_id:
            attachment_ids = self.env['ir.attachment'].search([('res_id', '=', int(rec_id)),
                                                               ('res_model', '=', 'property.agreement')])
            if attachment_ids:
                all_attachments = self.attachment_ids.ids
                for attach in attachment_ids:
                    all_attachments.append(attach.id)
                all_attachments = list(set(all_attachments))
                self.attachment_ids = all_attachments
        return res
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: