# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import api, models


class TenancyReport(models.AbstractModel):
    _name = 'report.dev_property_management.tenancy_pdf_template'

    def get_duration(self, tenancy_id):
        interval_type = dict(tenancy_id._fields['interval_type'].selection).get(tenancy_id.interval_type)
        print('interval_type==================',interval_type)
        duration = str(tenancy_id.duration) + ' ' + str(interval_type)
        print("duration=================================",duration)
        return duration

    def _get_report_values(self, docids, data=None):
        docs = self.env['property.tenancy'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'property.tenancy',
            'get_duration': self.get_duration,
            'docs': docs,
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: