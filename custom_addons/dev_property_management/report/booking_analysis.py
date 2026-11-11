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


class BookingAnalysis(models.Model):
    _name = "booking.analysis"
    _description = "Booking Analysis Report"
    _auto = False

    name = fields.Char(string='Number')
    property_type = fields.Selection(string='Property Type',
                                     selection=[('residential', 'Residential'),
                                                ('commercial', 'Commercial'),
                                                ('industrial', 'Industrial'),
                                                ('land', 'Land')],
                                     required=True, tracking=1)
    partner_id = fields.Many2one('res.partner', string='Contact', tracking=1, copy=False, required=1)
    property_id = fields.Many2one('property.property', string='Property', tracking=1, required=1, ondelete='cascade') # link
    booking_date = fields.Date(string='Booking Date', copy=False, tracking=1)
    confirmation_date = fields.Date(string='Confirmation Date', copy=False, tracking=1)
    booking_purpose = fields.Selection(string='Purpose', selection=[('rent', 'Rent'), ('buy', 'Sell')],
                                       default='rent', tracking=1, required=True)
    owner_partner_id = fields.Many2one('res.partner', string='Last Owner')
    state = fields.Selection(string='Status', selection=[('draft', 'New'),
                                                         ('confirmed', 'Confirmed'),
                                                         ('cancelled', 'Cancelled'),
                                                         ],
                             default='draft', copy=False, tracking=1)
    ask_price_amount = fields.Float(string='Ask Price', copy=False, tracking=1)
    agent_partner_id = fields.Many2one('res.partner', string='Agent', tracking=1, domain=[('is_agent', '=', True)])
    commission_amount = fields.Float(string='Commission')
    commission_type = fields.Selection(string='Commission Type',
                                       selection=[('fix', 'Fixed Amount'),
                                                  ('percentage', 'Percentage of Selling Price'),], tracking=1)
    commission_payment_id = fields.Many2one('account.payment', string='Payment', copy=False)
    create_uid = fields.Many2one('res.users', string='User')

    def _select(self):
        select_str = """ SELECT
                    min(pb.id) as id,
                    pb.name,
                    pb.property_type,
                    pb.partner_id,
                    pb.property_id,
                    pb.booking_date,
                    pb.confirmation_date,
                    pb.booking_purpose,
                    pb.owner_partner_id,
                    pb.state,
                    pb.ask_price_amount,
                    pb.agent_partner_id,
                    pb.create_uid,
                    pb.commission_amount,
                    pb.commission_type,
                    pb.commission_payment_id
        """
        return select_str

    def _from(self):
        from_str = """ property_booking pb join res_partner buyer on (pb.partner_id = buyer.id)"""
        return from_str

    def _group_by(self):
        group_by_str = """ GROUP BY
                    pb.name,
                    pb.property_type,
                    pb.partner_id,
                    pb.property_id,
                    pb.booking_date,
                    pb.confirmation_date,
                    pb.booking_purpose,
                    pb.owner_partner_id,
                    pb.state,
                    pb.ask_price_amount,
                    pb.agent_partner_id,
                    pb.create_uid,
                    pb.commission_amount,
                    pb.commission_type,
                    pb.commission_payment_id
        """
        return group_by_str

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""CREATE or REPLACE VIEW %s as (
            %s
            FROM ( %s ) %s
            )""" % (self._table, self._select(), self._from(), self._group_by()))

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
