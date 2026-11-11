# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import api , fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    tenancy_id = fields.Many2one('property.tenancy', string='Tenancy', copy=False) # link
    rent_schedule_id = fields.Many2one('rent.schedule', string='Rent Schedule', copy=False)
    property_id = fields.Many2one('property.property', string='Property', copy=False) # link
    is_maintenance_invoice = fields.Boolean(string='Is Maintenance Invoice?', copy=False)
    maintenance_id = fields.Many2one('maintenance.request', string='Maintenance', copy=False)
    
#    @api.model
#    def create(self, vals):
#        move = super().create(vals)
#        rent_schedule_id = self.env.context.get('default_rent_schedule_id')
#        if rent_schedule_id:
#            self.env['rent.schedule'].browse(rent_schedule_id).write({
#                'invoice_id': move.id
#            })
#        return move

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
