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
from datetime import date
from odoo.exceptions import ValidationError
import ast


class track_owner_payment(models.Model):
    _name = 'track.owner.payment'
    _inherit = ['mail.thread']
    _description = 'Track Owner Parent'
    _order = 'id desc'
    _rec_name='rent_number'

#    @api.model
#    def create(self, vals):
#        vals['name'] = self.env['ir.sequence'].next_by_code('property.booking') or '/'
#        return super(Booking, self).create(vals)

    def owner_paid(self):
        self.owner_paid_date = date.today()
        self.payment_state = 'paid'
        

#    


    partner_id = fields.Many2one('res.partner', string='Customer', tracking=1, copy=False)
    property_id = fields.Many2one('property.property', string='Property', tracking=1, required=1, ondelete='cascade') # link
    rent_number = fields.Char(string='Number')
    owner_partner_id = fields.Many2one('res.partner', string='Owner')
    installment_payment_date = fields.Date(string='Installment Date')
    owner_paid_date = fields.Date(string='Owner Paid Date')
    rent_amount = fields.Float(string='Monthly Rent')
    payment_state = fields.Selection([('draft','Draft'),('paid','Paid')],default='draft',string='State',tracking=1)
    
    
    
#    property_type = fields.Selection(string='Property Type',
#                                     selection=[('residential', 'Residential'),
#                                                ('commercial', 'Commercial'),
#                                                ('industrial', 'Industrial'),
#                                                ('land', 'Land')], default='residential',
#                                     required=True, tracking=1)
    
#    booking_date = fields.Date(string='Booking Date', copy=False, default=date.today(), tracking=1)
#    confirmation_date = fields.Date(string='Confirmation Date', copy=False, tracking=1)
#    booking_purpose = fields.Selection(string='Purpose', selection=[('rent', 'Rent'), ('buy', 'Sell')],
#                                       default='rent', tracking=1, required=True)
#    
#    state = fields.Selection(string='Status', selection=[('draft', 'New'),
#                                                         ('confirmed', 'Confirmed'),
#                                                         ('cancelled', 'Cancelled'),
#                                                         ],
#                             default='draft', copy=False, tracking=1)
#    price_amount = fields.Float(string='Selling Price', related='property_id.price_amount')
#    rent_amount = fields.Float(string='Monthly Rent',  related='property_id.rent_amount')
#    ask_price_amount = fields.Float(string='Ask Price', copy=False, tracking=1)
#    agreement_ids = fields.One2many('property.agreement', 'booking_id', string='Agreements')
#    agreement_count = fields.Integer(string='Agreement Counter', compute='_compute_agreement_count')
#    description = fields.Html(string='Description')
#    agent_partner_id = fields.Many2one('res.partner', string='Agent', tracking=1, domain=[('is_agent', '=', True)])
#    commission_amount = fields.Float(string='Commission')
#    commission_type = fields.Selection(string='Commission Type',
#                                       selection=[('fix', 'Fixed Amount'),
#                                                  ('percentage', 'Percentage of Selling Price'),],
#                                       default='fix', tracking=1)
#    commission_payment_id = fields.Many2one('account.payment', string='Payment', copy=False)
#    parent_id=fields.Integer('Parent Porperty')
#    parent_ids=fields.Many2one('property.property','Parent Porperty', tracking=1, required=1, ondelete='cascade')
#    sell_agent_id=fields.Many2one('res.partner',string="Agent",domain=[('is_agent','=',True)])
#    lead_id = fields.Many2one('crm.lead', string='Lead' )

#    @api.onchange('sell_agent_id')
#    def onchange_loan_agent_id(self):
#        if self.sell_agent_id.blacklisted == True:
#             warning_mess1 = {
#                            'title': _("Warning") ,
#                            'message': _("This Agent is blacklisted For This Reason - %s !!") % (self.sell_agent_id.blacklisted_reason)
#                            }
#             return {'warning': warning_mess1}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
