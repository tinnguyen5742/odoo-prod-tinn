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


class BookingReport(models.AbstractModel):
    _name = 'report.dev_property_management.booking_pdf_template'

    def _get_report_values(self, docids, data=None):
        docs = self.env['property.booking'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'property.booking',
            'docs': docs,
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: