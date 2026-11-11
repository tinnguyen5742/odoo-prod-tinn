# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import fields, models, api, _


class Maintenanceline(models.TransientModel):
    _name = 'maintenance.invoice.line'
    _description = 'Tenancy Maintenance line'

    
    maintenance_type_id = fields.Many2one('property.maintenance.type', string='Maintenance Type', required=True)
    maintenance_amount = fields.Float(string='Maintenance Amount')
    maintenance_invoice_id = fields.Many2one('maintenance.invoice', string='Maintenance Invoice')
    check_invoice = fields.Boolean(string='Generate Invoice')
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
