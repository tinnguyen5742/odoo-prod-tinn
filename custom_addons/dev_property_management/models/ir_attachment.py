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


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    property_id = fields.Many2one('property.property', string='Property', copy=False, ondelete='cascade') # link
    fp_property_id = fields.Many2one('property.property', string='Property', copy=False, ondelete='cascade') # link
    document_type = fields.Selection([
        ('property_image', 'Property Image'),
        ('floor_plan', 'Floor Plan Image'),
    ], string="Document Type")

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: