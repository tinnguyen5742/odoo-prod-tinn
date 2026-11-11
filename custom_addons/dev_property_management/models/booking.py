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


class Booking(models.Model):
    _name = 'property.booking'
    _inherit = ['mail.thread']
    _description = 'Property Booking'
    _order = 'id desc'

    @api.model
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].next_by_code('property.booking') or '/'
        return super(Booking, self).create(vals_list)

    def confirm_booking(self):
        self.property_id.booking_id = self.id 
        self.state = 'confirmed'
        self.property_id.state = 'sold'
        self.confirmation_date = date.today()
        # if not self.partner_id.is_owner:
        #     self.partner_id.is_owner = True
        # self.property_id.owner_partner_id = self.partner_id.id

    
    def create_commission(self):
    # Prepare the action to open the booking form view
    
        return {
            'name': 'Create Commission',
            'type': 'ir.actions.act_window',
            'res_model': 'agent.commission',  # The model associated with the booking
            'view_mode': 'form',
            'view_id': self.env.ref('dev_property_management.view_dev_agent_commission_form').id,  # Form view ID
            'target': 'new',  # Open in a modal dialog
            'context': {
                'default_sell_id': self.id,
                'default_agent_partner_id':self.sell_agent_id.id or ''
            },
        }

    count_commission_agent = fields.Integer('View Agent Commision', compute='_count_commission_agent')

    def _count_commission_agent(self):
        counter=0 
        for rec in self:
            commission_ids = self.env['agent.commission'].search([('sell_id','=',self.id),('agent_partner_id','=',self.sell_agent_id.id)])
            
            commission = commission_ids.ids
            
            counter = len(commission)
        rec.count_commission_agent = counter        
            
    def action_view_commission_agent(self):
        commission_ids = self.env['agent.commission'].search([('sell_id','=',self.id),('agent_partner_id','=',self.sell_agent_id.id)])
        
        if commission_ids:
            action = self.env.ref('dev_property_management.action_dev_agent_commission').read()[0]
            action['domain'] = [('id', 'in', commission_ids.ids)]
            return action
        else:
            action = {'type': 'ir.actions.act_window_close'}


    @api.onchange('booking_purpose')
    def onchange_booking_purpose(self):
        domain = {}
        domain['property_id'] = [('name', '=', 'odoo,dev,getodoo,property,etc#124')]
        if self.booking_purpose == 'rent':
            domain['property_id'] = [('state', '=', 'draft'), ('property_purpose', '=', 'rent')]
        else:
            domain['property_id'] = [('state', '=', 'draft'), ('property_purpose', '=', 'sell')]
        return {'domain': domain}

    def view_agreements(self):
        agreements_ids = self.agreement_ids
        action = self.env.ref('dev_property_management.action_property_agreement_sell').sudo().read()[0]
        if len(agreements_ids) > 1:
            action['domain'] = [('id', 'in', agreements_ids.ids)]
        elif len(agreements_ids) == 1:
            action['views'] = [(self.env.ref('dev_property_management.form_property_agreement').id, 'form')]
            action['res_id'] = agreements_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def _compute_agreement_count(self):
        for agreement in self:
            counter = len(agreement.agreement_ids)
            agreement.agreement_count = counter

    def set_to_new(self):
        self.state = 'draft'

    def cancel_booking(self):
        self.state = 'cancelled'
        self.property_id.booking_id = False
        self.property_id.owner_partner_id = self.owner_partner_id and self.owner_partner_id.id or False

    @api.onchange('property_id')
    def onchange_property_id(self):
        self.owner_partner_id = self.property_id and self.property_id.owner_partner_id and self.property_id.owner_partner_id.id or False
        self.parent_id = self.property_id and self.property_id.parent_id and self.property_id.parent_id.id or False

    
    def generate_agent_commission(self):
        if not self.agent_partner_id:
            raise ValidationError(_('''Please select Agent !'''))
        if not self.commission_type:
            raise ValidationError(_('''Please select Commission Type !'''))
        if self.commission_amount <= 0:
            raise ValidationError(_('''Commission Amount must be positive !'''))
        amount = self.commission_amount
        if self.commission_type == 'percentage':
            amount = self.price_amount * self.commission_amount / 100
        action = self.env.ref('account.action_account_payments_payable').sudo().read()[0]
        action['views'] = [(self.env.ref('account.view_account_payment_form').id, 'form')]
        context_dict = ast.literal_eval(action['context'])
        context_dict.update({'default_amount': amount,
                             'default_partner_id': self.agent_partner_id.id,
                             'default_booking_id': self.id})
        action['context'] = str(context_dict)
        return action

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError(_('''Only 'New' Booking can be deleted !'''))
        return super(Booking, self).unlink()

    name = fields.Char(string='Number')
    property_type = fields.Selection(string='Property Type',
                                     selection=[('residential', 'Residential'),
                                                ('commercial', 'Commercial'),
                                                ('industrial', 'Industrial'),
                                                ('land', 'Land')], default='residential',
                                     required=True, tracking=1)
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=1, copy=False,
                                 default=lambda self: self.env.user and self.env.user.partner_id or False, required=1)
    property_id = fields.Many2one('property.property', string='Property', tracking=1, required=1, ondelete='cascade') # link
    booking_date = fields.Date(string='Booking Date', copy=False, default=date.today(), tracking=1)
    confirmation_date = fields.Date(string='Confirmation Date', copy=False, tracking=1)
    booking_purpose = fields.Selection(string='Purpose', selection=[('rent', 'Rent'), ('buy', 'Sell')],
                                       default='rent', tracking=1, required=True)
    owner_partner_id = fields.Many2one('res.partner', string='Owner')
    state = fields.Selection(string='Status', selection=[('draft', 'New'),
                                                         ('confirmed', 'Confirmed'),
                                                         ('cancelled', 'Cancelled'),
                                                         ],
                             default='draft', copy=False, tracking=1)
    price_amount = fields.Float(string='Selling Price', related='property_id.price_amount')
    rent_amount = fields.Float(string='Monthly Rent',  related='property_id.rent_amount')
    ask_price_amount = fields.Float(string='Ask Price', copy=False, tracking=1)
    agreement_ids = fields.One2many('property.agreement', 'booking_id', string='Agreements')
    agreement_count = fields.Integer(string='Agreement Counter', compute='_compute_agreement_count')
    description = fields.Html(string='Description')
    agent_partner_id = fields.Many2one('res.partner', string='Agent', tracking=1, domain=[('is_agent', '=', True)])
    commission_amount = fields.Float(string='Commission')
    commission_type = fields.Selection(string='Commission Type',
                                       selection=[('fix', 'Fixed Amount'),
                                                  ('percentage', 'Percentage of Selling Price'),],
                                       default='fix', tracking=1)
    commission_payment_id = fields.Many2one('account.payment', string='Payment', copy=False)
    parent_id=fields.Integer('Parent Porperty')
    parent_ids=fields.Many2one('property.property','Parent Porperty', tracking=1, ondelete='cascade')
    sell_agent_id=fields.Many2one('res.partner',string="Agent",domain=[('is_agent','=',True)])
    lead_id = fields.Many2one('crm.lead', string='Lead' )

    @api.onchange('sell_agent_id')
    def onchange_loan_agent_id(self):
        if self.sell_agent_id.blacklisted == True:
             warning_mess1 = {
                            'title': _("Warning") ,
                            'message': _("This Agent is blacklisted For This Reason - %s !!") % (self.sell_agent_id.blacklisted_reason)
                            }
             return {'warning': warning_mess1}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
