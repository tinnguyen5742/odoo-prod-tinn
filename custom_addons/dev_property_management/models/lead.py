# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date
import random


class Lead(models.Model):
    _inherit = 'crm.lead'
    
    def action_property_book(self):
        if not self.property_id:
            raise UserError("Enter Property.")
        if self._context.get('book_for_rental'):
            tenancy_id = self.env['property.tenancy'].create({'property_id':self.property_id.id,
                                                              'partner_id':  self.partner_id.id,
                                                              'lead_id':self.id,
                                                              'owner_partner_id':self.property_id.owner_partner_id.id or False,
                                                              'property_type':self.property_id.property_type,
                                                              'lead_id':self.id,
#                                                              'rent_amount':self.property_id.rent_amount
                                                        })
            self.tenancy_id = tenancy_id.id
            self.tenancy_id.onchange_property_id()
            action = self.env["ir.actions.actions"]._for_xml_id("dev_property_management.action_property_tenancy")
            action['domain'] = [('id', '=', tenancy_id.id)]
#            action['views'] = [(self.env.ref('dev_property_management.form_property_tenancy').id, 'form')]
#            action['res_id'] = list_id[0]
            return action
        
        else:
        
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'property.booking',
                'view_mode': 'form',
                'context': {
                        'default_property_id': self.property_id and self.property_id.id,
                        'default_partner_id': self.partner_id and self.partner_id.id,
                        'default_lead_id': self.id,
                    },         
                'target': 'current',
            }
            return True

    def action_view_booking(self):
        if self._context.get('book_for_rental'):
            action = self.env["ir.actions.actions"]._for_xml_id("dev_property_management.action_property_tenancy")
            action['views'] = [(self.env.ref('dev_property_management.form_property_tenancy').id, 'form')]
            action['res_id'] = self.tenancy_id and self.tenancy_id.id or False 
            return action
        else:
            action = self.env["ir.actions.actions"]._for_xml_id("dev_property_management.action_property_booking")
            action['domain'] = [('lead_id', '=', self.id)]
            return action

    
#    LEAD SEQUEANCE NUMBER
    @api.model
    def create(self,vals_list):
        for vals in vals_list:
            vals['number'] = self.env['ir.sequence'].sudo().next_by_code('crm.lead.number') or 'New'
            res=super(Lead,self).create(vals_list)
        # if res.property_id:
        #     res.property_purpose = res.property_id.property_purpose
        return res

    number = fields.Char(string='Reference Number', default='New', readonly=1)
    property_id = fields.Many2one('property.property',string='Property', required=1)
    tenancy_id = fields.Many2one('property.tenancy',string='tenancy')
    property_purpose = fields.Selection(string='Purpose',
                                        selection=[('parent', 'Parent Property'),
                                                   ('rent', 'For Rent'),
                                                   ('sell', 'For Sell')],
                                                     tracking=1,)

    booking_count = fields.Integer(compute='_get_booking_count')

    def _get_booking_count(self):
        for rec in self:
            rec.booking_count = self.env['property.booking'].search_count([('lead_id', '=', rec.id)])



# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
