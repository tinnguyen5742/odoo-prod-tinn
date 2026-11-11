# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import fields, models


class RentType(models.Model):
    _name = 'rent.type'
    _description = 'Rent Type'

    def _compute_name(self):
        for rent_type in self:
            name = rent_type.duration + ' ' + dict(rent_type._fields['interval'].selection).get(rent_type.interval)
            rent_type.name = name

    name = fields.Char(string='Name', compute='_compute_name')
    duration = fields.Selection(string='Duration', selection=[('1', '1'),
                                                              ('2', '2'),
                                                              ('3', '3'),
                                                              ('4', '4'),
                                                              ('5', '5'),
                                                              ('6', '6'),
                                                              ('7', '7'),
                                                              ('8', '8'),
                                                              ('9', '9'),
                                                              ('10', '10'),
                                                              ('11', '11'),
                                                              ('12', '12'),],
                                default='1', required=True, tracking=1)
    interval = fields.Selection(string='Interval', selection=[('monthly', 'Monthly'),
                                                              ('yearly', 'Yearly')],
                                default='monthly', required=True)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: