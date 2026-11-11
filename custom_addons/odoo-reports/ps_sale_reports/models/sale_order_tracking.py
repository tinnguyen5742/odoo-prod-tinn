from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    ps_tracking_quantity_limit = fields.Float(
        string="Hạn mức số lượng", digits="Product Unit",
        help="Giới hạn số lượng của dòng SO, theo ĐVT khách hàng. 0 là chưa đặt hạn mức.",
    )
    ps_tracking_stock_qty = fields.Float(string="Tồn kho", compute="_compute_tracking_progress", digits="Product Unit")
    ps_tracking_unproduced_qty = fields.Float(string="SL chưa SX", compute="_compute_tracking_progress", digits="Product Unit")
    ps_tracking_has_mrp = fields.Boolean(string="Có lệnh MRP", compute="_compute_tracking_progress")
    ps_tracking_production_ids = fields.One2many("mrp.production", "sale_line_id", string="Lệnh sản xuất theo SO")

    @api.depends(
        "product_id", "product_id.qty_available", "product_uom_id", "company_id",
        "ps_tracking_production_ids.state", "ps_tracking_production_ids.product_qty",
        "ps_tracking_production_ids.qty_produced", "ps_tracking_production_ids.product_uom_id",
        "ps_tracking_production_ids.product_id",
    )
    def _compute_tracking_progress(self):
        # Normal ACLs apply to both stock and MRP. Never infer an MO from a text origin.
        productions = self.env["mrp.production"].search([
            ("sale_line_id", "in", self.ids), ("state", "!=", "cancel"),
            ("company_id", "in", self.company_id.ids),
        ]) if self.ids else self.env["mrp.production"]
        grouped = {}
        for production in productions:
            grouped.setdefault(production.sale_line_id.id, self.env["mrp.production"])
            grouped[production.sale_line_id.id] |= production
        for line in self:
            product = line.product_id.with_company(line.company_id).with_context(
                allowed_company_ids=[line.company_id.id], warehouse_id=False,
                location=False, to_date=False, from_date=False, lot_id=False,
                owner_id=False, package_id=False,
            )
            line.ps_tracking_stock_qty = product.uom_id._compute_quantity(
                product.qty_available, line.product_uom_id, round=False,
            ) if product and line.product_uom_id else 0
            orders = grouped.get(line.id, self.env["mrp.production"]).filtered(
                lambda mo: mo.product_id == line.product_id and mo.company_id == line.company_id
            )
            line.ps_tracking_has_mrp = bool(orders)
            line.ps_tracking_unproduced_qty = sum(
                mo.product_uom_id._compute_quantity(
                    max(mo.product_qty - mo.qty_produced, 0), line.product_uom_id, round=False,
                ) for mo in orders if mo.state != "done"
            )

    @api.constrains("ps_tracking_quantity_limit")
    def _check_tracking_limit(self):
        if any(line.ps_tracking_quantity_limit < 0 for line in self):
            raise ValidationError("Hạn mức số lượng không được âm.")

    ps_tracking_salesperson_id = fields.Many2one(
        related="order_id.user_id",
        string="Nhân viên Sales",
    )

    ps_tracking_order_date = fields.Datetime(
        related="order_id.date_order",
        string="Ngày SO",
    )

    ps_tracking_product_code = fields.Char(
        related="product_id.default_code",
        string="Mã hàng",
    )

    ps_requested_delivery_date = fields.Date(
        string="Ngày KH yêu cầu giao",
    )

    ps_actual_receipt_date = fields.Date(
        string="Ngày nhập kho",
        help="Ngày nhập kho thực tế phục vụ theo dõi đơn hàng.",
    )

    ps_customer_confirmation_date = fields.Date(
        string="Ngày xác nhận KH",
    )

    ps_product_structure = fields.Char(
        string="Cấu trúc sản phẩm",
    )

    ps_tracking_m2_factor = fields.Float(
        string="M² / ĐVT gốc",
        digits=(16, 6),
        help=(
            "Diện tích tương ứng với một đơn vị tính gốc "
            "của sản phẩm. Để 0 nếu không áp dụng."
        ),
    )

    ps_tracking_quantity_m2 = fields.Float(
        string="SL theo M²",
        compute="_compute_tracking_quantity_m2",
        digits=(16, 4),
    )

    @api.depends(
        "ps_base_quantity",
        "ps_tracking_m2_factor",
    )
    def _compute_tracking_quantity_m2(self):
        for line in self:
            line.ps_tracking_quantity_m2 = (
                line.ps_base_quantity
                * line.ps_tracking_m2_factor
            )

    @api.constrains("ps_tracking_m2_factor")
    def _check_tracking_m2_factor(self):
        for line in self:
            if line.ps_tracking_m2_factor < 0:
                raise ValidationError(
                    "Hệ số quy đổi M² không được âm."
                )
