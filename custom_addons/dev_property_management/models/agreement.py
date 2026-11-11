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
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError

class Agreement(models.Model):
    _name = 'property.agreement'
    _inherit = ['mail.thread']
    _description = 'Property Agreement'
    _order = 'id desc'

    @api.model
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].next_by_code('property.agreement') or '/'
        return super(Agreement, self).create(vals_list)

    @api.depends('duration', 'interval_type', 'agreement_date')
    def _compute_expiry_date(self):
        for agreement in self:
            expiry_date = False
            if agreement.interval_type == 'months':
                expiry_date = agreement.agreement_date + relativedelta(months=+agreement.duration)
            else:
                expiry_date = agreement.agreement_date + relativedelta(years=+agreement.duration)
            agreement.expiry_date = expiry_date
            
    @api.depends('duration', 'interval_type', 'agreement_date')
    def _compute_expiry_days(self):
        for agreement in self:
            expiry_date = False
            if agreement.interval_type == 'months':
                expiry_date = agreement.agreement_date + relativedelta(months=+agreement.duration)
            else:
                expiry_date = agreement.agreement_date + relativedelta(years=+agreement.duration)
            days = (expiry_date - date.today()).days
            agreement.expiry_day = days if days > 0 else 0
            
        

    def confirm_agreement(self):
        agreement_id = self.env[self._name].search([('id', '!=', self.id),
                                                    ('partner_id', '=', self.partner_id.id),
                                                    ('property_id', '=', self.property_id.id),
                                                    ('state', '=', 'running')], limit=1)
        if agreement_id:
            agreement_date = datetime.strptime(str(agreement_id.agreement_date), "%Y-%m-%d").strftime('%d-%m-%Y')
            expiry_date = datetime.strptime(str(agreement_id.expiry_date), "%Y-%m-%d").strftime('%d-%m-%Y')
            raise ValidationError(_('''Agreement '%s' is already running\n\nTenant : %s \nProperty : %s\nAgreement Date : %s\nExpiry Date : %s''')
                                  % (agreement_id.name, agreement_id.partner_id.name, agreement_id.property_id.name, agreement_date, expiry_date))
        self.state = 'running'

    def cancel_agreement(self):
        self.state = 'cancelled'

    def set_to_draft(self):
        self.state = 'draft'
        
    def expire_agreement(self):
        self.state='expired'

    @api.onchange('agreement_template_id')
    def onchange_agreement_template_id(self):
        self.description = self.agreement_template_id and self.agreement_template_id.description or ''

    def agreement_url(self):
        ir_param = self.env['ir.config_parameter'].sudo()
        base_url = ir_param.get_param('web.base.url')
        action_id = self.env.ref('dev_property_management.action_property_agreement').id
        menu_id = self.env.ref('dev_property_management.root_menu_property').id
        if base_url:
            base_url += '/web#id=%s&action=%s&model=%s&view_type=form&cids=&menu_id=%s' % (int(self.id), action_id, self._name, menu_id)
        return base_url

    def agreement_expiry_and_reminder(self):
        agreement_ids = self.env[self._name].search([('state', '=', 'running'), ('type', '=', 'rent')])
        if agreement_ids:
            for agreement_id in agreement_ids:
                if agreement_id.expiry_date == date.today():
                    agreement_id.state = 'expired'
        if self.env.company.send_aggr_exp_email:
            template_id = self.env.ref('dev_property_management.template_property_agreement_before_days')
            if template_id:
                before_days = self.env.company and self.env.company.aggr_exp_reminder_days
                if before_days > 0:
                    expiry_date = date.today() + timedelta(days=int(before_days))
                    agreement_ids = self.env['property.agreement'].search([('state', '=', 'running'),
                                                                           ('expiry_date', '=', expiry_date)])
                    if agreement_ids:
                        for agreement_id in agreement_ids:
                            template_id.send_mail(agreement_id.id, force_send=True)
            if self.env.company.send_aggr_exp_mail_same_day:
                template_id = self.env.ref('dev_property_management.template_property_agreement_same_day')
                if template_id:
                    agreement_ids = self.env['property.agreement'].search([('state', '=', 'expired'),
                                                                           ('expiry_date', '=', date.today())])
                    if agreement_ids:
                        for agreement_id in agreement_ids:
                            template_id.send_mail(agreement_id.id, force_send=True)

    def get_expiry_date(self):
        expiry_date = datetime.strptime(str(self.expiry_date), "%Y-%m-%d").strftime('%d-%m-%Y')
        return expiry_date

    def get_agreement_date(self):
        agreement_date = datetime.strptime(str(self.agreement_date), "%Y-%m-%d").strftime('%d-%m-%Y')
        return agreement_date

    def send_by_mail(self):
        self.ensure_one()
        template_id = self.env.ref('dev_property_management.template_property_agreement_send_by_mail')
        ctx = {
            'default_model': 'property.agreement',
            'default_res_ids': self.ids,
            # 'default_use_template': bool(template_id),
            'default_use_template': bool(template_id and template_id.id ),
            'default_template_id': template_id and template_id.id or False,
            'default_composition_mode': 'comment',
            'force_email': True,
        }
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }

    def view_renewed_agreement(self):
        action = self.env.ref('dev_property_management.action_property_agreement').sudo().read()[0]
        action['views'] = [(self.env.ref('dev_property_management.form_property_agreement').id, 'form')]
        action.update({'res_id': self.renew_agreement_id.id})
        return action

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError(_('''Only 'Draft' Agreement can be deleted !'''))
        return super(Agreement, self).unlink()

    def _compute_document_count(self):
        for rec in self:
            counter = 0
            document_ids = rec.env['ir.attachment'].search([('res_id', '=', rec.id), ('res_model', '=', rec._name)])
            if document_ids:
                counter = len(document_ids)
            rec.document_count = counter

    def view_documents(self):
        action = self.env["ir.actions.actions"]._for_xml_id("dev_property_management.action_property_agreement_documents")
        document_ids = self.env['ir.attachment'].search([('res_id', '=', self.id), ('res_model', '=', self._name)])
        if len(document_ids) > 1:
            action['domain'] = [('id', 'in', document_ids.ids)]
        elif len(document_ids) == 1:
            action['views'] = [(self.env.ref('dev_property_management.form_property_agreement_documents').id, 'form')]
            action['res_id'] = document_ids.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    name = fields.Char(string='Number')
    tenancy_id = fields.Many2one('property.tenancy', string='Tenancy', copy=False, ondelete='cascade') # link
    booking_id = fields.Many2one('property.booking', string='Booking', copy=False, ondelete='cascade') # link
    partner_id = fields.Many2one('res.partner', string='Tenant', tracking=1, required=1)
    property_id = fields.Many2one('property.property', string='Property', tracking=1, required=1)
    agreement_date = fields.Date(string='Agreement Date', default=date.today(), required=True, tracking=1)
    expiry_date = fields.Date(string='Expiry Date', compute='_compute_expiry_date')
    owner_partner_id = fields.Many2one('res.partner', string='Property Owner',
                                       related='property_id.owner_partner_id', tracking=1)
    state = fields.Selection(string='Status', selection=[('draft', 'Draft'),
                                                         ('running', 'Running'),
                                                         ('cancelled', 'Cancelled'),
                                                         ('expired', 'Expired'),],
                             default='draft', copy=False, tracking=1)
    type = fields.Selection(string='Agreement Type', selection=[('rent', 'Rent'),

                                                                ('sell', 'Sell')])
    rent_amount = fields.Float(related='property_id.rent_amount',string='Monthly Rent', tracking=1)
    duration = fields.Integer(string='Duration', default=11, tracking=1)
    interval_type = fields.Selection([('months', 'Months'),
                                      ('years', 'Years')], string='Interval Type',
                                     default='months', required=True, tracking=1)
    description = fields.Html( string='Description')
    agreement_template_id = fields.Many2one('agreement.template', string='Agreement Template')
    renew_agreement_id = fields.Many2one('property.agreement', string='Agreement', copy=False)
    document_count = fields.Integer(string='Document Counter', compute='_compute_document_count')
    
    expiry_day=fields.Integer(string='Expiry Days', compute='_compute_expiry_days')
    

    agreement_signature = fields.Binary(string='Signature',copy=False)
    agreement_signed_by = fields.Char(string='Signed By',copy=False)
    agreement_signed_on = fields.Datetime(string='Signed On',copy=False)
    

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
