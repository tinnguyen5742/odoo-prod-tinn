# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import api, models


class DueRentReport(models.AbstractModel):
    _name = 'report.dev_property_management.due_rent_pdf_template'

    def get_rent_details(self, wizard_id):
        rent_details = {}
        rent_ids = self.env['rent.schedule'].search([('date', '>=', wizard_id.start_date),
                                                     ('date', '<=', wizard_id.end_date),
                                                     ('property_id.property_type', '=', wizard_id.property_type)])

        if rent_ids:
            for rent_id in rent_ids:
                if rent_id.state == 'unpaid':
                    if rent_id.partner_id.name not in rent_details:
                        rent_details.update({rent_id.partner_id.name:[rent_id]})
                        
                    else:
                        rent_details[rent_id.partner_id.name].append(rent_id)
        return rent_details

    def _get_report_values(self, docids, data=None):
        docs = self.env['due.rent.popup'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'due.rent.popup',
            'get_rent_details': self.get_rent_details,
            'docs': docs,
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
