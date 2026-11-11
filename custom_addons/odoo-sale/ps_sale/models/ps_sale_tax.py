# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from .acumatica_api import SaleAcumaticaAPI

_logger = logging.getLogger(__name__)


class PsSaleTax(models.Model):
    _name = 'ps.sale.tax'
    _description = 'Acumatica Tax'
    _order = 'tax_id'

    tax_id = fields.Char(string='Tax ID', required=True, index=True)
    name = fields.Char(string='Tax Description', required=True, index=True)
    tax_type = fields.Char(string='Tax Type')
    tax_rate = fields.Float(string='Tax Rate (%)')
    start_date = fields.Datetime(string='Start Date')
    end_date = fields.Datetime(string='End Date')
    active = fields.Boolean(string='Active', default=True)

    _tax_id_uniq = models.Constraint(
        'unique(tax_id)',
        'Tax ID must be unique.',
    )

    # Hiển thị tên Thuế kèm mã code và thuế suất
    def _compute_display_name(self):
        for rec in self:
            rate_str = f"{rec.tax_rate:g}%" if rec.tax_rate is not False else ""
            if rec.name and rec.name != rec.tax_id:
                rec.display_name = f"[{rec.tax_id}] {rec.name} ({rate_str})" if rate_str else f"[{rec.tax_id}] {rec.name}"
            else:
                rec.display_name = f"[{rec.tax_id}] ({rate_str})" if rate_str else (rec.tax_id or '')

    # Đồng bộ danh sách Thuế từ Acumatica API vào Odoo
    @api.model
    def sync_from_acumatica(self):
        api_client = SaleAcumaticaAPI(self.env)
        try:
            payload = api_client.get_taxes(limit=100)
        except UserError:
            raise
        except Exception as e:
            _logger.error('Error calling Acumatica vat API: %s', e)
            raise UserError(_('Failed to connect or sync Taxes from Acumatica: %s') % str(e))

        items = (payload or {}).get('Data') or []
        if not items:
            return {'created': 0, 'updated': 0, 'total': 0}

        existing_map = {rec.tax_id: rec for rec in self.search([])}
        to_create = []
        created_count = 0
        updated_count = 0

        seen_taxes = set()
        for item in items:
            tax_id = (item.get('TaxID') or '').strip().upper()
            if not tax_id or tax_id in seen_taxes:
                continue
            seen_taxes.add(tax_id)

            descr = (item.get('Descr') or tax_id).strip()
            tax_type = (item.get('TaxType') or '').strip()
            tax_rate = float(item.get('TaxRate') or 0.0)

            vals = {
                'name': descr,
                'tax_type': tax_type,
                'tax_rate': tax_rate,
                'active': True,
            }

            if tax_id in existing_map:
                existing_map[tax_id].write(vals)
                updated_count += 1
            else:
                vals['tax_id'] = tax_id
                to_create.append(vals)

        if to_create:
            self.create(to_create)
            created_count = len(to_create)

        _logger.info('Tax sync completed: %s created, %s updated', created_count, updated_count)
        return {
            'created': created_count,
            'updated': updated_count,
            'total': len(seen_taxes),
        }

    # Action gọi đồng bộ Thuế từ nút bấm trên giao diện
    def action_sync_from_acumatica(self):
        res = self.sync_from_acumatica()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync Successful'),
                'message': _('Synced %s taxes from Acumatica (%s new, %s updated).') % (
                    res['total'], res['created'], res['updated']
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
