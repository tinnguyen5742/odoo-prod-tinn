# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##########################################################################

from odoo import fields, models, api
from datetime import date


class DueRentReport(models.TransientModel):
    _name = 'due.rent.popup'
    _description = 'Due Rent Report'

    def print_pdf(self):
        return self.env.ref('dev_property_management.menu_due_rent_pdf_template').report_action(self)

    start_date = fields.Date(string='Start Date', required=True, default=date.today())
    end_date = fields.Date(string='End Date', required=True, default=date.today())
    property_type = fields.Selection(string='Property Type',
                                     selection=[('residential', 'Residential'),
                                                ('commercial', 'Commercial'),
                                                ('industrial', 'Industrial'),
                                                ('land', 'Land')], default='residential', required=True)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: