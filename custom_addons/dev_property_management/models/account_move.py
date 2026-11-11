# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import fields, models,api,_

class account_move(models.Model):
    _inherit = 'account.move'
    
    agent_commission_id = fields.Many2one('agent.commission', string='Agent Commission')
    
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
