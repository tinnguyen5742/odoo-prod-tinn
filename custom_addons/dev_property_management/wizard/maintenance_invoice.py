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
from odoo.exceptions import ValidationError
from datetime import datetime,date
from odoo.exceptions import RedirectWarning
import base64

class AddMaintenance(models.TransientModel):
    _name = 'maintenance.invoice'
    _description = 'Maintenance Invoice'

    def default_get(self, fields):
        defaults = super(AddMaintenance, self).default_get(fields)
        active_ids = self._context.get('active_ids')
        if active_ids:
            records = self.env['property.tenancy'].browse(active_ids)
            maintenance_lines = []
            for record in records:
                for maintenance_line in record.maintenance_ids:
                    maintenance_lines.append((0, 0, {
                        'maintenance_type_id': maintenance_line.maintenance_type_id.id,
                        'maintenance_amount': maintenance_line.maintenance_amount,
                    }))
            defaults['maintenance_ids'] = maintenance_lines
        return defaults
    
    
    def load_maintenance(self):
        maintenance_to_invoice = self.maintenance_ids.filtered(lambda r: r.check_invoice)
        active_ids = self._context.get('active_ids')
        records = self.env['property.tenancy'].browse(active_ids)
        
        # for maintenance_line in maintenance_to_invoice:
            
        if not maintenance_to_invoice:
            raise ValidationError(_('''Please select Maintenance details !'''))
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
        
        desc = []
        for line in maintenance_to_invoice:
            desc.append(f"{line.maintenance_type_id.name}: {line.maintenance_amount}")

        description = ', '.join(desc)
        amount = sum(line.maintenance_amount for line in maintenance_to_invoice)
    
        vals = {'move_type': 'out_invoice',
                    'partner_id': records.partner_id and records.partner_id.id or False,
                    'tenancy_id': records.id,
                    'property_id':records.property_id and records.property_id.id or False,
                    'invoice_date': date.today(),
                    'is_maintenance_invoice': True,
                    'invoice_line_ids': [(0, 0, {'name': description,
                                                 'product_id': product_id.id,
                                                 'account_id': account_id.id,
                                                 'price_unit': amount,
                                                 'quantity': 1.0,
                                                 'product_uom_id': product_id.uom_id and product_id.uom_id.id or False
                                                 })
                                         ]}
        
        self.env['account.move'].create(vals)
           
        
        
        
    maintenance_ids = fields.One2many('maintenance.invoice.line', 'maintenance_invoice_id', string="Maintenance Details")

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: