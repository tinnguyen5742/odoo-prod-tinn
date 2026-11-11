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


class AgreementReport(models.AbstractModel):
    _name = 'report.dev_property_management.agreement_pdf_template'

    def get_duration(self, agreement_id):
        interval_type = dict(agreement_id._fields['interval_type'].selection).get(agreement_id.interval_type)
        duration = str(agreement_id.duration) + ' ' + str(interval_type)
        return duration

    def _get_report_values(self, docids, data=None):
        docs = self.env['property.agreement'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'property.agreement',
            'get_duration': self.get_duration,
            'docs': docs,
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: