from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class SaleQuantityWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(
        selection_add=[("quantity", "Tổng hợp bán hàng theo M² / ĐVT gốc"), ("execution",)],
        ondelete={"quantity": "set default"},
    )
    quantity_parent_partner_id = fields.Many2one(
        "res.partner", string="Khách hàng cha", check_company=True,
    )
    quantity_sales_team_id = fields.Many2one(
        "crm.team", string="Nhóm Sales", check_company=True,
    )

    def _get_quantity_data(self):
        self.ensure_one()
        if self.report_type != "quantity":
            raise UserError("Chọn báo cáo Tổng hợp bán hàng theo M² / ĐVT gốc.")
        filters = []
        if self.partner_id:
            filters.append(("order_id.partner_id", "child_of", self.partner_id.id))
        if self.quantity_parent_partner_id:
            filters.append(("order_id.partner_id", "child_of", self.quantity_parent_partner_id.id))
        if self.product_id:
            filters.append(("product_id", "=", self.product_id.id))
        if self.quantity_sales_team_id:
            filters.append(("order_id.team_id", "=", self.quantity_sales_team_id.id))
        events = self._get_dispatch_quantities(self.date_from, self.date_to, filters)
        currency = self.company_id.currency_id
        customers = {}
        for event in events:
            line, day, shipped = event["line"], event["day"], event["quantity"]
            if not shipped:
                continue
            product = line.product_id
            base_qty = line.product_uom_id._compute_quantity(shipped, product.uom_id, round=False)
            if line.ps_tracking_m2_factor:
                quantity, unit_key, unit_name = base_qty * line.ps_tracking_m2_factor, ("m2", 0), "M²"
            else:
                quantity, unit_key, unit_name = base_qty, ("base", product.uom_id.id), product.uom_id.name
            amount = line.currency_id._convert(
                line.price_subtotal / line.product_uom_qty * shipped, currency, self.company_id, day,
            )
            tax = line.currency_id._convert(
                line.price_tax / line.product_uom_qty * shipped, currency, self.company_id, day,
            )
            partner = line.order_id.partner_id
            customer = customers.setdefault(partner.id, {"partner": partner, "items": {}})
            item = customer["items"].setdefault((product.id, unit_key), {
                "product": product, "unit_key": unit_key, "unit_name": unit_name,
                "quantity": 0.0, "amount": 0.0, "tax": 0.0, "notes": set(),
            })
            item["quantity"] += quantity
            item["amount"] += amount
            item["tax"] += tax
            if line.ps_report_note:
                item["notes"].add(line.ps_report_note)
        if not customers:
            raise UserError("Không có phiếu giao hoàn tất hoặc phiếu trả cập nhật SO phù hợp trong khoảng ngày đã chọn.")
        rows, seq, grand_totals, grand_qty = [], 0, [0.0, 0.0, 0.0], {}

        def add_qty(target, item):
            qty = target.setdefault(item["unit_key"], [item["unit_name"], 0.0])
            qty[1] += item["quantity"]

        def quantity_list(qty):
            return [(unit, value) for unit, value in sorted(qty.values(), key=lambda q: q[0])]

        for customer in sorted(customers.values(), key=lambda c: (c["partner"].name.casefold(), c["partner"].id)):
            partner = customer["partner"]
            label = f"({partner.ref}) - {partner.name}" if partner.ref else partner.name
            items, totals, quantities = [], [0.0, 0.0, 0.0], {}
            for item in sorted(customer["items"].values(), key=lambda i: (i["product"].display_name.casefold(), i["product"].id, i["unit_name"])):
                seq += 1
                amount, tax = currency.round(item["amount"]), currency.round(item["tax"])
                total = currency.round(amount + tax)
                qty = item["quantity"]
                # Returns at a different price can leave a value with zero net
                # quantity. Preserve that value and leave average price blank.
                price = None if float_is_zero(qty, precision_digits=6) else amount / qty
                items.append({"kind": "item", "values": [seq, item["product"].display_name,
                    item["unit_name"], qty, price, amount, tax, total, " | ".join(sorted(item["notes"]))]})
                totals = [a + b for a, b in zip(totals, (amount, tax, total))]
                add_qty(quantities, item)
                add_qty(grand_qty, item)
            rows.append({"kind": "customer", "label": "Tên KH: " + label,
                         "totals": totals, "quantities": quantity_list(quantities)})
            rows.extend(items)
            grand_totals = [a + b for a, b in zip(grand_totals, totals)]
        rows.append({"kind": "total", "label": "TỔNG CỘNG", "totals": grand_totals,
                     "quantities": quantity_list(grand_qty)})
        return {"wizard": self, "rows": rows, "currency": currency, "page_budget": 475,
                "headers": ["STT", "Tên mặt hàng", "ĐVT", "Số lượng", "Trị giá", "Thành tiền", "VAT", "Tổng cộng", "Ghi chú"],
                "sales_filter": self.salesperson_id.name or "", "customer_filter": self.partner_id.display_name or "",
                "product_filter": self.product_id.display_name or "",
                "extra_filters": [label + value for label, value in [
                    ("Khách hàng cha: ", self.quantity_parent_partner_id.display_name or ""),
                    ("Nhóm Sales: ", self.quantity_sales_team_id.name or ""),
                ] if value]}

    def action_print_pdf(self):
        if self.report_type != "quantity":
            return super().action_print_pdf()
        self._get_quantity_data()
        return self.env.ref("ps_sale_reports.action_sale_quantity_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "quantity":
            return super().action_export_xlsx()
        return self._export_daily_xlsx(self._get_quantity_data(), "Tong hop M2 DVT goc",
            "BÁO CÁO TỔNG HỢP BÁN HÀNG THEO M² / ĐVT GỐC",
            f"Tong_hop_ban_hang_M2_DVT_goc_{self.date_from}_{self.date_to}.xlsx")
