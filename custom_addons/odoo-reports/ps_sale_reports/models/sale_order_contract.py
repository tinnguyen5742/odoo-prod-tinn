from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    ps_contract_customer_id = fields.Many2one(
        related="order_id.partner_id",
        string="Khách hàng",
        store=True,
        index=True,
    )

    ps_contract_promised_date = fields.Datetime(
        string="Ngày giao dự kiến",
        compute="_compute_ps_contract_promised_date",
    )

    @api.depends("order_id.commitment_date", "order_id.expected_date")
    def _compute_ps_contract_promised_date(self):
        for line in self:
            line.ps_contract_promised_date = (
                line.order_id.commitment_date or line.order_id.expected_date
            )

    ps_contract_delivered_qty = fields.Float(
        string="SL thực hiện",
        compute="_compute_ps_contract_execution",
        digits="Product Unit",
    )

    ps_contract_delivered_value = fields.Monetary(
        string="Trị giá thực hiện",
        compute="_compute_ps_contract_execution",
        currency_field="currency_id",
    )

    ps_contract_remaining_qty = fields.Float(
        string="SL còn lại",
        compute="_compute_ps_contract_execution",
        digits="Product Unit",
    )

    ps_contract_last_delivery_date = fields.Date(
        string="Ngày giao thực tế gần nhất",
        compute="_compute_ps_contract_execution",
    )

    @api.depends_context("ps_contract_date_to", "tz")
    @api.depends(
        "product_uom_qty",
        "price_total",
        "move_ids.state",
        "move_ids.date",
        "move_ids.quantity",
        "move_ids.product_uom",
        "move_ids.to_refund",
    )
    def _compute_ps_contract_execution(self):
        cutoff = self.env.context.get("ps_contract_date_to")
        if not cutoff:
            cutoff = fields.Date.to_string(
                fields.Date.context_today(self)
            )

        # Dùng cơ chế tính số lượng giao theo ngày của Odoo 19.
        lines = self.with_context(accrual_entry_date=cutoff)
        delivered_quantities = lines._prepare_qty_delivered()

        for line in lines:
            delivered = delivered_quantities.get(line, 0.0)

            line.ps_contract_delivered_qty = delivered
            line.ps_contract_remaining_qty = (
                line.product_uom_qty - delivered
            )

            if line.product_uom_qty:
                line.ps_contract_delivered_value = line.currency_id.round(
                    line.price_total
                    * delivered
                    / line.product_uom_qty
                )
            else:
                line.ps_contract_delivered_value = 0.0

            outgoing, incoming = (
                line._get_outgoing_incoming_moves()
            )

            delivery_dates = [
                fields.Date.context_today(move, move.date)
                for move in outgoing
                if move.state == "done"
            ]

            line.ps_contract_last_delivery_date = (
                max(delivery_dates)
                if delivery_dates
                else False
            )
