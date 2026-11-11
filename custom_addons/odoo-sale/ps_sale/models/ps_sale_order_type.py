# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from .acumatica_api import SaleAcumaticaAPI

_logger = logging.getLogger(__name__)


class PsSaleOrderType(models.Model):
    _name = 'ps.sale.order.type'
    _description = 'Acumatica SO Order Type'
    _order = 'code'

    code = fields.Char(string='Order Type', required=True, index=True)
    name = fields.Char(string='Description', required=True)
    template = fields.Char(string='Template')
    behavior = fields.Char(string='Behavior')
    active = fields.Boolean(string='Active', default=True)

    _code_uniq = models.Constraint(
        'unique(code)',
        'Order Type code must be unique.',
    )

    # Hiển thị tên Loại SO kèm mã code
    def _compute_display_name(self):
        for rec in self:
            if rec.name and rec.name != rec.code:
                rec.display_name = f"[{rec.code}] {rec.name}"
            else:
                rec.display_name = rec.code or ''

    # Đồng bộ danh sách Loại SO từ Acumatica API vào Odoo
    @api.model
    def sync_from_acumatica(self):
        api_client = SaleAcumaticaAPI(self.env)
        try:
            payload = api_client.get_so_order_types()
        except UserError:
            raise
        except Exception as e:
            _logger.error('Error calling Acumatica SOOrderType API: %s', e)
            raise UserError(_('Failed to connect or sync from Acumatica: %s') % str(e))

        items = (payload or {}).get('Data') or []
        if not items:
            return {'created': 0, 'updated': 0, 'total': 0}

        existing_map = {rec.code: rec for rec in self.search([])}
        to_create = []
        created_count = 0
        updated_count = 0

        for item in items:
            order_type = (item.get('OrderType') or '').strip().upper()
            if not order_type:
                continue
            descr = (item.get('Descr') or order_type).strip()
            template = (item.get('Template') or '').strip()
            behavior = (item.get('Behavior') or '').strip()

            vals = {
                'name': descr,
                'template': template,
                'behavior': behavior,
                'active': True,
            }

            if order_type in existing_map:
                existing_map[order_type].write(vals)
                updated_count += 1
            else:
                vals['code'] = order_type
                to_create.append(vals)

        if to_create:
            self.create(to_create)
            created_count = len(to_create)

        _logger.info('SOOrderType sync completed: %s created, %s updated', created_count, updated_count)
        return {
            'created': created_count,
            'updated': updated_count,
            'total': len(items),
        }

    # Action gọi đồng bộ Loại SO từ nút bấm trên giao diện
    def action_sync_from_acumatica(self):
        res = self.sync_from_acumatica()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync Successful'),
                'message': _('Synced %s order types from Acumatica (%s new, %s updated).') % (
                    res['total'], res['created'], res['updated']
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
