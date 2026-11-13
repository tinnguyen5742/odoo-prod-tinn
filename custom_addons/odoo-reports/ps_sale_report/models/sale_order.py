from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    ps_contract_ref = fields.Char(
        string="Số hợp đồng",
        index=True,
    )


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    ps_contract_ref = fields.Char(
        related="order_id.ps_contract_ref",
        string="Số hợp đồng",
    )
    ps_customer_po = fields.Char(
        related="order_id.client_order_ref",
        string="Số PO khách hàng",
    )
    ps_specification = fields.Char(
        string="QCSP",
    )
    ps_requested_receipt_date = fields.Date(
        string="Ngày yêu cầu nhập kho",
    )
    ps_confirmed_receipt_date = fields.Date(
        string="Ngày xác nhận nhập kho",
    )
    ps_production_ref = fields.Char(
        string="LSX tham chiếu",
    )
    ps_production_number = fields.Char(
        string="LSX",
    )
    ps_report_note = fields.Char(
        string="Ghi chú báo cáo",
    )
    ps_base_uom_id = fields.Many2one(
        related="product_id.uom_id",
        string="ĐVT gốc",
    )
    ps_base_quantity = fields.Float(
        string="Số lượng gốc",
        compute="_compute_ps_base_quantity",
        digits="Product Unit",
    )

    @api.depends(
        "product_uom_qty",
        "product_uom_id",
        "product_id.uom_id",
    )
    def _compute_ps_base_quantity(self):
        for line in self:
            if line.product_uom_id and line.product_id.uom_id:
                line.ps_base_quantity = (
                    line.product_uom_id._compute_quantity(
                        line.product_uom_qty,
                        line.product_id.uom_id,
                        round=False,
                    )
                )
            else:
                line.ps_base_quantity = 0.0