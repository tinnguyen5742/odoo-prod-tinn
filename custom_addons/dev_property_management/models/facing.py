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


class Facing(models.Model):
    _name = 'property.facing'
    _description = 'Facing'

    name = fields.Char(string='Name')
    code=fields.Integer(string='Code')    

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
