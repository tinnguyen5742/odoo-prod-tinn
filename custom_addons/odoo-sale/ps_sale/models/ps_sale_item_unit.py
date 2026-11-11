# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from .acumatica_api import SaleAcumaticaAPI

_logger = logging.getLogger(__name__)


class PsSaleItemUnit(models.Model):
    _name = 'ps.sale.item.unit'
    _description = 'Acumatica Item Unit'
    _order = 'name'

    name = fields.Char(string='Unit', required=True, index=True)
    to_unit = fields.Char(string='To Unit')
    unit_mult_div = fields.Char(string='Mult/Div')
    unit_rate = fields.Float(string='Unit Rate', default=1.0)
    price_adjustment_multiplier = fields.Float(string='Price Adjustment Multiplier', default=1.0)
    active = fields.Boolean(string='Active', default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'Item Unit name must be unique.',
    )

    # Đồng bộ danh sách Đơn vị tính từ Acumatica API vào Odoo
    @api.model
    def sync_from_acumatica(self):
        api_client = SaleAcumaticaAPI(self.env)
        try:
            payload = api_client.get_item_units(limit=1000)
        except UserError:
            raise
        except Exception as e:
            _logger.error('Error calling Acumatica ItemUnit API: %s', e)
            raise UserError(_('Failed to connect or sync Item Units from Acumatica: %s') % str(e))

        items = (payload or {}).get('Data') or []
        if not items:
            return {'created': 0, 'updated': 0, 'total': 0}

        existing_map = {rec.name: rec for rec in self.search([])}
        to_create = []
        created_count = 0
        updated_count = 0

        seen_units = set()
        for item in items:
            from_unit = (item.get('FromUnit') or '').strip().upper()
            if not from_unit or from_unit in seen_units:
                continue
            seen_units.add(from_unit)

            to_unit = (item.get('ToUnit') or from_unit).strip().upper()
            mult_div = (item.get('UnitMultDiv') or 'M').strip()
            unit_rate = float(item.get('UnitRate') or 1.0)
            price_adj = float(item.get('PriceAdjustmentMultiplier') or 1.0)

            vals = {
                'to_unit': to_unit,
                'unit_mult_div': mult_div,
                'unit_rate': unit_rate,
                'price_adjustment_multiplier': price_adj,
                'active': True,
            }

            if from_unit in existing_map:
                existing_map[from_unit].write(vals)
                updated_count += 1
            else:
                vals['name'] = from_unit
                to_create.append(vals)

        if to_create:
            self.create(to_create)
            created_count = len(to_create)

        _logger.info('ItemUnit sync completed: %s created, %s updated', created_count, updated_count)
        return {
            'created': created_count,
            'updated': updated_count,
            'total': len(seen_units),
        }

    # Action gọi đồng bộ ĐVT từ nút bấm trên giao diện
    def action_sync_from_acumatica(self):
        res = self.sync_from_acumatica()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync Successful'),
                'message': _('Synced %s item units from Acumatica (%s new, %s updated).') % (
                    res['total'], res['created'], res['updated']
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
