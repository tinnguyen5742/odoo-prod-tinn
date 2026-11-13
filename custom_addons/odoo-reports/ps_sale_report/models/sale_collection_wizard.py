import base64
import io
from datetime import datetime, time

import xlsxwriter
from odoo import fields, models
from odoo.exceptions import UserError


COLLECTION_HEADERS = ["STT", "Số hóa đơn / Số CT", "Ngày", "Diễn giải", "Giá trị hóa đơn", "Giá trị thanh toán", "Giá trị còn lại", "Hạn TT"]


class SaleCollectionWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(selection_add=[("collection", "Thu tiền khách hàng"), ("delivery",)], ondelete={"collection": "set default"})

    def _get_unallocated_collections(self):
        """Posted customer receipts in the period, still unused at the cutoff."""
        domain = [("company_id", "=", self.company_id.id), ("move_id.state", "=", "posted"),
            ("move_id.move_type", "=", "entry"), ("account_id.account_type", "=", "asset_receivable"),
            ("date", ">=", self.date_from), ("date", "<=", self.date_to), ("credit", ">", 0),
            ("partner_id", "!=", False),
            "|", "&", ("move_id.origin_payment_id.payment_type", "=", "inbound"),
                ("move_id.origin_payment_id.partner_type", "=", "customer"),
                ("journal_id.type", "in", ["bank", "cash"]),
            "|", ("move_id.origin_payment_id", "=", False),
                ("move_id.origin_payment_id.state", "in", ["in_process", "paid"])]
        if self.partner_id:
            domain.append(("partner_id", "child_of", self.partner_id.id))
        lines = self.env["account.move.line"].search(domain, order="date, move_id, id", limit=20001)
        partials = self.env["account.partial.reconcile"].search([
            ("company_id", "=", self.company_id.id), ("credit_move_id", "in", lines.ids),
            ("max_date", "<=", self.date_to)], limit=20001)
        if max(len(lines), len(partials)) > 20000:
            raise UserError("Có hơn 20.000 dòng thu tiền/đối trừ. Hãy thu hẹp bộ lọc.")
        used = {}
        for partial in partials:
            used[partial.credit_move_id.id] = used.get(partial.credit_move_id.id, 0.0) + partial.credit_amount_currency
        result = {}
        for line in lines:
            currency = line.currency_id or self.company_id.currency_id
            available = currency.round(-line.amount_currency - used.get(line.id, 0.0))
            if available <= 0 or currency.is_zero(available):
                continue
            customer = line.partner_id.commercial_partner_id
            key = (customer.id, currency.id, line.move_id.id)
            item = result.setdefault(key, {"customer": customer, "currency": currency,
                "name": line.move_id.name, "date": line.date, "description": line.move_id.ref or line.name or "", "amount": 0.0})
            item["amount"] += available
        return list(result.values())

    def _get_collection_data(self):
        self.ensure_one()
        invoices, settlements, _orders = self._get_receivable_snapshot(allow_empty=True)
        advances = self._get_unallocated_collections()
        if not invoices and not advances:
            raise UserError("Không có hóa đơn đã ghi sổ hoặc tiền thu chưa phân bổ phù hợp trong kỳ đã chọn.")
        groups, totals, seq = {}, {}, 0
        for invoice in invoices:
            customer, currency = invoice.commercial_partner_id, invoice.currency_id
            key = (customer.id, currency.id)
            group = groups.setdefault(key, {"customer": customer, "currency": currency, "rows": []})
            sign = -1 if invoice.move_type == "out_refund" else 1
            net, tax, gross = sign * invoice.amount_untaxed, sign * invoice.amount_tax, sign * invoice.amount_total
            events = sorted(settlements.get(invoice.id, {}).values(), key=lambda v: (v["date"], v["name"]))
            paid = currency.round(sum(v["amount"] for v in events))
            remaining = currency.round(gross - paid)
            seq += 1
            group["rows"].append({"kind": "invoice", "currency": currency,
                "values": [seq, invoice.name, None, "Điều chỉnh giảm" if sign == -1 else "", gross, paid, remaining, invoice.invoice_date_due or None]})
            detail_seq = 0
            for event in events:
                detail_seq += 1
                label = "Đối trừ hóa đơn" if event["move_type"] in ("out_invoice", "out_refund") else "Thu tiền / Đối trừ"
                group["rows"].append({"kind": "item", "currency": currency, "invoice_ref": invoice.name,
                    "values": [detail_seq, event["name"], event["date"], label + (": " + event["description"] if event["description"] else ""),
                        None, currency.round(event["amount"]), None, None]})
            pieces = [("Tiền hàng sau chiết khấu, chưa thuế", net), ("Tiền VAT", tax)]
            adjustment = currency.round(gross - net - tax)
            if not currency.is_zero(adjustment):
                pieces.append(("Làm tròn / Điều chỉnh hóa đơn", adjustment))
            for label, amount in pieces:
                detail_seq += 1
                group["rows"].append({"kind": "item", "currency": currency, "invoice_ref": invoice.name,
                    "values": [detail_seq, invoice.name, invoice.invoice_date, label, amount, None, None, None]})
            total = totals.setdefault(currency.id, {"currency": currency, "totals": [0.0] * 3})
            total["totals"] = [a + b for a, b in zip(total["totals"], [gross, paid, remaining])]
        rows = []
        for group in groups.values():
            customer, currency = group["customer"], group["currency"]
            rows.append({"kind": "customer", "label": (customer.ref + " - " if customer.ref else "") + customer.name, "currency": currency})
            rows.append({"kind": "currency", "label": "Loại tiền: " + currency.name, "currency": currency})
            rows.extend(group["rows"])
        for total in totals.values():
            rows.append({"kind": "total", "label": "TỔNG HÓA ĐƠN | " + total["currency"].name, **total})
        advance_groups = {}
        for advance in advances:
            customer, currency = advance["customer"], advance["currency"]
            key = (customer.id, currency.id)
            group = advance_groups.setdefault(key, {"customer": customer, "currency": currency, "rows": [], "amount": 0.0})
            group["amount"] += advance["amount"]
            group["rows"].append({"kind": "advance", "currency": currency,
                "values": [len(group["rows"]) + 1, advance["name"], advance["date"],
                    "Tiền thu còn chưa phân bổ" + (": " + advance["description"] if advance["description"] else ""),
                    None, advance["amount"], None, None]})
        for group in advance_groups.values():
            customer, currency = group["customer"], group["currency"]
            rows.append({"kind": "customer", "label": "TIỀN THU CHƯA PHÂN BỔ | " + (customer.ref + " - " if customer.ref else "") + customer.name,
                "currency": currency})
            rows.append({"kind": "currency", "label": "Loại tiền: " + currency.name, "currency": currency})
            rows.extend(group["rows"])
            rows.append({"kind": "advance_total", "label": "CỘNG TIỀN CHƯA PHÂN BỔ | " + currency.name,
                "currency": currency, "totals": [None, group["amount"], None]})
        if len(rows) > 20000:
            raise UserError("Báo cáo có hơn 20.000 dòng. Hãy thu hẹp bộ lọc.")
        return {"wizard": self, "rows": rows, "headers": COLLECTION_HEADERS}

    def action_print_pdf(self):
        if self.report_type != "collection":
            return super().action_print_pdf()
        self._get_collection_data()
        return self.env.ref("ps_sale_report.action_sale_collection_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "collection":
            return super().action_export_xlsx()
        data = self._get_collection_data()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False,
            "default_format_properties": {"font_name": "Times New Roman", "font_size": 11}})
        sheet = book.add_worksheet("Thu tien khach hang")
        base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter"}
        heading = book.add_format({**base, "bold": True, "align": "center", "text_wrap": True, "bg_color": "#EDF1F6"})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        sheet.merge_range(0, 0, 0, 7, self.company_id.name)
        sheet.merge_range(1, 0, 1, 7, "BÁO CÁO SỐ DƯ TỪNG HÓA ĐƠN THEO KHÁCH HÀNG", title)
        sheet.set_row(1, 30)
        sheet.merge_range(2, 0, 2, 7, f"Từ ngày {self.date_from:%d/%m/%Y} đến ngày {self.date_to:%d/%m/%Y}", book.add_format({"align": "center"}))
        for col, width in enumerate([6, 30, 18, 75, 25, 25, 25, 18]):
            sheet.set_column(col, col, width)
            sheet.write_string(4, col, COLLECTION_HEADERS[col], heading)
        sheet.set_row(4, 35)
        formats = {}
        for index, row in enumerate(data["rows"], 5):
            digits = row["currency"].decimal_places
            category = "summary" if row["kind"] in ("invoice", "customer") else "total" if row["kind"] in ("total", "advance_total") else "normal"
            key = (digits, category)
            if key not in formats:
                properties = {**base}
                if category != "normal":
                    properties.update(bold=True, font_color="#0645AD" if category == "summary" else "#B91C1C", bg_color="#EDF1F6")
                formats[key] = {
                    "text": book.add_format({**properties, "text_wrap": True}),
                    "date": book.add_format({**properties, "num_format": "dd/mm/yyyy"}),
                    "number": book.add_format({**properties, "num_format": "#,##0" + ("." + "0" * digits if digits else "")}),
                    "integer": book.add_format({**properties, "num_format": "0", "align": "center"})}
            fmts = formats[key]
            if row["kind"] in ("customer", "currency"):
                sheet.merge_range(index, 0, index, 7, row["label"], fmts["text"])
                sheet.set_row(index, 27)
                continue
            if row["kind"] in ("total", "advance_total"):
                sheet.merge_range(index, 0, index, 3, row["label"], fmts["text"])
                for col, value in enumerate(row["totals"], 4):
                    sheet.write_blank(index, col, None, fmts["number"]) if value is None else sheet.write_number(index, col, value, fmts["number"])
                sheet.write_blank(index, 7, None, fmts["text"])
                sheet.set_row(index, 30)
                continue
            for col, value in enumerate(row["values"]):
                fmt = fmts["integer"] if col == 0 else fmts["date"] if col in (2, 7) else fmts["number"] if col in (4, 5, 6) else fmts["text"]
                if value is None or value == "":
                    sheet.write_blank(index, col, None, fmt)
                elif col in (2, 7):
                    sheet.write_datetime(index, col, datetime.combine(value, time.min), fmt)
                elif col in (0, 4, 5, 6):
                    sheet.write_number(index, col, value, fmt)
                else:
                    sheet.write_string(index, col, value, fmt)
            wrapped = max(max(1, (len(str(row["values"][c])) + width - 1) // width) for c, width in [(1, 25), (3, 65)])
            sheet.set_row(index, min(400, max(28, wrapped * 15)))
        last = len(data["rows"]) + 6
        self._write_xlsx_signature(book, sheet, last, 7)
        sheet.hide_gridlines(0)
        sheet.freeze_panes(5, 3)
        sheet.repeat_rows(4)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.print_area(0, 0, last + 1, 7)
        sheet.set_footer("&RTrang &P / &N")
        book.close()
        filename = f"Thu_tien_KH_{self.date_from}_{self.date_to}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self", "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
