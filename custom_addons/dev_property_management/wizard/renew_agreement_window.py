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
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError

class RenewAgreementWindow(models.TransientModel):
    _name = 'renew.agreement.window'
    _description = 'Re-New Agreement Window'

    def renew_agreement(self):
        if self.agreement_id.renew_agreement_id:
            raise ValidationError(_(''''%s' agreement is already renewed from '%s' agreement''') %
                                  (self.agreement_id.renew_agreement_id.name, self.agreement_id.name))
        if self.agreement_date <= self.old_expiry_date:
            expiry_date = datetime.strptime(str(self.old_expiry_date), "%Y-%m-%d").strftime('%d-%m-%Y')
            raise ValidationError(_('''Agreement Date must be greater than '%s' ''') % (expiry_date))
        vals = {'partner_id': self.agreement_id and self.agreement_id.partner_id and self.agreement_id.partner_id.id or False,
                'property_id': self.agreement_id and self.agreement_id.property_id and self.agreement_id.property_id.id or False,
                'owner_partner_id': self.agreement_id and self.agreement_id.owner_partner_id and self.agreement_id.owner_partner_id.id or False,
                'agreement_date': self.agreement_date,
                'rent_amount': self.agreement_id and self.agreement_id.rent_amount or 0,
                'duration': self.duration,
                'type': self.agreement_id and self.agreement_id.type or False,
                'interval_type': self.interval_type,
                'description': self.agreement_id and self.agreement_id.description or '',
                'booking_id': self.agreement_id and self.agreement_id.booking_id and self.agreement_id.booking_id.id or False,
                'tenancy_id': self.agreement_id and self.agreement_id.tenancy_id and self.agreement_id.tenancy_id.id or False,
                'agreement_template_id': self.agreement_id and self.agreement_id.agreement_template_id and self.agreement_id.agreement_template_id.id or False,
                }
        agreement_id = self.env['property.agreement'].sudo().create(vals)
        self.agreement_id.renew_agreement_id = agreement_id.id
        action = self.env.ref('dev_property_management.action_property_agreement').sudo().read()[0]
        action['views'] = [(self.env.ref('dev_property_management.form_property_agreement').id, 'form')]
        action.update({'res_id': agreement_id.id})
        return action

    @api.depends('duration', 'interval_type', 'agreement_date')
    def _compute_expiry_date(self):
        for agreement in self:
            expiry_date = False
            if agreement.interval_type == 'months':
                expiry_date = agreement.agreement_date + relativedelta(months=+agreement.duration)
            else:
                expiry_date = agreement.agreement_date + relativedelta(years=+agreement.duration)
            agreement.expiry_date = expiry_date

    agreement_id = fields.Many2one('property.agreement', string='Agreement')
    agreement_date = fields.Date(string='Agreement Date', default=date.today(), required=True)
    expiry_date = fields.Date(string='Expiry Date', compute='_compute_expiry_date')
    duration = fields.Integer(string='Duration', default=11, tracking=1)
    interval_type = fields.Selection([('months', 'Months'),
                                      ('years', 'Years')], string='Interval Type',
                                     default='months', required=True, tracking=1)
    old_expiry_date = fields.Date(string='Expired On', related='agreement_id.expiry_date')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: