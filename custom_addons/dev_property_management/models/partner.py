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


class Partner(models.Model):
    _inherit = 'res.partner'

    def view_agreements(self):
        agreements_ids = self.env['property.agreement'].search([('partner_id', '=', self.id)])
        action = self.env.ref('dev_property_management.action_property_agreement').sudo().read()[0]
        if len(agreements_ids) > 1:
            action['domain'] = [('id', 'in', agreements_ids.ids)]
        elif len(agreements_ids) == 1:
            action['views'] = [(self.env.ref('dev_property_management.form_property_agreement').id, 'form')]
            action['res_id'] = agreements_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def _compute_agreement_count(self):
        for partner in self:
            agreements_ids = self.env['property.agreement'].search([('partner_id', '=', partner.id)])
            counter = len(agreements_ids.ids)
            partner.agreement_count = counter

    def view_properties(self):
        property_ids = self.env['property.property'].search(['|', ('owner_partner_id', '=', self.id),
                                                             ('tenant_partner_id', '=', self.id)])
        action = self.env.ref('dev_property_management.action_property_dev_property_management').sudo().read()[0]
        if len(property_ids) > 1:
            action['domain'] = [('id', 'in', property_ids.ids)]
        elif len(property_ids) == 1:
            action['views'] = [(self.env.ref('dev_property_management.form_property_dev_property_management').id, 'form')]
            action['res_id'] = property_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def _compute_property_count(self):
        for partner in self:
            property_ids = self.env['property.property'].search(['|', ('owner_partner_id', '=', partner.id),
                                                                 ('tenant_partner_id', '=', partner.id)])
            counter = len(property_ids.ids)
            partner.property_count = counter

    def view_bookings(self):
        booking_ids = self.env['property.booking'].search([('partner_id', '=', self.id)])
        action = self.env.ref('dev_property_management.action_property_booking').sudo().read()[0]
        if len(booking_ids) > 1:
            action['domain'] = [('id', 'in', booking_ids.ids)]
        elif len(booking_ids) == 1:
            action['views'] = [(self.env.ref('dev_property_management.form_property_booking').id, 'form')]
            action['res_id'] = booking_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def _compute_bookings_count(self):
        for partner in self:
            booking_ids = self.env['property.booking'].search([('partner_id', '=', partner.id)])
            counter = len(booking_ids.ids)
            partner.bookings_count = counter

    def view_tenancies(self):
        tenancy_ids = self.tenancy_ids
        action = self.env.ref('dev_property_management.action_property_tenancy').sudo().read()[0]
        if len(tenancy_ids) > 1:
            action['domain'] = [('id', 'in', tenancy_ids.ids)]
        elif len(tenancy_ids) == 1:
            action['views'] = [(self.env.ref('dev_property_management.form_property_tenancy').id, 'form')]
            action['res_id'] = tenancy_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def _compute_tenancy_count(self):
        for partner in self:
            counter = len(partner.tenancy_ids.ids)
            partner.tenancy_count = counter

    def _compute_invoice_count(self):
        for partner in self:
            counter = 0
            invoice_ids = self.env['account.move'].search([('partner_id', '=', partner.id),
                                                           ('is_maintenance_invoice', '=', True),
                                                           ('move_type', '=', 'out_invoice')])
            if invoice_ids:
                counter = len(invoice_ids)
            counter = counter
            partner.invoice_count = counter

    def view_maintenance_invoices(self):
        invoice_ids = self.invoice_ids
        action = self.env.ref('account.action_move_out_invoice_type').sudo().read()[0]
        action.update({'display_name': 'Maintenance Invoices'})
        if len(invoice_ids) > 1:
            action['domain'] = [('id', 'in', invoice_ids.ids), ('move_type', '=', 'out_invoice')]
        elif len(invoice_ids) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = invoice_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def view_rent_schedule(self):
        records_ids=self.env['rent.schedule'].search([('partner_id','=',self.id)])
        action = self.env.ref('dev_property_management.action_property_rent_schedule').sudo().read()[0]
        if len(records_ids) > 1:
            action['domain'] = [('id', 'in', records_ids.ids)]
        elif len(records_ids) == 1:
            action['views'] = [(self.env.ref('dev_property_management.form_property_rent_schedule').id, 'form')]
            action['res_id'] = records_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def _compute_rent_schedule(self):
        for partner in self:
            rent_schedule=0
            records=self.env['rent.schedule'].search([('partner_id','=',partner.id)])
            rent_schedule = len(records)
            partner.rent_schedule_count = rent_schedule

    is_owner = fields.Boolean(string='Owner', copy=False)
    is_tenant = fields.Boolean(string='Tenant', copy=False)
    is_agent = fields.Boolean(string='Agent', copy=False)
    agreement_count = fields.Integer(string='Agreement Counter', compute='_compute_agreement_count')
    property_count = fields.Integer(string='Property Counter', compute='_compute_property_count')
    bookings_count = fields.Integer(string='Booking Counter', compute='_compute_bookings_count')
    tenancy_ids = fields.One2many('property.tenancy', 'partner_id', string='Tenancy')
    tenancy_count = fields.Integer(string='Tenancy Counter', compute='_compute_tenancy_count')
    invoice_ids = fields.One2many('account.move', 'partner_id', string='Invoices')
    invoice_count = fields.Integer(string='Invoice Counter', compute='_compute_invoice_count')
    rent_schedule_count=fields.Integer(string="rent Schedule" , compute='_compute_rent_schedule')

    blacklisted=fields.Boolean('Blacklisted Agent')
    blacklisted_reason=fields.Text('Blacklist Reason ')
    count_commission_agent = fields.Integer('View Agent Commision', compute='_count_commission_agent')

    def _count_commission_agent(self):
        counter=0 
        for rec in self:
            commission_ids = self.env['agent.commission'].search([('agent_partner_id','=',self.id)])
            
            commission = commission_ids.ids
            
            counter = len(commission)
        rec.count_commission_agent = counter        
            
    def action_view_commission_agent(self):
        commission_ids = self.env['agent.commission'].search([('agent_partner_id','=',self.id)])
        
        if commission_ids:
            action = self.env.ref('dev_property_management.action_dev_agent_commission').read()[0]
            action['domain'] = [('id', 'in', commission_ids.ids)]
            return action
        else:
            action = {'type': 'ir.actions.act_window_close'}   

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
