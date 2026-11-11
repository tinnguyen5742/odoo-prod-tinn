# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##########################################################################

from odoo import fields, models, api, _
from datetime import date
from dateutil.relativedelta import relativedelta
import base64

class AgreementWindow(models.TransientModel):
    _name = 'agreement.window'
    _description = 'Agreement Window'

    def add_documents(self):
        pass

    def generate_rent_agreement(self):
        vals = {'partner_id': self.partner_id and self.partner_id.id or False,
                'property_id': self.property_id and self.property_id.id or False,
                'owner_partner_id': self.owner_partner_id and self.owner_partner_id.id or False,
                'agreement_date': self.agreement_date,
                'rent_amount': self.rent_amount,
                'duration': self.duration,
                'interval_type': self.interval_type,
                'description': self.description,
                'booking_id': self.booking_id and self.booking_id.id or False,
                'tenancy_id': self.tenancy_id and self.tenancy_id.id or False,
                'agreement_template_id': self.agreement_template_id and self.agreement_template_id.id or False,
                'type': self.type
                }
        print('===========vals===================',vals)
        agreement_id = self.env['property.agreement'].sudo().create(vals)
        if self.type == 'rent':
            action = self.env.ref('dev_property_management.action_property_agreement_rent').sudo().read()[0]
        else:
            action = self.env.ref('dev_property_management.action_property_agreement_sell').sudo().read()[0]
        action['views'] = [(self.env.ref('dev_property_management.form_property_agreement').id, 'form')]
        action.update({'res_id': agreement_id.id})
        if agreement_id:
            if self.attachment_ids:
                for line_id in self.attachment_ids:
                    attachment_vals = {
                        'name': line_id.name,
                        'res_model': agreement_id._name,
                        'res_id': agreement_id.id,
                        'datas': base64.b64encode(line_id.datas),
                        'type': 'binary'
                    }
                    self.env['ir.attachment'].sudo().create(attachment_vals)
        return action

    @api.depends('duration', 'interval_type', 'agreement_date')
    def _compute_expiry_date(self):
        for agreement in self:
            expiry_date = False
            if agreement.interval_type == 'months':
                expiry_date = agreement.agreement_date + relativedelta(months=+agreement.duration)
            else:
                expiry_date = agreement.agreement_date + relativedelta(years=+agreement.duration)
            agreement.expiry_date = expiry_date

    @api.onchange('agreement_template_id')
    def onchange_agreement_template_id(self):
        self.description = self.agreement_template_id and self.agreement_template_id.description or ''

    @api.onchange('tenancy_id')
    def onchange_tenancy_id(self):
        if self.tenancy_id:
            self.partner_id = self.tenancy_id and self.tenancy_id.partner_id and self.tenancy_id.partner_id.id or False
            self.property_id = self.tenancy_id and self.tenancy_id.property_id and self.tenancy_id.property_id.id or False
            self.owner_partner_id = self.tenancy_id  and self.tenancy_id.owner_partner_id and self.tenancy_id.owner_partner_id.id or False
            self.rent_amount = self.tenancy_id and self.tenancy_id.rent_amount or ''

    @api.onchange('booking_id')
    def onchange_booking_id(self):
        if self.booking_id:
            self.partner_id = self.booking_id and self.booking_id.partner_id and self.booking_id.partner_id.id or False
            self.property_id = self.booking_id and self.booking_id.property_id and self.booking_id.property_id.id or False
            self.owner_partner_id = self.booking_id  and self.booking_id.partner_id and self.booking_id.partner_id.id or False

    booking_id = fields.Many2one('property.booking', string='Booking')
    tenancy_id = fields.Many2one('property.tenancy', string='Tenancy')
    agreement_template_id = fields.Many2one('agreement.template', string='Agreement Template')
    partner_id = fields.Many2one('res.partner', string='Tenant')
    property_id = fields.Many2one('property.property')
    agreement_date = fields.Date(string='Agreement Date', default=date.today(), required=True)
    expiry_date = fields.Date(string='Expiry Date', compute='_compute_expiry_date')
    owner_partner_id = fields.Many2one('res.partner', string='Property Owner', tracking=1)
    rent_amount = fields.Float(string='Monthly Rent', tracking=1)
    duration = fields.Integer(string='Duration', default=11, tracking=1)
    interval_type = fields.Selection([('months', 'Months'),
                                      ('years', 'Years')], string='Interval Type',
                                     default='months', required=True, tracking=1)
    type = fields.Selection(string='Type', selection=[('rent', 'Rent'),
                                                      ('sell', 'Sell')])
    description = fields.Text(string='Description')
    attachment_ids = fields.Many2many('ir.attachment', string='Documents')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: