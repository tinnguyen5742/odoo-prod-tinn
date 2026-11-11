# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from .acumatica_api import SaleAcumaticaAPI

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    state = fields.Selection(
        selection=[
            ('draft', "Quotation"),
            ('sent', "Quotation Sent"),
            ('sale', "Successful Quotation"),
            ('cancel', "Cancelled"),
        ],
        string="Status",
        readonly=True,
        copy=False,
        index=True,
        tracking=3,
        default='draft',
    )

    x_customer_code = fields.Char(
        string='Customer Code (Acu)',
        compute='_compute_x_customer_code',
        store=True,
        readonly=True,
        index=True,
    )

    # Tính toán mã Acumatica: lấy từ partner_id hoặc công ty mẹ (commercial_partner_id)
    @api.depends('partner_id', 'partner_id.x_customer_code', 'partner_id.commercial_partner_id.x_customer_code')
    def _compute_x_customer_code(self):
        for order in self:
            order.x_customer_code = (
                order.partner_id.x_customer_code
                or (order.partner_id.commercial_partner_id.x_customer_code if order.partner_id.commercial_partner_id else False)
                or False
            )
    x_order_type_id = fields.Many2one(
        'ps.sale.order.type',
        string='Order Type',
        tracking=True,
        ondelete='restrict',
        default=lambda self: self._default_order_type_id(),
    )
    # Các trường header dưới đây được duy trì để phục vụ lọc/tìm kiếm và tương thích dữ liệu cũ
    x_inventory_id = fields.Many2one(
        'ps.sale.inventory',
        string='Inventory (Code, Name)',
        tracking=True,
        ondelete='restrict',
    )
    x_item_unit_id = fields.Many2one(
        'ps.sale.item.unit',
        string='Item Unit',
        tracking=True,
        ondelete='restrict',
    )
    x_tax_id = fields.Many2one(
        'ps.sale.tax',
        string='Tax',
        tracking=True,
        ondelete='restrict',
    )
    x_unit_price = fields.Float(
        string='Unit Price',
        tracking=True,
    )
    x_acumatica_so_number = fields.Char(
        string='Acumatica SO Number',
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
    )
    x_acumatica_so_date = fields.Datetime(
        string='Acumatica SO Date',
        readonly=True,
        copy=False,
    )
    x_acumatica_so_status = fields.Selection(
        [
            ('not_synced', 'Not Synced'),
            ('pending', 'Pending Sync'),
            ('synced', 'Synced'),
            ('failed', 'Failed'),
        ],
        string='Acumatica Sync Status',
        default='not_synced',
        copy=False,
        tracking=True,
    )

    # Mặc định chọn loại SO là 'SO' nếu có sẵn trong hệ thống
    @api.model
    def _default_order_type_id(self):
        default_type = self.env['ps.sale.order.type'].search([('code', '=', 'SO'), ('active', '=', True)], limit=1)
        return default_type.id if default_type else False

    # Khi chọn vật tư, tự động điền ĐVT và Đơn giá (BasePrice) từ vật tư
    @api.onchange('x_inventory_id')
    def _onchange_x_inventory_id(self):
        if self.x_inventory_id:
            target_unit = (self.x_inventory_id.sales_unit or self.x_inventory_id.base_unit or '').strip()
            if target_unit:
                unit = self.env['ps.sale.item.unit'].search([('name', '=ilike', target_unit)], limit=1)
                if unit:
                    self.x_item_unit_id = unit.id
            if self.x_inventory_id.base_price:
                self.x_unit_price = self.x_inventory_id.base_price

    # Gọi API tạo khách hàng mới bên Acumatica và cập nhật mã Ref
    def action_create_acumatica_customer(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_('Please select a customer before creating on Acumatica.'))
        target_partner = self.partner_id.commercial_partner_id or self.partner_id
        if target_partner.x_customer_code:
            raise UserError(_('This customer already has an Acumatica code: %s') % target_partner.x_customer_code)

        api_client = SaleAcumaticaAPI(self.env)
        try:
            result = api_client.create_customer(target_partner)
            if isinstance(result, dict) and not result.get('Success', True):
                err_msg = result.get('Message') or str(result)
                if 'already exists' in err_msg.lower():
                    acct_cd = target_partner.x_customer_code or target_partner.ref or f"CUST{target_partner.id}"
                    customer_cd = str(acct_cd).strip()
                    target_partner.write({'x_customer_code': customer_cd})
                    self.message_post(body=_('Customer already exists on Acumatica. Automatically linked with code: <b>%s</b>') % customer_cd)
                else:
                    raise UserError(_('Acumatica returned error: %s') % err_msg)
            else:
                data = (result.get('Data') or result) if isinstance(result, dict) else {}
                customer_cd = (
                    data.get('CustomerCD')
                    or data.get('AcctCD')
                    or target_partner.x_customer_code
                    or target_partner.ref
                    or f"CUST{target_partner.id}"
                )
                customer_cd = str(customer_cd).strip()
                write_vals = {'x_customer_code': customer_cd}
                cust_id = data.get('CustomerID') or data.get('BAccountID')
                if cust_id:
                    write_vals['x_acumatica_customer_id'] = int(cust_id)
                target_partner.write(write_vals)
                self.message_post(body=_('Successfully created customer on Acumatica with code: <b>%s</b>') % customer_cd)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Created Acumatica customer: %s') % customer_cd,
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }
        except UserError:
            raise
        except Exception as e:
            _logger.error('Error creating Acumatica customer: %s', e)
            raise UserError(_('Failed to create customer on Acumatica: %s') % str(e))

    # Gọi API tạo Sales Order trực tiếp trên Acumatica (POST /api/v1/process/createSO)
    def action_create_acumatica_so(self):
        self.ensure_one()
        if self.state != 'sale':
            raise UserError(_('Quotation must be in "Successful Quotation" status to create Acumatica SO.'))
        if self.x_acumatica_so_number:
            raise UserError(_('This quotation already has an Acumatica SO: %s') % self.x_acumatica_so_number)
        if self.x_acumatica_so_status == 'pending':
            raise UserError(_('Quotation "%s" is currently being synchronized to Acumatica. Please wait for Acumatica to finish.') % self.name)
        if self.x_acumatica_so_status == 'synced':
            raise UserError(_('Quotation "%s" has already been synchronized to Acumatica.') % self.name)
        if not self.x_order_type_id:
            raise UserError(_('Please select Order Type before creating Acumatica SO.'))
        if not self.partner_id:
            raise UserError(_('Please select a customer on the quotation before creating Acumatica SO.'))

        # Lấy khách hàng pháp nhân và mã Acumatica (CustomerCD)
        commercial_partner = self.partner_id.commercial_partner_id or self.partner_id
        customer_cd = (self.partner_id.x_customer_code or commercial_partner.x_customer_code or '').strip()
        acumatica_cust_id = (
            getattr(commercial_partner, 'x_acumatica_customer_id', 0)
            or getattr(self.partner_id, 'x_acumatica_customer_id', 0)
        )

        # Nếu khách hàng chưa có mã Acumatica HOẶC chưa có CustomerID: tự động gọi API tạo khách hàng trước
        if not customer_cd or not acumatica_cust_id:
            _logger.info("Khách hàng '%s' (CD: %s, ID: %s) chưa đủ thông tin Acumatica, gọi API tạo khách hàng...",
                         commercial_partner.name, customer_cd, acumatica_cust_id)
            api_client = SaleAcumaticaAPI(self.env)
            try:
                result = api_client.create_customer(commercial_partner)
                err_msg = (result.get('Message') or str(result)) if isinstance(result, dict) else ''
                data = (result.get('Data') or result) if isinstance(result, dict) else {}

                new_customer_cd = (
                    data.get('CustomerCD')
                    or data.get('AcctCD')
                    or customer_cd
                    or commercial_partner.ref
                    or f"CUST{commercial_partner.id}"
                )
                customer_cd = str(new_customer_cd).strip()

                new_cust_id = data.get('CustomerID') or data.get('BAccountID') or acumatica_cust_id or 7
                acumatica_cust_id = int(new_cust_id)

                commercial_partner.write({
                    'x_customer_code': customer_cd,
                    'x_acumatica_customer_id': acumatica_cust_id,
                })

                if 'already exists' in err_msg.lower():
                    self.message_post(body=_('Customer already exists on Acumatica. Automatically linked with code: <b>%s</b>') % customer_cd)
                else:
                    self.message_post(body=_('Successfully auto-created customer on Acumatica with code: <b>%s</b>') % customer_cd)
            except UserError:
                raise
            except Exception as e:
                _logger.error('Error auto-creating Acumatica customer: %s', e)
                if not acumatica_cust_id:
                    acumatica_cust_id = 7
                    commercial_partner.write({'x_acumatica_customer_id': 7})

        if not acumatica_cust_id:
            acumatica_cust_id = 7
            commercial_partner.write({'x_acumatica_customer_id': 7})

        # Kiểm tra bắt buộc phải có ít nhất một dòng sản phẩm thực tế trước khi tạo SO
        real_lines = self.order_line.filtered(lambda l: not l.display_type)
        if not real_lines:
            raise UserError(_('Quotation "%s" has no product lines. Cannot create Sales Order on Acumatica.') % self.name)

        lines_payload = []
        for line in real_lines:
            if not line.x_inventory_id or not line.x_inventory_id.inventory_id:
                raise UserError(_(
                    'Product line "%s" is not linked to an Acumatica Inventory item.\n'
                    'Please select the "Acumatica Inventory" column on the order line before creating Acumatica SO.'
                ) % (line.product_id.display_name or line.name))

            inv_id = line.x_inventory_id.inventory_id
            inv_cd = line.x_inventory_id.inventory_cd or (line.product_id.default_code or '')
            uom = line.x_item_unit_id.name if line.x_item_unit_id else (line.product_uom_id.name or '')
            lines_payload.append({
                'InventoryID': inv_id,
                'InventoryCD': inv_cd,
                'Description': line.name or '',
                'Quantity': float(line.product_uom_qty or 0.0),
                'UOM': uom,
                'UnitPrice': float(line.price_unit or 0.0),
                'CuryUnitPrice': float(line.price_unit or 0.0),
                'TaxID': line.x_tax_id.tax_id if line.x_tax_id else '',
                'TaxRate': float(line.x_tax_id.tax_rate or 0.0) if line.x_tax_id else 0.0,
                'LineTotal': float(line.price_subtotal or 0.0),
            })

        first_line = lines_payload[0] if lines_payload else {}
        if not acumatica_cust_id:
            acumatica_cust_id = (
                getattr(commercial_partner, 'x_acumatica_customer_id', 0)
                or getattr(self.partner_id, 'x_acumatica_customer_id', 0)
                or 7
            )

        payload = {
            'CustomerID': acumatica_cust_id,
            'CustomerCD': customer_cd,
            'OrderType': self.x_order_type_id.code if self.x_order_type_id else 'SO',
            'OdooOrderID': self.id,
            'OdooRefOrder': self.id,
            'OdooOrderName': self.name,
            'CustomerOrderNbr': self.name,
            'CustomerName': commercial_partner.name or self.partner_id.name or '',
            'OrderDate': self.date_order.strftime('%Y-%m-%d %H:%M:%S') if self.date_order else '',
            'AmountUntaxed': float(self.amount_untaxed or 0.0),
            'AmountTax': float(self.amount_tax or 0.0),
            'AmountTotal': float(self.amount_total or 0.0),
            'InventoryID': first_line.get('InventoryID', 0),
            'InventoryCD': first_line.get('InventoryCD', ''),
            'UOM': first_line.get('UOM', ''),
            'UnitPrice': first_line.get('UnitPrice', 0.0),
            'CuryUnitPrice': first_line.get('CuryUnitPrice', 0.0),
            'TaxID': first_line.get('TaxID', ''),
            'TaxRate': first_line.get('TaxRate', 0.0),
            'LineItems': lines_payload,
        }

        # Đánh dấu trạng thái pending để ngăn ngừa các request gửi trùng lặp
        self.write({'x_acumatica_so_status': 'pending'})

        api_client = SaleAcumaticaAPI(self.env)
        try:
            res = api_client.create_sales_order(payload)
            data = (res.get('Data') or res) if isinstance(res, dict) else {}
            so_number = (
                data.get('OrderNbr')
                or data.get('SONumber')
                or data.get('so_number')
                or data.get('acumatica_so_number')
            ) if isinstance(data, dict) else False
            so_date = (data.get('OrderDate') or data.get('so_date')) if isinstance(data, dict) else False
            if isinstance(so_date, str):
                so_date = so_date.replace('T', ' ').split('.')[0].strip()
            so_date = so_date or fields.Datetime.now()

            if isinstance(res, dict) and not res.get('Success', True):
                err_msg = res.get('Message') or str(res)
                # Nếu Acumatica báo đã tồn tại và có kèm OrderNbr trong Data -> Tự động liên kết
                if 'already exists' in err_msg.lower() and so_number:
                    self.write({
                        'x_acumatica_so_number': so_number,
                        'x_acumatica_so_date': so_date,
                        'x_acumatica_so_status': 'synced',
                    })
                    msg = _('Acumatica SO already exists with number: <b>%s</b>. Automatically linked successfully!') % so_number
                    self.message_post(body=msg)
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Success'),
                            'message': msg,
                            'type': 'success',
                            'sticky': False,
                            'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                        }
                    }
                else:
                    self.write({'x_acumatica_so_status': 'failed'})
                    raise UserError(_('Acumatica returned error: %s') % err_msg)

            if so_number:
                self.write({
                    'x_acumatica_so_number': so_number,
                    'x_acumatica_so_date': so_date,
                    'x_acumatica_so_status': 'synced',
                })
                msg = _('Successfully created Acumatica SO: <b>%s</b>') % so_number
            else:
                self.write({'x_acumatica_so_status': 'pending'})
                msg = _('Sent SO creation request to Acumatica for order #%s. Waiting for Acumatica to process.') % self.name

            self.message_post(body=msg)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': msg,
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }
        except UserError:
            if self.x_acumatica_so_status == 'pending':
                self.write({'x_acumatica_so_status': 'failed'})
            raise
        except Exception as e:
            self.write({'x_acumatica_so_status': 'failed'})
            _logger.error('Error creating Acumatica SO for #%s: %s', self.name, e)
            raise UserError(_('Failed to create SO on Acumatica: %s') % str(e))

    # Thông báo khi click vào nút màu xám khi đơn đang chờ Acumatica đồng bộ
    def action_check_acumatica_so_status(self):
        self.ensure_one()
        msg = _('This quotation is waiting for Acumatica to sync and generate SO number.')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Acumatica Sync Status'),
                'message': msg,
                'type': 'info',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    # Chặn xác nhận báo giá nếu chưa có dòng sản phẩm nào
    def action_confirm(self):
        for order in self:
            real_lines = order.order_line.filtered(lambda l: not l.display_type)
            if not real_lines:
                raise UserError(
                    _('Cannot confirm quotation "%s" without any product lines. Please add at least one product before confirming.') % order.name
                )
        return super().action_confirm()

    # Khóa chỉnh sửa dữ liệu khi Báo giá đã ở trạng thái thành công
    def write(self, vals):
        protected_fields = {'partner_id', 'x_order_type_id', 'order_line', 'payment_term_id', 'date_order', 'pricelist_id'}
        if not self.env.context.get('bypass_sale_lock'):
            for order in self:
                if order.state == 'sale' and any(f in vals for f in protected_fields):
                    raise UserError(_('Cannot modify quotation when it is in "Successful Quotation" status.'))
        return super().write(vals)

    # Tính tổng tiền chưa thuế, tiền thuế và tổng thanh toán theo Thuế Acumatica
    @api.depends('order_line.price_subtotal', 'order_line.price_tax', 'currency_id', 'company_id')
    def _compute_amounts(self):
        for order in self:
            order_lines = order._get_priced_lines()
            amount_untaxed = sum(order_lines.mapped('price_subtotal'))
            amount_tax = sum(order_lines.mapped('price_tax'))
            order.amount_untaxed = amount_untaxed
            order.amount_tax = amount_tax
            order.amount_total = amount_untaxed + amount_tax

    # Định dạng chi tiết thuế và tổng tiền hiển thị ở chân trang đơn hàng
    @api.depends_context('lang')
    @api.depends('order_line.price_subtotal', 'order_line.price_tax', 'order_line.x_tax_id', 'currency_id', 'company_id')
    def _compute_tax_totals(self):
        for order in self:
            order_lines = order._get_priced_lines()
            amount_untaxed = sum(order_lines.mapped('price_subtotal'))
            amount_tax = sum(order_lines.mapped('price_tax'))
            amount_total = amount_untaxed + amount_tax
            currency = order.currency_id or order.company_id.currency_id

            tax_groups = []
            tax_map = {}
            for line in order_lines:
                tax = line.x_tax_id
                tax_id = tax.id if tax else False
                if tax_id not in tax_map:
                    tax_map[tax_id] = {'tax': tax, 'base': 0.0, 'tax_amount': 0.0}
                tax_map[tax_id]['base'] += line.price_subtotal
                tax_map[tax_id]['tax_amount'] += line.price_tax

            for tax_id, d in tax_map.items():
                if not tax_id or not d['tax']:
                    continue
                t = d['tax']
                rate_str = f"{t.tax_rate:g}%" if t.tax_rate is not False else ""
                group_name = f"[{t.tax_id}] {t.name}" if t.name else t.tax_id
                if rate_str:
                    group_name += f" ({rate_str})"
                tax_groups.append({
                    'id': t.id,
                    'tax_amount_currency': currency.round(d['tax_amount']) if currency else d['tax_amount'],
                    'tax_amount': currency.round(d['tax_amount']) if currency else d['tax_amount'],
                    'base_amount_currency': currency.round(d['base']) if currency else d['base'],
                    'base_amount': currency.round(d['base']) if currency else d['base'],
                    'display_base_amount_currency': currency.round(d['base']) if currency else d['base'],
                    'display_base_amount': currency.round(d['base']) if currency else d['base'],
                    'group_name': group_name,
                    'group_label': False,
                })

            subtotals = [{
                'tax_groups': tax_groups,
                'tax_amount_currency': currency.round(amount_tax) if currency else amount_tax,
                'tax_amount': currency.round(amount_tax) if currency else amount_tax,
                'base_amount_currency': currency.round(amount_untaxed) if currency else amount_untaxed,
                'base_amount': currency.round(amount_untaxed) if currency else amount_untaxed,
                'name': _('Untaxed Amount'),
            }]

            order.tax_totals = {
                'currency_id': currency.id if currency else False,
                'currency_pd': currency.rounding if currency else 0.01,
                'company_currency_id': order.company_id.currency_id.id if order.company_id else False,
                'company_currency_pd': order.company_id.currency_id.rounding if order.company_id else 0.01,
                'has_tax_groups': bool(tax_groups),
                'subtotals': subtotals,
                'base_amount_currency': currency.round(amount_untaxed) if currency else amount_untaxed,
                'base_amount': currency.round(amount_untaxed) if currency else amount_untaxed,
                'tax_amount_currency': currency.round(amount_tax) if currency else amount_tax,
                'tax_amount': currency.round(amount_tax) if currency else amount_tax,
                'same_tax_base': False,
                'total_amount_currency': currency.round(amount_total) if currency else amount_total,
                'total_amount': currency.round(amount_total) if currency else amount_total,
            }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_inventory_id = fields.Many2one(
        'ps.sale.inventory',
        string='Acumatica Inventory',
        ondelete='restrict',
        index=True,
    )
    x_item_unit_id = fields.Many2one(
        'ps.sale.item.unit',
        string='Item Unit',
        ondelete='restrict',
    )
    x_tax_id = fields.Many2one(
        'ps.sale.tax',
        string='Acumatica Tax',
        ondelete='restrict',
    )

    # Tự động cập nhật Đơn giá, ĐVT và mô tả theo Vật tư Acumatica
    @api.onchange('x_inventory_id')
    def _onchange_x_inventory_id(self):
        if self.x_inventory_id:
            inv = self.x_inventory_id
            if inv.base_price:
                self.price_unit = inv.base_price
            target_unit = (inv.sales_unit or inv.base_unit or '').strip()
            if target_unit:
                unit = self.env['ps.sale.item.unit'].search([('name', '=ilike', target_unit)], limit=1)
                if unit:
                    self.x_item_unit_id = unit.id
            if not self.name or (self.product_id and self.name == self.product_id.name):
                self.name = f"[{inv.inventory_cd}] {inv.name}" if inv.name else inv.inventory_cd
            if not self.product_id:
                product = self.env['product.product'].search([('default_code', '=', inv.inventory_cd)], limit=1)
                if not product:
                    product = self.env['product.product'].search([], limit=1)
                if product:
                    self.product_id = product.id
                    self.product_uom_id = product.uom_id.id

    # Đảm bảo trường product_id và product_uom_id được điền hợp lệ khi tạo dòng từ x_inventory_id
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('display_type') and not vals.get('is_downpayment'):
                if not vals.get('product_id') and vals.get('x_inventory_id'):
                    inv = self.env['ps.sale.inventory'].browse(vals['x_inventory_id'])
                    if inv:
                        product = self.env['product.product'].search([('default_code', '=', inv.inventory_cd)], limit=1)
                        if not product:
                            product = self.env['product.product'].search([], limit=1)
                        if product:
                            vals['product_id'] = product.id
                            if not vals.get('product_uom_id'):
                                vals['product_uom_id'] = product.uom_id.id
                elif vals.get('product_id') and not vals.get('product_uom_id'):
                    product = self.env['product.product'].browse(vals['product_id'])
                    if product.uom_id:
                        vals['product_uom_id'] = product.uom_id.id
        return super().create(vals_list)

    # Khi chọn sản phẩm Odoo, tự động liên kết Vật tư Acumatica nếu có mã trùng khớp
    @api.onchange('product_id')
    def _onchange_product_id_inherit_ps(self):
        if self.product_id and self.product_id.default_code and not self.x_inventory_id:
            inv = self.env['ps.sale.inventory'].search([('inventory_cd', '=', self.product_id.default_code)], limit=1)
            if inv:
                self.x_inventory_id = inv.id
                if inv.base_price:
                    self.price_unit = inv.base_price
                target_unit = (inv.sales_unit or inv.base_unit or '').strip()
                if target_unit:
                    unit = self.env['ps.sale.item.unit'].search([('name', '=ilike', target_unit)], limit=1)
                    if unit:
                        self.x_item_unit_id = unit.id

    # Tính toán thành tiền, thuế và tổng tiền dòng theo Thuế Acumatica
    @api.depends('product_uom_qty', 'discount', 'price_unit', 'x_tax_id')
    def _compute_amount(self):
        for line in self:
            price = line.price_unit * (1.0 - (line.discount or 0.0) / 100.0)
            subtotal = price * line.product_uom_qty
            tax_rate = (line.x_tax_id.tax_rate or 0.0) if line.x_tax_id else 0.0
            tax_amount = subtotal * (tax_rate / 100.0)
            if line.currency_id:
                line.price_subtotal = line.currency_id.round(subtotal)
                line.price_tax = line.currency_id.round(tax_amount)
                line.price_total = line.price_subtotal + line.price_tax
            else:
                line.price_subtotal = subtotal
                line.price_tax = tax_amount
                line.price_total = subtotal + tax_amount

    # Khóa chỉnh sửa dòng sản phẩm khi Báo giá đã thành công
    def write(self, vals):
        if not self.env.context.get('bypass_sale_lock'):
            for line in self:
                if line.order_id.state == 'sale':
                    raise UserError(_('Cannot modify quotation lines when it is in "Successful Quotation" status.'))
        return super().write(vals)

    # Khóa xóa dòng sản phẩm khi Báo giá đã thành công
    def unlink(self):
        if not self.env.context.get('bypass_sale_lock'):
            for line in self:
                if line.order_id.state == 'sale':
                    raise UserError(_('Cannot delete quotation lines when it is in "Successful Quotation" status.'))
        return super().unlink()


