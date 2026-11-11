# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##########################################################################

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import base64

class AddAgreementDocuments(models.TransientModel):
    _name = 'add.agreement.documents'
    _description = 'Add Agreement Documents'

    def add_documents(self):
        if not self.attachment_ids:
            raise ValidationError(_('''Please upload documents !'''))
        for line_id in self.attachment_ids:
            attachment_vals = {
                'name': line_id.name,
                'res_model': self.agreement_id._name,
                'res_id': self.agreement_id.id,
                'datas': base64.b64encode(line_id.datas),
            }
            self.env['ir.attachment'].sudo().create(attachment_vals)

    attachment_ids = fields.Many2many('ir.attachment',  string='Documents')
    agreement_id = fields.Many2one('property.agreement', string='Agreement')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: