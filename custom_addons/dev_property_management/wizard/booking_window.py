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
from odoo.exceptions import ValidationError
from datetime import date


class BookingWindow(models.TransientModel):
    _name = 'booking.window'
    _description = 'Booking Window'

    def make_booking_request(self):
        if not self.property_line_ids:
            raise ValidationError(_('''Please Load Properties !'''))
        if not self.property_id:
            raise ValidationError(_('''You have not selected any property, please select any !'''))
        if self.ask_price_amount <= 0:
            raise ValidationError(_('''Ask Price must be positive !'''))
        booking_type_id=self.env['property.booking']
        
        vals = {'partner_id': self.partner_id and self.partner_id.id or False,
                'property_id': self.property_id and self.property_id.id or False,
                'booking_date': date.today(),
                'ask_price_amount': self.ask_price_amount,
                'property_type': self.property_type,
                'owner_partner_id': self.property_id and self.property_id.owner_partner_id and self.property_id.owner_partner_id.id or False,
                'agent_partner_id': self.agent_id and self.agent_id.id or False,
                'commission_type': self.agent_commission_type,
                'commission_amount':self.agent_commission_percentage
                }
        booking_id = self.env['property.booking'].sudo().create(vals)
        action = self.env.ref('dev_property_management.action_property_booking').sudo().read()[0]
        action['views'] = [(self.env.ref('dev_property_management.form_property_booking').id, 'form')]
        action.update({'res_id': booking_id.id})
        return action

    def load_properties(self):
        self.property_line_ids.sudo().unlink()
        lines = []
        domain = [('property_type', '=', self.property_type),
                  ('property_purpose', '!=', 'parent'),
                  ('state', '=', 'draft'),
                  ('property_purpose', '=', 'sell'),
                  ('price_amount', '>=', self.minimum_budget),
                  ('price_amount', '<=', self.maximum_budget)]
        if self.furnishing:
            domain.append(('furnishing', '=', self.furnishing))
        if self.total_square_foot > 0:
            domain.append(('total_square_foot', '<=', self.total_square_foot))
        if self.property_type == 'residential' and self.residential_type_id:
            domain.append(('residential_type_id', '=', self.residential_type_id.id))
        if self.property_type == 'commercial' and self.commercial_type_id:
            domain.append(('commercial_type_id', '=', self.commercial_type_id.id))
        if self.property_type == 'industrial':
            if self.industrial_location:
                domain.append(('industrial_location', '=', self.industrial_location))
            if self.industrial_type_id:
                domain.append(('industrial_type_id', '=', self.industrial_type_id.id))
            if self.property_status:
                domain.append(('property_status', '=', self.property_status))
        property_ids = self.env['property.property'].search(domain)
        if property_ids:
            for property_id in property_ids:
                vals = {'property_id': property_id.id, 'booking_widow_id': self.id}
                lines.append((0, 0, vals))
        if lines:
            self.property_line_ids = lines
            action = self.env.ref('dev_property_management.action_booking_window_dev_property_management').sudo().read()[0]
            action.update({'res_id': self.id})
            return action
        else:
            raise ValidationError(_('''No properties found in given criteria !'''))

    def action_open_booking_window(self):
        action = self.env.ref('dev_property_management.action_booking_window_dev_property_management').sudo().read()[0]
        line_ids = self.env['property.line'].sudo().search([])
        if line_ids:
            line_ids.sudo().unlink()
        return action

    # @api.depends("agent_commission_percentage")
    # def _compute_commission_amount(self):
    #     percentage_amount=0
    #     for rec in self:
    #         if self.price_amount:
    #             percentage_amount=(self.price_amount*self.agent_commission_percentage)/100
    #         self.agent_commission_amount=percentage_amount




    

    @api.onchange('property_type', 'furnishing', 'residential_type_id', 'commercial_type_id', 'industrial_type_id')
    def onchange_furnishing_property_type(self):
        self.property_id = False
        self.ask_price_amount = 0

    minimum_budget = fields.Float(string='Minimum Budget')
    maximum_budget = fields.Float(string='Maximum Budget')
    property_type = fields.Selection(string='Property Type', selection=[('residential', 'Residential'),
                                                                        ('commercial', 'Commercial'),
                                                                        ('industrial', 'Industrial'),
                                                                        ('land', 'Land')],
                                     default='residential', required=True)
    furnishing = fields.Selection(string='Furnishing',
                                  selection=[('non_furnished', 'Non Furnished'),
                                             ('semi_furnished', 'Semi Furnished'),
                                             ('fully_furnished', 'Fully Furnished')])
    total_square_foot = fields.Float(string='Total Size(sq.ft.)')
    property_status = fields.Selection(string='Status',
                                       selection=[('new', 'Newly Constructed'),
                                                  ('re_sale', 'Re-Sale'),
                                                  ('under_construction', 'Under Construction')])
    property_line_ids = fields.Many2many('property.line', 'booking_widow_id', string='Property Line')
    property_id = fields.Many2one('property.property', string='Property')
    residential_type_id = fields.Many2one('residential.type', string='Type of Residential')
    commercial_type_id = fields.Many2one('commercial.type', string='Type of Commercial')
    industrial_type_id = fields.Many2one('industrial.type', string='Type of Industrial')
    industrial_location = fields.Selection(string='Location', selection=[('inside_city', 'In City'),
                                                                         ('outside_city', 'Outside of City')])
                                
    
    ask_price_amount = fields.Float(string='Ask Price')
    price_amount = fields.Float(string='Selling Price', related='property_id.price_amount')
    rent_amount = fields.Float(string='Monthly Rent', related='property_id.rent_amount')
    partner_id = fields.Many2one('res.partner', string='Contact', default=lambda self: self.env.user and self.env.user.partner_id and self.env.user.partner_id.id or False)
    agent_id = fields.Many2one('res.partner', string='Agent', domain=[('is_agent', '=', True)])
    agent_commission_percentage=fields.Float(string="Commission Amount")
    # agent_commission_amount=fields.Float(string="Commission Amount",compute="_compute_commission_amount" )
    agent_commission_type=fields.Selection(string='Commission Type',
                                       selection=[('fix', 'Fixed Amount'),
                                                  ('percentage', 'Percentage of Selling Price'),],
                                       default='fix', tracking=1)


class PropertyLine(models.TransientModel):
    _name = 'property.line'
    _description = 'Property Available for booking'

    def select_property(self):
        self.booking_widow_id.property_id = self.property_id and self.property_id.id or False
        action = self.env.ref('dev_property_management.action_booking_window_dev_property_management').sudo().read()[0]
        action.update({'res_id': self.booking_widow_id.id})
        return action

    
    

    booking_widow_id = fields.Many2one('booking.window', string='Booking Window', ondelete='cascade')
    property_id = fields.Many2one('property.property', string='Property')
    owner_partner_id = fields.Many2one('res.partner', string='Owner', related='property_id.owner_partner_id')
    contact_phone = fields.Char(string='Phone', related='owner_partner_id.phone')
    contact_mobile = fields.Char(string='Mobile', related='owner_partner_id.phone')
    price_amount = fields.Float(string='Selling Price', related='property_id.price_amount')
    rent_amount = fields.Float(string='Monthly Rent', related='property_id.rent_amount')
    total_square_foot = fields.Float(string='Total Size(sq.ft.)', related='property_id.total_square_foot')
    deposit_amount = fields.Float(string='Security Deposit', related='property_id.deposit_amount')
    


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: