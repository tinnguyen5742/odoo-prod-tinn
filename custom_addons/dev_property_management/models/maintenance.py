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
import ast
from odoo.exceptions import ValidationError

class Maintenance(models.Model):
    _name = 'tenancy.maintenance'
    _description = 'Tenancy Maintenance'

    tenancy_id = fields.Many2one('property.tenancy', string='Tenancy', ondelete='cascade') # link
    property_id = fields.Many2one('property.property', string='Property', ondelete='cascade') # link
    maintenance_type_id = fields.Many2one('property.maintenance.type', string='Maintenance Type', required=True)
    maintenance_amount = fields.Float(string='Maintenance Amount')
    
class maintenance_request(models.Model):
    _inherit = 'maintenance.request'

    partner_id = fields.Many2one('res.partner', string='Customer') 
    property_id = fields.Many2one('property.property', string='Property', ondelete='cascade') 
    tenancy_id = fields.Many2one('property.tenancy', string='Tenancy', ondelete='cascade') 
    cost = fields.Float(string='Maintenance Cost') 
    
    street = fields.Char(string='Street') 
    street2 = fields.Char(string='street2') 
    city_id = fields.Many2one('property.city',string='City') 
    state_id = fields.Many2one('res.country.state',string='State') 
    zip = fields.Char(string='Zip') 
    country_id = fields.Many2one('res.country',string='Country') 
    
    def create_maintenance_invoice(self):
        if self.cost <= 0:
            raise ValidationError('Add Maintenance Cost  !')
        action = self.env.ref('account.action_move_out_invoice_type').sudo().read()[0]
        action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
        context_dict = ast.literal_eval(action['context'])
        context_dict.update({
            'default_partner_id': self.partner_id.id,
            'default_move_type': 'out_invoice',
            'default_maintenance_id': self.id,
            'default_invoice_line_ids': [(0, 0, {
            'product_id': self.env.company.rent_product_id.id or False,
            'name': 'Maintenance',
            'price_unit': self.cost,
            'quantity': 1,
            })],
        })
        action['context'] = str(context_dict)
        return action
        
        

    def view_maintenance_invoices(self):
        invoice_ids = self.env['account.move'].search([('maintenance_id','=',self.id)])
        if not invoice_ids:
            raise ValidationError('No Invoice Found !')
        action = self.env.ref('account.action_move_out_invoice_type').sudo().read()[0]
        action.update({'display_name': 'Maintenance Invoices'})
        if len(invoice_ids) > 1:
            action['domain'] = [('id', 'in', invoice_ids.ids)]
        elif len(invoice_ids) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = invoice_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action
    
    @api.onchange('property_id')
    def _onchange_property(self):
        if self.property_id:
            self.street =   self.property_id.street or ''
            self.street2 = self.property_id.street2 or ''
            self.city_id = self.property_id.city_id and self.property_id.city_id.id  or False
            self.state_id = self.property_id.state_id and self.property_id.state_id.id or False
            self.zip = self.property_id.zip or ''
            self.country_id = self.property_id.country_id and self.property_id.country_id.id or False
    
    @api.onchange('tenancy_id')
    def _onchange_tenancy_id(self):
        if self.tenancy_id:
            self.partner_id = self.tenancy_id and self.tenancy_id.partner_id.id or False
    
#    maintenance_type_id = fields.Many2one('property.maintenance.type', string='Maintenance Type', required=True)
#    maintenance_amount = fields.Float(string='Maintenance Amount')
    
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
