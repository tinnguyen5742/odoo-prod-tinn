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


class Areamange(models.Model):
    _name = 'property.document'
    _description = 'Property Document'

    name = fields.Char(string='Name')
    document=fields.Binary(string='Document')  
    property_id=fields.Many2one('property.property',string='Document')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
