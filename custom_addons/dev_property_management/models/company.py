# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import models, fields


class Company(models.Model):
    _inherit = 'res.company'

    send_aggr_exp_email = fields.Boolean(string='Agreement Expiry Reminder')
    send_aggr_exp_mail_same_day = fields.Boolean(string='Agreement Expiry Reminder Same Day')
    aggr_exp_reminder_days = fields.Integer(string='Before Days')

    send_rent_email = fields.Boolean(string='Rent Reminder')
    send_rent_same_day = fields.Boolean(string='Rent Reminder Same Day')
    rent_reminder_days = fields.Integer(string='Before Days')

    maintenance_product_id = fields.Many2one('product.product', string='Maintenance Product')
    rent_product_id = fields.Many2one('product.product', string='Rent Product')
    agent_commission_product_id = fields.Many2one('product.product', string='Agent Commission')
    deposit_product_id = fields.Many2one('product.product', string='Deposit Product')
    rent_invoice_auto_day = fields.Integer(string='Rent Invoice Created Before Days')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
