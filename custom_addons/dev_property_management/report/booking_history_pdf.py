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


class BookingHistoryReport(models.AbstractModel):
    _name = 'report.dev_property_management.booking_history_pdf_template'

    def get_booking_details(self, wizard_id):
        booking_details = []
        booking_ids = self.env['property.booking'].search([('booking_date', '>=', wizard_id.start_date),
                                                           ('booking_date', '<=', wizard_id.end_date),
                                                           ('property_type', '=', wizard_id.property_type)])
        if booking_ids:
            booking_details = booking_ids
        return booking_details

    def _get_report_values(self, docids, data=None):
        docs = self.env['booking.history.popup'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'booking.history.popup',
            'get_booking_details': self.get_booking_details,
            'docs': docs,
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: