# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from .acumatica_api import SaleAcumaticaAPI

_logger = logging.getLogger(__name__)


class PsSaleInventory(models.Model):
    _name = 'ps.sale.inventory'
    _description = 'Acumatica Inventory'
    _order = 'inventory_cd'

    inventory_id = fields.Integer(string='Inventory ID', index=True)
    inventory_cd = fields.Char(string='Inventory Code', required=True, index=True)
    name = fields.Char(string='Inventory Name', required=True, index=True)
    item_type = fields.Char(string='Item Type')
    item_status = fields.Char(string='Item Status')
    base_unit = fields.Char(string='Base Unit')
    sales_unit = fields.Char(string='Sales Unit')
    base_price = fields.Float(string='Base Price')
    active = fields.Boolean(string='Active', default=True)

    _inventory_cd_uniq = models.Constraint(
        'unique(inventory_cd)',
        'Inventory Code must be unique.',
    )

    # Hiển thị tên Vật tư kèm mã code
    def _compute_display_name(self):
        for rec in self:
            if rec.name and rec.name != rec.inventory_cd:
                rec.display_name = f"[{rec.inventory_cd}] {rec.name}"
            else:
                rec.display_name = rec.inventory_cd or ''

    # Đồng bộ danh sách Vật tư từ Acumatica API vào Odoo
    @api.model
    def sync_from_acumatica(self):
        api_client = SaleAcumaticaAPI(self.env)
        try:
            payload = api_client.get_inventories(limit=1000)
        except UserError:
            raise
        except Exception as e:
            _logger.error('Error calling Acumatica inventories API: %s', e)
            raise UserError(_('Failed to connect or sync inventories from Acumatica: %s') % str(e))

        items = (payload or {}).get('Data') or []
        if not items:
            return {'created': 0, 'updated': 0, 'total': 0}

        existing_map = {rec.inventory_cd: rec for rec in self.search([])}
        to_create = []
        created_count = 0
        updated_count = 0

        for item in items:
            inventory_cd = (item.get('InventoryCD') or '').strip()
            if not inventory_cd:
                continue
            descr = (item.get('Descr') or inventory_cd).strip()
            inv_id = item.get('InventoryID') or 0
            item_type = (item.get('ItemType') or '').strip()
            item_status = (item.get('ItemStatus') or '').strip()
            base_unit = (item.get('BaseUnit') or '').strip()
            sales_unit = (item.get('SalesUnit') or '').strip()
            base_price = float(item.get('BasePrice') or 0.0)

            vals = {
                'inventory_id': inv_id,
                'name': descr,
                'item_type': item_type,
                'item_status': item_status,
                'base_unit': base_unit,
                'sales_unit': sales_unit,
                'base_price': base_price,
                'active': True,
            }

            if inventory_cd in existing_map:
                existing_map[inventory_cd].write(vals)
                updated_count += 1
            else:
                vals['inventory_cd'] = inventory_cd
                to_create.append(vals)

        if to_create:
            self.create(to_create)
            created_count = len(to_create)

        _logger.info('Inventories sync completed: %s created, %s updated', created_count, updated_count)
        return {
            'created': created_count,
            'updated': updated_count,
            'total': len(items),
        }

    # Action gọi đồng bộ Vật tư từ nút bấm trên giao diện
    def action_sync_from_acumatica(self):
        res = self.sync_from_acumatica()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync Successful'),
                'message': _('Synced %s inventories from Acumatica (%s new, %s updated).') % (
                    res['total'], res['created'], res['updated']
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
