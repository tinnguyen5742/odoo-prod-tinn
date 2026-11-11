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
from odoo.exceptions import ValidationError,RedirectWarning
from datetime import datetime, date

class AgentCommission(models.Model):
    _name = "agent.commission"
    _description = "Agent Comission"
    
    name = fields.Char('Name', default='/', copy=False)
    agent_partner_id=fields.Many2one('res.partner','Agent',domain=[('is_agent','=',True)])
    rent_id=fields.Many2one('property.tenancy',string='Rent Tenancy') 
    sell_id=fields.Many2one('property.booking', string="Sell Property")
    
    property_type = fields.Selection([('rent','Rent'),
                              ('sell','Sell')], string='Property Type')
    
    amount = fields.Monetary(string='Property Price',compute='_compute_amount', store=True , required="1")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self:self.env.user.company_id.id)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self:self.env.user.company_id.currency_id.id)
    description=fields.Html('Description')   
    color=fields.Integer('Color')
    state = fields.Selection([('draft','Draft'),
                              ('done','Done')], string='State', required="1", default='draft')
    bill_count = fields.Integer('Bill Count', compute='_compute_bill_count')
    commission_type = fields.Selection(string="Commission Type",selection=[('fixed','Fixed'),('percentage','Percentage')],default='fixed')
    commission_fixed_amount = fields.Monetary('Fixed Amount')
    commission_percentage = fields.Float('Percentage')
    percentage_amount = fields.Monetary('Percentage Amount',compute="compute_percentage_amount")

    @api.constrains('rent_id', 'sell_id')
    def _check_only_one_selected(self):
        for record in self:
            if record.rent_id and record.sell_id:
                raise ValidationError(
                    _("You can only select either a Rent Property or a Sell Property, not both.")
                )
    
    
    @api.depends('commission_percentage','amount')
    def compute_percentage_amount(self):
        for commission in self:
            if commission.commission_percentage:
                commission.percentage_amount = (commission.amount * commission.commission_percentage / 100)
            else:
                commission.percentage_amount = 0
                              
    
    def action_view_bill(self):
        bill_id = self.env['account.move'].search([('agent_commission_id', '=', self.id),('move_type','=','in_invoice')])
        bill_ids = bill_id.ids
        action = self.env.ref('account.action_move_in_invoice_type').read()[0]
        if len(bill_ids) > 1:
            action['domain'] = [('id', 'in', bill_ids)]
        elif len(bill_ids) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = bill_ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action  
        
    def _compute_bill_count(self):
        for bill in self:
            bill_ids = self.env['account.move'].search([('agent_commission_id', '=', self.id),('move_type','=','in_invoice')])
            bill.bill_count = len(bill_ids)
    
    def action_draft(self):
        self.state = 'draft'
     
    def action_done(self):
        self.state = 'done'  
        
    @api.model
    def create(self,vals_list):
        for vals in vals_list:
            vals.update({
                        'name':self.env['ir.sequence'].next_by_code('agent.commission') or _('/')
                    })
        return super(AgentCommission,self).create(vals_list)
    
    # @api.onchange('rent_id','sell_id')
    # def onchange_property_id(self):
    #     if self.rent_id == 'rent':
    #         self.amount = self.rent_id and self.rent_id.rent_amount or False
    #     else:
    #         self.amount = self.sell_id and self.sell_id.price_amount or False
    @api.depends('rent_id', 'sell_id')
    def _compute_amount(self):
        for record in self:
            if record.rent_id:
                record.amount = record.rent_id.rent_amount or 0.0
            elif record.sell_id:
                record.amount = record.sell_id.price_amount or 0.0
            else:
                record.amount = 0.0
            
    def get_account(self, product_id):
        account_id = False
        if product_id:
            account_id = product_id.property_account_income_id or False
        if not account_id:
            account_id = product_id.categ_id and product_id.categ_id.property_account_income_categ_id or False
        return account_id
        
        
    def create_agent_commission_bill(self):
        if self.commission_type == 'fixed':
            if self.commission_fixed_amount <= 0:
                raise ValidationError(_('''Commission Amount is Zero or Less Then Zero, Bill can't be generated !'''))
            configure_action = self.env.ref('dev_property_management.action_config_dev_property_management')
            if not self.company_id.agent_commission_product_id:
                msg = _('Configure Agent Commission Product into the Loan Type !')
                raise RedirectWarning(msg, configure_action.id, _('Go to the page'))
                
            agent_commission_product_id = self.company_id and self.company_id.agent_commission_product_id or False
            invoice_lines = []
            if self.company_id.agent_commission_product_id:
                account_id = self.get_account(agent_commission_product_id)
                if not account_id:
                    raise ValidationError(_('''There is no income account defined for the product '%s' ''') % (
                        agent_commission_product_id.name))
                line_vals = {'product_id': agent_commission_product_id.id,
                             'name': self.name + ' : ' + 'Agent Commission',
                             'account_id': account_id.id,
                             'price_unit': self.commission_fixed_amount,
                             'quantity': 1,
                             'product_uom_id': agent_commission_product_id.uom_id and agent_commission_product_id.uom_id.id or False
                             }
                invoice_lines.append((0, 0, line_vals))
               
            vals = {'move_type': 'in_invoice',
                    'partner_id': self.agent_partner_id and self.agent_partner_id.id or False,
                    'agent_commission_id': self.id,
                    'invoice_date': date.today(),
                    'invoice_line_ids': invoice_lines}
            self.env['account.move'].create(vals)
            
        if self.commission_type == 'percentage':
            if self.commission_percentage <= 0:
                raise ValidationError(_('''Commission Percentage is Zero or Less Then Zero, Bill can't be generated !'''))
            configure_action = self.env.ref('dev_property_management.action_config_dev_property_management')
            if not self.company_id.agent_commission_product_id:
                msg = _('Configure Agent Commission Product into the Loan Type !')
                raise RedirectWarning(msg, configure_action.id, _('Go to the Loan Type page'))
                
            agent_commission_product_id = self.company_id and self.company_id.agent_commission_product_id or False
            invoice_lines = []
            if self.company_id.agent_commission_product_id:
                account_id = self.get_account(agent_commission_product_id)
                if not account_id:
                    raise ValidationError(_('''There is no income account defined for the product '%s' ''') % (
                        agent_commission_product_id.name))
                amount = 0
                if self.commission_percentage:
                    amount = (self.amount * self.commission_percentage / 100)
                line_vals = {'product_id': agent_commission_product_id.id,
                             'name': self.name + ' : ' + 'Agent Commission',
                             'account_id': account_id.id,
                             'price_unit': amount,
                             'quantity': 1,
                             'product_uom_id': agent_commission_product_id.uom_id and agent_commission_product_id.uom_id.id or False
                             }
                invoice_lines.append((0, 0, line_vals))
               
            vals = {'move_type': 'in_invoice',
                    'partner_id': self.agent_partner_id and self.agent_partner_id.id or False,
                    'agent_commission_id': self.id,
                    'invoice_date': date.today(),
                    'invoice_line_ids': invoice_lines}
            self.env['account.move'].create(vals)
        
            
       
            
  
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
