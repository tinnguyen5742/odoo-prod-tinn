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


class RentAgreementTemplate(models.Model):
    _name = 'agreement.template'
    _description = 'Agreement Template'

    name = fields.Char(string='Template Name', required=True)
    description = fields.Html(string='Description')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: