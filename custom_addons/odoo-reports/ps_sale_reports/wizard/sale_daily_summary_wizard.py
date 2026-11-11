from odoo import fields, models
from odoo.exceptions import UserError


class SaleDailySummaryWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(
        selection_add=[("daily_summary", "Tổng hợp bán hàng theo ngày"), ("tracking",)],
        ondelete={"daily_summary": "set default"},
    )

    def _get_daily_summary_data(self):
        self.ensure_one()
        if self.report_type != "daily_summary":
            raise UserError("Chọn báo cáo Tổng hợp bán hàng theo ngày.")
        detail = self._get_daily_data()
        days, day, customer, document = {}, None, None, ""
        for row in detail["rows"]:
            if row["kind"] == "day":
                day = row["label"]
                days.setdefault(day, {})
            elif row["kind"] == "customer":
                customer = days[day].setdefault(row["label"], {
                    "label": row["label"].removeprefix("Tên KH: "), "items": {},
                    "quantities": {}, "totals": [0.0, 0.0, 0.0],
                })
            elif row["kind"] == "document":
                document = row["label"]
            elif row["kind"] == "item":
                values = row["values"]
                # Never combine different products, UOMs, prices or notes.
                key = (document, row["product_id"], row["uom_id"], values[4], values[8])
                item = customer["items"].setdefault(key, {"values": [0, document + "\n" + values[1],
                    values[2], 0.0, values[4], 0.0, 0.0, 0.0, values[8]]})
                for col in (3, 5, 6, 7):
                    item["values"][col] += values[col]
                uom_key = (row["uom_id"], values[2])
                customer["quantities"][uom_key] = customer["quantities"].get(uom_key, 0.0) + values[3]
                customer["totals"] = [a + b for a, b in zip(customer["totals"], values[5:8])]
        rows, seq, all_qty, totals = [], 0, {}, [0.0, 0.0, 0.0]
        for day, customers in days.items():
            rows.append({"kind": "day", "label": day})
            for customer in customers.values():
                quantities = [(key[1], qty) for key, qty in sorted(customer["quantities"].items(), key=lambda i: (i[0][1], i[0][0]))]
                rows.append({"kind": "customer", "label": customer["label"],
                             "totals": customer["totals"], "quantities": quantities})
                for item in customer["items"].values():
                    seq += 1
                    item["values"][0] = seq
                    rows.append({"kind": "item", **item})
                for uom_key, qty in customer["quantities"].items():
                    all_qty[uom_key] = all_qty.get(uom_key, 0.0) + qty
                totals = [a + b for a, b in zip(totals, customer["totals"])]
        rows.append({"kind": "total", "label": "TỔNG CỘNG", "totals": totals,
                     "quantities": [(key[1], qty) for key, qty in sorted(all_qty.items(), key=lambda i: (i[0][1], i[0][0]))]})
        return {**detail, "rows": rows, "headers": ["STT", "Tên mặt hàng / Chứng từ", "ĐVT", "Số lượng",
                                                   "Đơn giá", "Thành tiền", "VAT", "Tổng cộng", "Ghi chú"]}

    def action_print_pdf(self):
        if self.report_type != "daily_summary":
            return super().action_print_pdf()
        self._get_daily_summary_data()
        return self.env.ref("ps_sale_reports.action_sale_daily_summary_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "daily_summary":
            return super().action_export_xlsx()
        return self._export_daily_xlsx(self._get_daily_summary_data(), "Tong hop ban hang theo ngay",
            "BÁO CÁO TỔNG HỢP BÁN HÀNG THEO NGÀY",
            f"Tong_hop_ban_hang_theo_ngay_{self.date_from}_{self.date_to}.xlsx")
