import base64
import io

import xlsxwriter
from odoo import fields, models
from odoo.exceptions import UserError


DAILY_HEADERS = ["STT", "Mặt hàng", "ĐVT", "Số lượng", "Đơn giá", "Thành tiền", "VAT", "Tổng cộng", "Ghi chú"]


class SaleDailyWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(
        selection_add=[("daily", "Chi tiết bán hàng theo ngày (xuất bán)"), ("tracking",)],
        ondelete={"daily": "set default"},
    )

    def _get_daily_data(self):
        self.ensure_one()
        if self.report_type not in ("daily", "daily_summary"):
            raise UserError("Chọn báo cáo Chi tiết bán hàng theo ngày (xuất bán).")
        filters = []
        if self.partner_id:
            filters.append(("order_id.partner_id", "child_of", self.partner_id.id))
        if self.product_id:
            filters.append(("product_id", "=", self.product_id.id))
        events = self._get_dispatch_quantities(self.date_from, self.date_to, filters)
        currency = self.company_id.currency_id
        days = {}
        for event in events:
            line, day, quantity = event["line"], event["day"], event["quantity"]
            if not quantity:
                continue
            order = line.order_id
            partner = order.partner_id
            documents = event["moves"].picking_id.sorted("name")
            document_ids = tuple(documents.ids) or tuple(-move.id for move in event["moves"])
            customer = days.setdefault(day, {}).setdefault(partner.id, {
                "partner": partner, "documents": {}, "totals": [0.0, 0.0, 0.0],
            })
            document = customer["documents"].setdefault((order.id, document_ids), {
                "label": "Số HĐ: " + (order.ps_contract_ref or "") + " – Chứng từ: "
                         + (", ".join(documents.mapped("name")) or ", ".join(event["moves"].mapped("reference")))
                         + " | SO: " + order.name,
                "items": [], "totals": [0.0, 0.0, 0.0],
            })
            net_unit = line.price_subtotal / line.product_uom_qty
            tax_unit = line.price_tax / line.product_uom_qty
            amount = line.currency_id._convert(net_unit * quantity, currency, self.company_id, day)
            tax = line.currency_id._convert(tax_unit * quantity, currency, self.company_id, day)
            unit = line.currency_id._convert(net_unit, currency, self.company_id, day, round=False)
            document["items"].append({"line": line, "quantity": quantity, "unit": unit,
                                      "amount": amount, "tax": tax, "total": currency.round(amount + tax)})
            for total in (document["totals"], customer["totals"]):
                for index, value in enumerate((amount, tax, currency.round(amount + tax))):
                    total[index] += value
        if not days:
            raise UserError("Không có phiếu giao hoàn tất hoặc phiếu trả cập nhật SO phù hợp trong khoảng ngày đã chọn.")
        rows, seq, totals = [], 0, [0.0, 0.0, 0.0]
        for day, customers in sorted(days.items()):
            rows.append({"kind": "day", "label": f"Ngày {day:%d/%m/%Y}"})
            for customer in sorted(customers.values(), key=lambda c: (c["partner"].name.casefold(), c["partner"].id)):
                partner = customer["partner"]
                name = f"({partner.ref}) - {partner.name}" if partner.ref else partner.name
                rows.append({"kind": "customer", "label": "Tên KH: " + name, "totals": customer["totals"]})
                for document in sorted(customer["documents"].values(), key=lambda d: d["label"]):
                    rows.append({"kind": "document", "label": document["label"], "totals": document["totals"]})
                    for item in sorted(document["items"], key=lambda i: (i["line"].sequence, i["line"].id)):
                        seq += 1
                        line = item["line"]
                        rows.append({"kind": "item", "product_id": line.product_id.id,
                            "uom_id": line.product_uom_id.id, "values": [seq, line.product_id.display_name,
                            line.product_uom_id.name, item["quantity"], item["unit"], item["amount"],
                            item["tax"], item["total"], line.ps_report_note or ""]})
                totals = [a + b for a, b in zip(totals, customer["totals"])]
        rows.append({"kind": "total", "label": "TỔNG CỘNG", "totals": totals})
        return {"wizard": self, "rows": rows, "currency": currency, "headers": DAILY_HEADERS,
                "sales_filter": self.salesperson_id.name or "", "customer_filter": self.partner_id.display_name or "",
                "product_filter": self.product_id.display_name or ""}

    def action_print_pdf(self):
        if self.report_type != "daily":
            return super().action_print_pdf()
        self._get_daily_data()
        return self.env.ref("ps_sale_reports.action_sale_daily_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "daily":
            return super().action_export_xlsx()
        data = self._get_daily_data()
        return self._export_daily_xlsx(data, "Chi tiet ban hang theo ngay",
            "BÁO CÁO CHI TIẾT BÁN HÀNG THEO NGÀY",
            f"Chi_tiet_ban_hang_theo_ngay_{self.date_from}_{self.date_to}.xlsx")

    def _export_daily_xlsx(self, data, sheet_name, report_title, filename):
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False,
            "strings_to_urls": False, "default_format_properties": {"font_name": "Times New Roman", "font_size": 11}})
        sheet = book.add_worksheet(sheet_name)
        base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter"}
        number_format = "#,##0" + ("." + "0" * data["currency"].decimal_places if data["currency"].decimal_places else "")
        text = book.add_format({**base, "text_wrap": True})
        number = book.add_format({**base, "num_format": number_format})
        quantity = book.add_format({**base, "num_format": "#,##0.00"})
        integer = book.add_format({**base, "num_format": "0", "align": "center"})
        heading = book.add_format({**base, "bold": True, "bg_color": "#EDF1F6", "align": "center"})
        group = book.add_format({**base, "bold": True, "font_color": "#0645AD", "text_wrap": True})
        group_number = book.add_format({**base, "bold": True, "font_color": "#0645AD", "num_format": number_format})
        total_text = book.add_format({**base, "bold": True, "bg_color": "#EDF1F6"})
        total_number = book.add_format({**base, "bold": True, "bg_color": "#EDF1F6", "num_format": number_format})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        meta = book.add_format({"text_wrap": True})
        centered = book.add_format({"italic": True, "align": "center"})
        for col, width in enumerate([6, 55, 12, 16, 18, 20, 18, 20, 35]):
            sheet.set_column(col, col, width)
        sheet.merge_range(0, 0, 0, 8, self.company_id.name, meta)
        sheet.merge_range(1, 0, 1, 8, report_title, title)
        sheet.set_row(1, 28)
        sheet.merge_range(2, 0, 2, 8, f"Từ ngày {self.date_from:%d/%m/%Y} đến ngày {self.date_to:%d/%m/%Y} | ĐVT tiền: {data['currency'].name}", centered)
        filters = [label + value for label, value in [("Sales: ", data["sales_filter"]),
                   ("Khách hàng: ", data["customer_filter"]), ("Sản phẩm: ", data["product_filter"])] if value]
        filters.extend(data.get("extra_filters", []))
        sheet.merge_range(3, 0, 3, 8, " | ".join(filters), meta)
        sheet.set_row(3, 30 if filters else 15)
        for col, label in enumerate(data["headers"]):
            sheet.write_string(5, col, label, heading)
        for row, entry in enumerate(data["rows"], 6):
            if entry["kind"] == "item":
                for col, value in enumerate(entry["values"]):
                    if col in (0, 3, 4, 5, 6, 7):
                        fmt = integer if col == 0 else quantity if col == 3 else number
                        if value is None:
                            sheet.write_blank(row, col, None, fmt)
                        else:
                            sheet.write_number(row, col, value, fmt)
                    else:
                        sheet.write_string(row, col, value, text)
                sheet.set_row(row, max(26, min(300, 15 * max((len(str(entry["values"][c])) + width - 1) // width for c, width in [(1, 50), (8, 30)]))))
            elif entry["kind"] == "day":
                sheet.merge_range(row, 0, row, 8, entry["label"], group)
                sheet.set_row(row, 24)
            else:
                is_total, is_customer = entry["kind"] == "total", entry["kind"] == "customer"
                fmt = total_text if is_total else group if is_customer else text
                num = total_number if is_total else group_number if is_customer else number
                if "quantities" in entry:
                    sheet.merge_range(row, 0, row, 1, entry["label"], fmt)
                    quantities = entry["quantities"]
                    if len(quantities) == 1:
                        sheet.write_string(row, 2, quantities[0][0], fmt)
                        sheet.write_number(row, 3, quantities[0][1], quantity)
                    else:
                        sheet.merge_range(row, 2, row, 3, "\n".join(f"{uom}: {qty:,.2f}" for uom, qty in quantities), fmt)
                    sheet.write_blank(row, 4, None, fmt)
                else:
                    sheet.merge_range(row, 0, row, 4, entry["label"], fmt)
                for col, value in enumerate(entry["totals"], 5):
                    sheet.write_number(row, col, value, num)
                sheet.write_blank(row, 8, None, fmt)
                width = 65 if "quantities" in entry else 86
                sheet.set_row(row, max(26, min(300, 15 * max((len(entry["label"]) + width - 1) // width,
                    len(entry.get("quantities", []))))))
        last = len(data["rows"]) + 7
        self._write_xlsx_signature(book, sheet, last, 8)
        sheet.freeze_panes(6, 0)
        sheet.repeat_rows(5)
        sheet.hide_gridlines(0)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.print_area(0, 0, last + 1, 8)
        sheet.set_footer("&RTrang &P / &N")
        book.close()
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self",
                "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
