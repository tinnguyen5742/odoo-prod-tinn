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


class AreaMeasurement(models.Model):
    _name = 'property.area.measurement'
    _description = 'Area Measurement'

    def _compute_carpet_area(self):
        for rec in self:
            area = rec.length * rec.width
            rec.carpet_area = area

    property_id = fields.Many2one('property.property', string='Property', ondelete='cascade', copy=False) # link
    name = fields.Char(string='Section', required=True)
    length = fields.Float(string='Length(sq.ft.)')
    width = fields.Float(string='Width(sq.ft.)')
    height = fields.Float(string='Height(sq.ft.)')
    carpet_area = fields.Float(string='Carpet Area(sq.ft.)', compute='_compute_carpet_area')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
