# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import tools
from odoo import api, fields, models


class TenancyAnalysis(models.Model):
    _name = "tenancy.analysis"
    _description = "Tenancy Analysis Report"
    _auto = False

    name = fields.Char(string='Number')
    date = fields.Date(string='Date')
    confirmation_date = fields.Date(string='Confirmation Date', tracking=1, copy=False)
    partner_id = fields.Many2one('res.partner', string='Tenant', tracking=1, required=1, ondelete='cascade')
    agent_partner_id = fields.Many2one('res.partner', string='Agent', tracking=1, domain=[('is_agent', '=', True)])
    commission_amount = fields.Float(string='Commission')
    commission_type = fields.Selection(string='Commission Type',
                                       selection=[('fix', 'Fixed Amount'),
                                                  ('percentage', 'Percentage of Monthly Rent'), ],
                                       default='fix', tracking=1)
    commission_payment_id = fields.Many2one('account.payment', string='Commission Payment', copy=False)
    deposit_payment_id = fields.Many2one('account.payment', string='Deposit Payment', copy=False)
    property_id = fields.Many2one('property.property', string='Property', tracking=1, required=1, ondelete='cascade')
    state = fields.Selection(string='Status', selection=[('draft', 'New'),
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
    rent_type_id = fields.Many2one('rent.type', string='Rent Type', required=True)

    def _select(self):
        select_str = """ SELECT
                    min(pt.id) as id,
                    pt.name,
                    pt.date,
                    pt.confirmation_date,
                    pt.partner_id,
                    pt.agent_partner_id,
                    pt.commission_amount,
                    pt.commission_type,
                    pt.commission_payment_id,
                    pt.deposit_payment_id,
                    pt.property_id,
                    pt.state,
                    pt.property_type,
                    pt.rent_amount,
                    pt.deposit_amount,
                    pt.rent_type_id
        """
        return select_str

    def _from(self):
        from_str = """ property_tenancy pt join res_partner tenant on (pt.partner_id = tenant.id)"""
        return from_str

    def _group_by(self):
        group_by_str = """ GROUP BY
                    pt.name,
                    pt.date,
                    pt.confirmation_date,
                    pt.partner_id,
                    pt.agent_partner_id,
                    pt.commission_amount,
                    pt.commission_type,
                    pt.commission_payment_id,
                    pt.deposit_payment_id,
                    pt.property_id,
                    pt.state,
                    pt.property_type,
                    pt.rent_amount,
                    pt.deposit_amount,
                    pt.rent_type_id
        """
        return group_by_str

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""CREATE or REPLACE VIEW %s as (
            %s
            FROM ( %s ) %s
            )""" % (self._table, self._select(), self._from(), self._group_by()))

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
