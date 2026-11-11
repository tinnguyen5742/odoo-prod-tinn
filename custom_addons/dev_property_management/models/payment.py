# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import fields, models, api


class Payment(models.Model):
    _inherit = 'account.payment'

    @api.model
    def create(self, vals):
        payment_id = super(Payment, self).create(vals)
        ctx = self._context
        if 'default_rent_schedule_id' in ctx:
            rent_schedule_id = self.env['rent.schedule'].browse(ctx['default_rent_schedule_id'])
            rent_schedule_id.payment_id = payment_id.id
        if 'default_deposit_tenancy_id' in ctx:
            tenancy_id = self.env['property.tenancy'].browse(ctx['default_deposit_tenancy_id'])
            tenancy_id.deposit_payment_id = payment_id.id
        if 'default_commission_tenancy_id' in ctx:
            tenancy_id = self.env['property.tenancy'].browse(ctx['default_commission_tenancy_id'])
            tenancy_id.commission_payment_id = payment_id.id
        if 'default_booking_id' in ctx:
            default_booking_id = self.env['property.booking'].browse(ctx['default_booking_id'])
            default_booking_id.commission_payment_id = payment_id.id
        return payment_id

    rent_schedule_id = fields.Many2one('rent.schedule', string='Rent Schedule', copy=False)
    deposit_tenancy_id = fields.Many2one('property.tenancy', string='Tenancy', copy=False)
    booking_id = fields.Many2one('property.booking', string='Booking', copy=False)
    commission_tenancy_id = fields.Many2one('property.tenancy', string='Commission Tenancy', copy=False)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
