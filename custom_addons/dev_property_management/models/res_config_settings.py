# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import models, fields, api, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    send_aggr_exp_email = fields.Boolean(string='Agreement Expiry Reminder', related='company_id.send_aggr_exp_email', readonly=False)
    send_aggr_exp_mail_same_day = fields.Boolean(string='Agreement Expiry Reminder Same Day', related='company_id.send_aggr_exp_mail_same_day', readonly=False)
    aggr_exp_reminder_days = fields.Integer(string='Before Days', related='company_id.aggr_exp_reminder_days', readonly=False)
    
    send_rent_email = fields.Boolean(string='Rent Reminder', related='company_id.send_rent_email', readonly=False)
    send_rent_same_day = fields.Boolean(string='Rent Reminder Same Day', related='company_id.send_rent_same_day', readonly=False)
    rent_reminder_days = fields.Integer(string='Before Days', related='company_id.rent_reminder_days', readonly=False)

    maintenance_product_id = fields.Many2one('product.product', domain=[('type', '=', 'service')], related='company_id.maintenance_product_id', readonly=False)
    rent_product_id = fields.Many2one('product.product', domain=[('type', '=', 'service')], related='company_id.rent_product_id', readonly=False)

    agent_commission_product_id = fields.Many2one('product.product',related='company_id.agent_commission_product_id', readonly=False )
    
    deposit_product_id = fields.Many2one('product.product', domain=[('type', '=', 'service')], related='company_id.deposit_product_id', readonly=False)
    
    rent_invoice_auto_day = fields.Integer(string='Rent Invoice Created Before Days', related='company_id.rent_invoice_auto_day', readonly=False)
       
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
