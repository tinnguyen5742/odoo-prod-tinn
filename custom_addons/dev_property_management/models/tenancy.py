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
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError
import calendar
from odoo.exceptions import RedirectWarning
import ast

class Tenancy(models.Model):
    _name = 'property.tenancy'
    _inherit = ['mail.thread','portal.mixin']
    _description = 'Property Tenancy'
    _order = 'id desc'

    #    PORTAL
    def _compute_access_url(self):
        super(Tenancy, self)._compute_access_url()
        for property in self:
            property.access_url = '/my/tenant_property_details/%s' % (property.id)
            
    def _get_report_base_filename(self):
        self.ensure_one()
        return '%s %s' % (_('Tenant Property'), self.name)

    # #    PORTAL
    # def _compute_access_url(self):
    #     super(Tenancy, self)._compute_access_url()
    #     for property in self:
    #         property.access_url = '/my/tenant_property_details/%s' % (property.id)
            
    # def _get_report_base_filename(self):
    #     self.ensure_one()
    #     return '%s %s' % (_('Tenant Property'), self.name)


    @api.model
    def create(self, vals_list):
        for vals in vals_list:

            vals['name'] = self.env['ir.sequence'].next_by_code('property.tenancy') or '/'
        return super(Tenancy, self).create(vals_list)

    @api.onchange('property_type')
    def onchange_property_type(self):
        self.property_id = False

    @api.onchange('property_id')
    def onchange_property_id(self):
        self.rent_amount = self.property_id and self.property_id.rent_amount or 0
        self.deposit_amount = self.property_id and self.property_id.deposit_amount or 0
        self.owner_partner_id = self.property_id and self.property_id.owner_partner_id or False

    @api.depends('duration', 'interval_type', 'start_date')
    def _compute_end_date(self):
        for tenancy in self:
            end_date = False
            if tenancy.interval_type == 'months':
                end_date = tenancy.start_date + relativedelta(months=+tenancy.duration)
            else:
                end_date = tenancy.start_date + relativedelta(years=+tenancy.duration)
            tenancy.end_date = end_date

    def confirm_tenancy(self):
        tenancy_id = self.env[self._name].search([('id', '!=', self.id),
                                                  ('property_id', '=', self.property_id.id),
                                                  ('state', '=', 'running')], limit=1)
        if tenancy_id:
            raise ValidationError(_('''Tenancy '%s' is already running\n\nTenant : %s \nProperty : %s''')
                                  % (tenancy_id.name, tenancy_id.partner_id.name, tenancy_id.property_id.name))
        if not self.rent_type_id:
            raise ValidationError(_(''' Add Rental Type !'''))
        if self.rent_amount <= 0:
            raise ValidationError(_(''' Add Monthly Rent !'''))
        if not self.partner_id:
            raise ValidationError(_(''' Add Tenant !'''))
        
        self.state = 'confirm'
        self.confirmation_date = date.today()
        self.property_id.tenant_partner_id = self.partner_id.id
        self.property_id.state = 'on_rent'

    def close_tenancy(self):
        for agreement_id in self.agreement_ids:
            if agreement_id.state == 'running':
                raise ValidationError(_(''''%s' Agreement is still running, cancel it to move further!''') % (agreement_id.name))
        for agreement_id in self.agreement_ids:
            agreement_id.expire_agreement()
        self.state = 'closed'
        self.property_id.tenant_partner_id = False
        self.property_id.state = 'draft'

    def cancel_tenancy(self):
        for agreement_id in self.agreement_ids:
            if agreement_id.state == 'running':
                raise ValidationError(_(''''%s' Agreement is still running, cancel it to move further!''') % (agreement_id.name))
        self.state = 'cancelled'
        self.property_id.tenant_partner_id = False
        self.property_id.state = 'draft'

    def set_to_new(self):
        self.state = 'draft'

    def get_month_differance(self, end_date, start_date):
        differance = relativedelta(end_date, start_date)
        months = (differance.years * 12) + differance.months
        return months

    def generate_rent_schedule(self):
        self.state = 'running'
        if self.end_date <= self.start_date:
            raise ValidationError(_('''End Date must be greater than Start Date !'''))
        if self.start_date < self.confirmation_date:
            raise ValidationError(_('''Start Date must be greater than or equal to Confirmation Date !'''))
        self.rent_schedule_ids.sudo().unlink()
        date_list = []
        new_date = self.start_date
        while new_date < self.end_date:
            date_list.append(new_date)
            if self.rent_type_id.interval == 'monthly':
                new_date = new_date + relativedelta(months=1)
#                new_date = new_date + relativedelta(months=int(self.rent_type_id.duration))
            else:
                new_date = new_date + relativedelta(years=int(self.rent_type_id.duration))
        if date_list:
            advance_days = (self.start_date - self.confirmation_date).days
            if advance_days > 0:
                confirmation_date_month_days = calendar.monthrange(self.confirmation_date.year, self.confirmation_date.month)[1]
                per_day_rent = self.rent_amount / confirmation_date_month_days
                advance_rent = per_day_rent * advance_days
                # generating rent for advance installment which is the duration between tenancy start date and confirmation date
                vals = {'tenancy_id': self.id,
                       'date': self.confirmation_date,
                       'rent_amount': advance_rent}
                self.env['rent.schedule'].create(vals)
            if self.rent_type_id.interval == 'monthly':
                line_rent = self.rent_amount
            else:
                year_months = int(self.rent_type_id.duration) * 12
                line_rent = self.rent_amount * year_months
            lines = []
            last_date = date_list.pop()
            # generating fixes installments by month filters
            for line_date in date_list:
                vals = {'tenancy_id': self.id,
                        'date': line_date,
                        'rent_amount': line_rent}
                lines.append((0, 0, vals))
            if lines:
                self.rent_schedule_ids = lines
            # generating rent for last installments based on month differance
            month_differance = self.get_month_differance(self.end_date, last_date)
            vals = {'tenancy_id': self.id,
                    'date': last_date,
                    'rent_amount': self.rent_amount * month_differance}
            self.env['rent.schedule'].create(vals)

    def view_agreements(self):
        agreements_ids = self.agreement_ids
        action = self.env.ref('dev_property_management.action_property_agreement_rent').sudo().read()[0]
        if len(agreements_ids) > 1:
            action['domain'] = [('id', 'in', agreements_ids.ids)]
        elif len(agreements_ids) == 1:
            action['views'] = [(self.env.ref('dev_property_management.form_property_agreement').id, 'form')]
            action['res_id'] = agreements_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def refund_deposite(self):
        records = self.env['account.payment'].search(
            [('partner_id', '=', self.partner_id.id), ('payment_type', '=', 'inbound'), ('deposit_tenancy_id', '=', self.id)])
        if not records:
            raise ValidationError(_("Please credit some amount first."))
        if self.deposit_payment_id.amount == 0:
            records=self.env['rent.schedule'].search([('payment_id','=',self.deposit_payment_id.id)])
            rent_name=[]
            for record in records:
                rent_name.append(record.name)
            
            rent = f"Your deposit amount already used {', '.join(str(record) for record in rent_name)}"   
            raise ValidationError(_(rent))
        for record in records:
            vals = {
                'payment_type': 'outbound',
                'amount': record.amount,
                'date': fields.Date.today(),
                'partner_id': record.partner_id and record.partner_id.id or False,
                'ref': f"Refund Security Deposit",
                'partner_type': 'supplier',
                # 'deposit_tenancy_id': record.id,
            }
            return_payment = self.env['account.payment'].create(vals)
        self.deposit_refunded = True
        return True

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
                'default_rent_id': self.id,
                'default_rent_id': self.id,
                'default_agent_partner_id':self.rent_agent_id.id or ''
            },
        }

    def create_maintenance(self):
    # Prepare the action to open the booking form view
    
        return {
            'name': 'Create maintenance',
            'type': 'ir.actions.act_window',
            'res_model': 'maintenance.request',  # The model associated with the booking
            'view_mode': 'form',
            'view_id': self.env.ref('maintenance.hr_equipment_request_view_form').id,  # Form view ID
#            'target': 'new',  # Open in a modal dialog
            'context': {
                'default_property_id': self.property_id and self.property_id.id or False ,
                'default_tenancy_id': self.id,
                
                
                'default_street': self.property_id and self.property_id.street ,
                'default_street2': self.property_id and self.property_id.street2,
                'default_city_id': self.property_id.city_id and self.property_id.city_id.id or False,
                'default_state_id': self.property_id.state_id and self.property_id.state_id.id or False ,
                'default_zip': self.property_id.zip,
                'default_country_id': self.property_id.country_id and self.property_id.country_id.id or False,
            },
        }

    count_commission_agent = fields.Integer('View Agent Commision', compute='_count_commission_agent')

    def _count_commission_agent(self):
        counter=0 
        for rec in self:
            commission_ids = self.env['agent.commission'].search([('rent_id','=',self.id),('agent_partner_id','=',self.rent_agent_id.id)])
            
            commission = commission_ids.ids
            
            counter = len(commission)
        rec.count_commission_agent = counter        
            
    def action_view_commission_agent(self):
        commission_ids = self.env['agent.commission'].search([('rent_id','=',self.id),('agent_partner_id','=',self.rent_agent_id.id)])
        
        if commission_ids:
            action = self.env.ref('dev_property_management.action_dev_agent_commission').read()[0]
            action['domain'] = [('id', 'in', commission_ids.ids)]
            return action
        else:
            action = {'type': 'ir.actions.act_window_close'}


    def action_view_lead(self):
        action = self.env.ref('dev_property_management.action_dev_property_lead').read()[0]
        action['domain'] = [('id', '=', self.lead_id.id)]
        return action

    

    

    def _compute_agreement_count(self):
        for agreement in self:
            counter = len(agreement.agreement_ids)
            agreement.agreement_count = counter

    def generate_maintenance_invoice(self):
        if not self.maintenance_ids:
            raise ValidationError(_('''Please add Maintenance details !'''))
        product_id = self.env.company and self.env.company.maintenance_product_id or False
        if not product_id:
            action = self.env.ref('dev_property_management.action_config_dev_property_management')
            msg = _('Configure Maintenance Product into the configuration')
            raise RedirectWarning(msg, action.id, _('Go to the configuration panel'))
        account_id = False
        if product_id:
            account_id = product_id.property_account_income_id or False
        if not account_id:
            account_id = product_id.categ_id and product_id.categ_id.property_account_income_categ_id or False
        if not account_id:
            raise ValidationError(_('''There is no income account defined for the product '%s' ''') % (product_id.name))
        description = 'Maintenance of ' + str(self.name)
        amount = sum(line.maintenance_amount for line in self.maintenance_ids)
        vals = {'move_type': 'out_invoice',
                'partner_id': self.partner_id and self.partner_id.id or False,
                'tenancy_id': self.id,
                'property_id': self.property_id and self.property_id.id or False,
                'invoice_date': date.today(),
                'is_maintenance_invoice': True,
                'invoice_line_ids': [(0, 0, {'name': description,
                                             'product_id': product_id.id,
                                             'account_id': account_id.id,
                                             'price_unit': amount,
                                             'quantity': 1.0,
                                             'product_uom_id': product_id.uom_id and product_id.uom_id.id or False})
                                     ]}
        self.env['account.move'].create(vals)

    def _compute_invoice_count(self):
        for tenancy in self:
            counter = 0
            if tenancy.invoice_ids:
                invoice_ids = self.env['account.move'].search([('id', 'in', tenancy.invoice_ids.ids), ('move_type', '=', 'out_invoice')])
                if invoice_ids:
                    counter = len(invoice_ids)
            tenancy.invoice_count = counter

    def _compute_maintenance_count(self):
        for tenancy in self:
            counter = 0
            maintenance_ids = self.env['maintenance.request'].search([('tenancy_id', '=', self.id)])
            if maintenance_ids:
                counter = len(maintenance_ids)
            tenancy.maintenance_count = counter

    def view_maintenance_invoices(self):
        invoice_ids = self.env['account.move'].search([('id', 'in', self.invoice_ids.ids), ('move_type', '=', 'out_invoice')])
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

    def view_maintenance(self):
        maintenance_ids = self.env['maintenance.request'].search([('tenancy_id', '=', self.id)])
        action = self.env.ref('maintenance.hr_equipment_request_action').sudo().read()[0]
        if len(maintenance_ids) > 1:
            action['domain'] = [('id', 'in', maintenance_ids.ids)]
        elif len(maintenance_ids) == 1:
            action['views'] = [(self.env.ref('maintenance.hr_equipment_request_view_form').id, 'form')]
            action['res_id'] = maintenance_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def generate_agent_commission(self):
        if not self.agent_partner_id:
            raise ValidationError(_('''Please select Agent !'''))
        if not self.commission_type:
            raise ValidationError(_('''Please select Commission Type !'''))
        if self.commission_amount <= 0:
            raise ValidationError(_('''Commission Amount must be positive !'''))
        amount = self.commission_amount
        if self.commission_type == 'percentage':
            amount = self.rent_amount * self.commission_amount / 100
        action = self.env.ref('account.action_account_payments_payable').sudo().read()[0]
        action['views'] = [(self.env.ref('account.view_account_payment_form').id, 'form')]
        context_dict = ast.literal_eval(action['context'])
        context_dict.update({'default_amount': amount,
                             'default_partner_id': self.agent_partner_id.id,
                             'default_commission_tenancy_id': self.id})
        action['context'] = str(context_dict)
        return action

    def generate_deposit_payment(self):
        if self.deposit_amount <= 0:
            raise ValidationError(_('''Security Deposit Amount must be positive !'''))
        action = self.env.ref('account.action_account_payments').sudo().read()[0]
        action['views'] = [(self.env.ref('account.view_account_payment_form').id, 'form')]
        context_dict = ast.literal_eval(action['context'])
        context_dict.update({'default_amount': self.deposit_amount,
                             'default_partner_id': self.partner_id.id,
                             'default_deposit_tenancy_id': self.id})
        action['context'] = str(context_dict)
        return action

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError(_('''Only 'New' Tenancy can be deleted !'''))
        return super(Tenancy, self).unlink()
    

    name = fields.Char(string='Number')
    date = fields.Date(string='Date', default=date.today())
    confirmation_date = fields.Date(string='Confirmation Date', tracking=1, copy=False)
    partner_id = fields.Many2one('res.partner', string='Tenant', tracking=1, ondelete='cascade')
    agent_partner_id = fields.Many2one('res.partner', string='Agent', tracking=1, domain=[('is_agent', '=', True)])
    commission_amount = fields.Float(string='Commission')
    commission_type = fields.Selection(string='Commission Type',
                                       selection=[('fix', 'Fixed Amount'),
                                                  ('percentage', 'Percentage of Monthly Rent'),],
                                       default='fix', tracking=1)
    commission_payment_id = fields.Many2one('account.payment', string='Commission Payment', copy=False)
    deposit_payment_id = fields.Many2one('account.payment', string='Deposit Payment', copy=False)
    property_id = fields.Many2one('property.property', string='Property', tracking=1, required=1, ondelete='cascade')
    owner_partner_id = fields.Many2one('res.partner', string='Property Owner', related='property_id.owner_partner_id')
    state = fields.Selection(string='Status', selection=[('draft', 'New'),
                                                         ('confirm', 'Confirm'),
                                                         ('running', 'Running'),
                                                         ('closed', 'Closed'),
                                                         ('cancelled', 'Cancelled')],
                             default='draft', copy=False, tracking=1)
    property_type = fields.Selection(string='Property Type',
                                     selection=[('residential', 'Residential'),
                                                ('commercial', 'Commercial'),
                                                ('industrial', 'Industrial'),
                                                ('land', 'Land')], default='residential',
                                     required=True, tracking=1)
    rent_amount = fields.Float(string='Monthly Rent', tracking=1)
    deposit_amount = fields.Float(string='Security Deposit', tracking=1)
    description = fields.Text(string='Description')
    rent_type_id = fields.Many2one('rent.type', string='Rent Type')
    start_date = fields.Date(string='Start Date', required=True, default=date.today)
    end_date = fields.Date(string='End Date', compute='_compute_end_date')
    duration = fields.Integer(string='Duration', default=11, tracking=1)
    interval_type = fields.Selection([('months', 'Months'),
                                      ('years', 'Years')], string='Interval Type',
                                     default='months', required=True, tracking=1)
    rent_schedule_ids = fields.One2many('rent.schedule', 'tenancy_id', string='Rent Schedule')
    agreement_ids = fields.One2many('property.agreement', 'tenancy_id', string='Agreements')
    maintenance_ids = fields.One2many('tenancy.maintenance', 'tenancy_id', string='Maintenance')
    agreement_count = fields.Integer(string='Agreement Counter', compute='_compute_agreement_count')
    invoice_ids = fields.One2many('account.move', 'tenancy_id', string='Invoices')
    invoice_count = fields.Integer(string='Invoice Counter', compute='_compute_invoice_count')
    maintenance_count = fields.Integer(string='Maintenance Counter', compute='_compute_maintenance_count')
    
    # maintenance
    deposit_refunded = fields.Boolean(string='')
    rent_agent_id=fields.Many2one('res.partner',string="Agent",domain=[('is_agent','=',True)])
    lead_id=fields.Many2one('crm.lead',string='Lead')
    
    @api.onchange('rent_type_id')
    def onchange_rent_type(self):
        print ("self===============",self.rent_type_id)
        self.duration = self.rent_type_id and self.rent_type_id.duration
        self.interval_type  = 'months'
        if self.rent_type_id.interval == 'yearly':
            self.interval_type = 'years'

    @api.onchange('rent_agent_id')
    def onchange_loan_agent_id(self):
        if self.rent_agent_id.blacklisted == True:
             warning_mess1 = {
                            'title': _("Warning") ,
                            'message': _("This Agent is blacklisted For This Reason - %s !!") % (self.rent_agent_id.blacklisted_reason)
                            }
             return {'warning': warning_mess1}
    
    

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
