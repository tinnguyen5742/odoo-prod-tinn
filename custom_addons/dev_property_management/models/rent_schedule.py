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
from datetime import date, timedelta, datetime
from odoo.exceptions import UserError,ValidationError

import ast

class RentSchedule(models.Model):
    _name = 'rent.schedule'
    _description = 'Rent Schedule'

    @api.model
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].next_by_code('rent.schedule') or '/'
        return super(RentSchedule, self).create(vals_list)

    def send_rent_reminder_emails(self):
        if self.env.company.send_rent_email:
            template_id = self.env.ref('dev_property_management.template_rent_reminder_before_days')
            if template_id:
                before_days = self.env.company and self.env.company.rent_reminder_days
                if before_days > 0:
                    rent_date = date.today() + timedelta(days=int(before_days))
                    rent_ids = self.env['rent.schedule'].search([('date', '=', rent_date)])
                    if rent_ids:
                        for rent_id in rent_ids:
                            if rent_id.state == 'unpaid':
                                template_id.send_mail(rent_id.id, force_send=True)
            if self.env.company.send_rent_same_day:
                template_id = self.env.ref('dev_property_management.template_rent_reminder_same_day')
                if template_id:
                    rent_ids = self.env['rent.schedule'].search([('date', '=', date.today())])
                    if rent_ids:
                        for rent_id in rent_ids:
                            if rent_id.state == 'unpaid':
                                template_id.send_mail(rent_id.id, force_send=True)

    def get_rent_date(self):
        rent_date = datetime.strptime(str(self.date), "%Y-%m-%d").strftime('%d-%m-%Y')
        return rent_date

    def rent_url(self):
        ir_param = self.env['ir.config_parameter'].sudo()
        base_url = ir_param.get_param('web.base.url')
        action_id = self.env.ref('dev_property_management.action_property_rent_schedule').id
        menu_id = self.env.ref('dev_property_management.root_menu_property').id
        if base_url:
            base_url += '/web#id=%s&action=%s&model=%s&view_type=form&cids=&menu_id=%s' % (int(self.id), action_id, self._name, menu_id)
        return base_url
        
    def auto_generate_payment(self):
        if not (self.env.company.rent_product_id and self.env.company.rent_invoice_auto_day ):
            raise ValidationError(_('Please Configure Rent Product or Rent Invoice Before Days '))
        final_date = date.today() + timedelta(days=int(self.env.company.rent_invoice_auto_day))
        search_rent_id = self.search([('date','=',final_date),('invoice_id','=',False)])
        if search_rent_id:
            for rent_line in search_rent_id:
                invoice_vals = {
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_id.id,
                    'invoice_origin': self.name or 'Rent Invoice',
                    'invoice_line_ids': [(0, 0, {
                        'product_id': self.env.company.rent_product_id.id,
                        'name':  'Rent',
                        'quantity': 1,
                        'price_unit': self.rent_amount,
                    })],
                }
                
                invoice = self.env['account.move'].sudo().create(invoice_vals)
                
                track_value = {
                               'rent_number':rent_line.name,
                               'partner_id':rent_line.tenancy_id.partner_id and rent_line.tenancy_id.partner_id.id,
                               'property_id':rent_line.tenancy_id.property_id and rent_line.tenancy_id.property_id.id,
                               'owner_partner_id':rent_line.tenancy_id.property_id and rent_line.tenancy_id.owner_partner_id.id,
                               'installment_payment_date':rent_line.date,
                               'rent_amount':rent_line.rent_amount,
                             }
                
                track_owner_payment_id = self.env['track.owner.payment'].create(track_value)
                
                invoice_vals = {
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_id.id,
                    'invoice_origin': self.name or 'Rent Invoice',
                    'invoice_line_ids': [(0, 0, {
                        'product_id': self.env.company.rent_product_id.id,
                        'name':  'Rent',
                        'quantity': 1,
                        'price_unit': self.rent_amount,
                    })],
                }
                
                invoice = self.env['account.move'].sudo().create(invoice_vals)
                
                
                
                
    #            invoice.action_post()  
                rent_line.invoice_id = invoice.id

    def generate_payment(self):
        if not self.env.company.rent_product_id:
            raise ValidationError(_('Please Configure Rent Product '))
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_origin': self.name or 'Rent Invoice',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.env.company.rent_product_id.id,
                'name':  'Rent',
                'quantity': 1,
                'price_unit': self.rent_amount,
#                'account_id': rent_product.property_account_income_id.id or rent_product.categ_id.property_account_income_categ_id.id,
            })],
        }
        
        invoice = self.env['account.move'].sudo().create(invoice_vals)
        track_value = {
                        'rent_number':self.name,
                        'partner_id':self.tenancy_id.partner_id and self.tenancy_id.partner_id.id,
                        'property_id':self.tenancy_id.property_id and self.tenancy_id.property_id.id,
                        'owner_partner_id':self.tenancy_id.property_id and self.tenancy_id.owner_partner_id.id,
                        'installment_payment_date':self.date,
                        'rent_amount':self.rent_amount,
                     }
        
        track_owner_payment_id = self.env['track.owner.payment'].create(track_value)
        invoice.action_post()  
        self.invoice_id = invoice.id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': invoice.id,
            'target': 'current',
        }
        return action

    def post_payment(self):
        if self.payment_id:
            self.payment_id.sudo().action_post()

    def view_payment(self):
        action = self.env.ref('account.action_move_out_invoice_type').sudo().read()[0]
        action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
        action.update({'res_id': self.invoice_id.id})
        return action

    @api.depends('invoice_id.payment_state')
    def _compute_state(self):
        for rent in self:
            status = 'unpaid'
            if rent.invoice_id and rent.invoice_id.payment_state == 'paid':
                status = 'paid'
            rent.state = status

    def _compute_is_posted(self):
        for rec in self:
            flag = True
            if rec.payment_id and rec.payment_id.state != 'posted':
                flag = False
            rec.is_posted = flag
    
    def payment_by_deposit(self):
        adv_payment_id = self.tenancy_id and self.tenancy_id.deposit_payment_id
        if not adv_payment_id:
            raise ValidationError(_('Deposit Payment Not Found'))
        if adv_payment_id.amount < self.rent_amount:
            raise ValidationError(_('You have insufficient deposit amount'))
        else:
            security_deposite = adv_payment_id.amount - self.rent_amount 
            self.payment_id.amount = security_deposite
        return True

    tenancy_id = fields.Many2one('property.tenancy', string='Tenancy', ondelete='cascade') # link
    name = fields.Char(string='Name', required=True)
    date = fields.Date(string='Date')
    rent_amount = fields.Float(string='Rent Amount')
    cheque_number = fields.Char(string='Cheque Number')
    state = fields.Selection(string='Status', selection=[('unpaid', 'Unpaid'),
                                                         ('paid', 'Paid')], compute='_compute_state', store=True)
    partner_id = fields.Many2one('res.partner', related='tenancy_id.partner_id', string='Tenant')
    property_id = fields.Many2one('property.property', related='tenancy_id.property_id', string='Property')
    payment_id = fields.Many2one('account.payment', string='Payment', copy=False)
    invoice_id = fields.Many2one('account.move', string='Invoice', copy=False)
    is_posted = fields.Boolean(string='Is Posted', compute='_compute_is_posted')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
