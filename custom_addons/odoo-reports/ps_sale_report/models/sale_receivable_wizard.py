import base64
import io
from datetime import datetime, time

import xlsxwriter
from odoo import fields, models
from odoo.exceptions import UserError


RECEIVABLE_HEADERS = ["STT", "Số hóa đơn", "Ngày hóa đơn", "Diễn giải", "Trước thuế", "Sau thuế",
    "Giá trị thanh toán", "Giá trị còn lại", "Số CT thanh toán", "Ngày CT thanh toán", "Số hợp đồng SO"]


class SaleReceivableWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(selection_add=[("receivable", "Công nợ theo hóa đơn khách hàng"), ("tracking",)], ondelete={"receivable": "set default"})

    def _get_receivable_snapshot(self, allow_empty=False):
        self.ensure_one()
        self.check_access("read")
        if self.company_id not in self.env.companies:
            raise UserError("Bạn không có quyền truy cập công ty đã chọn.")
        # Preserve the accounting ACLs and record rules; Sales membership alone
        # never grants extra access to invoices or payment reconciliations.
        for name in ("account.move", "account.move.line", "account.partial.reconcile"):
            self.env[name].check_access("read")
        domain = [("company_id", "=", self.company_id.id), ("state", "=", "posted"),
            ("move_type", "in", ["out_invoice", "out_refund"]),
            ("invoice_date", ">=", self.date_from), ("invoice_date", "<=", self.date_to),
            ("date", "<=", self.date_to)]
        if self.partner_id:
            domain.append(("partner_id", "child_of", self.partner_id.id))
        invoices = self.env["account.move"].search(domain, order="commercial_partner_id, currency_id, invoice_date, name, id", limit=10001)
        if len(invoices) > 10000:
            raise UserError("Có hơn 10.000 hóa đơn. Hãy thu hẹp bộ lọc.")
        if not invoices and not allow_empty:
            raise UserError("Không có hóa đơn khách hàng hoặc điều chỉnh giảm đã ghi sổ trong khoảng ngày đã chọn.")
        receivable_lines = self.env["account.move.line"].search([
            ("move_id", "in", invoices.ids), ("account_id.account_type", "=", "asset_receivable"),
        ], limit=20001)
        partials = self.env["account.partial.reconcile"].search([
            ("company_id", "=", self.company_id.id), ("max_date", "<=", self.date_to),
            "|", ("debit_move_id", "in", receivable_lines.ids), ("credit_move_id", "in", receivable_lines.ids),
        ], order="max_date, id", limit=20001)
        if max(len(receivable_lines), len(partials)) > 20000:
            raise UserError("Có hơn 20.000 dòng công nợ hoặc đối trừ thanh toán. Hãy thu hẹp bộ lọc.")
        line_ids = set(receivable_lines.ids)
        settlements = {}
        for partial in partials:
            for source, other, value in [
                (partial.debit_move_id, partial.credit_move_id, partial.debit_amount_currency),
                (partial.credit_move_id, partial.debit_move_id, -partial.credit_amount_currency),
            ]:
                if source.id not in line_ids or other.move_id.state != "posted":
                    continue
                # Values are in the source invoice's currency, including FX
                # clearing/write-offs and credit-note offsets, not cash only.
                events = settlements.setdefault(source.move_id.id, {})
                key = (other.move_id.id, other.date)
                event = events.setdefault(key, {"amount": 0.0, "name": other.move_id.name, "date": other.date,
                    "description": other.move_id.ref or other.name or "", "move_type": other.move_id.move_type})
                event["amount"] += value
        # Read SO references through the normal Sales rules as well. Do not
        # disclose contract numbers from orders the current user cannot read.
        so_ids = invoices.invoice_line_ids.sale_line_ids.order_id.ids
        orders = self.env["sale.order"].search([("id", "in", so_ids)]) if so_ids else self.env["sale.order"]
        allowed_orders = set(orders.ids)
        return invoices, settlements, allowed_orders

    def _get_receivable_data(self):
        invoices, settlements, allowed_orders = self._get_receivable_snapshot()
        groups, currency_totals, seq = {}, {}, 0
        for invoice in invoices:
            currency = invoice.currency_id
            customer = invoice.commercial_partner_id
            key = (customer.id, currency.id)
            label = "Mã KH: %s - Tên KH: %s | %s" % (customer.ref or "", customer.name, currency.name)
            group = groups.setdefault(key, {"label": label, "currency": currency, "totals": [0.0] * 4, "items": []})
            events = sorted(settlements.get(invoice.id, {}).values(), key=lambda v: (v["date"], v["name"]))
            paid = currency.round(sum(v["amount"] for v in events))
            sign = -1 if invoice.move_type == "out_refund" else 1
            net, gross = sign * invoice.amount_untaxed, sign * invoice.amount_total
            remaining = currency.round(gross - paid)
            totals = [net, gross, paid, remaining]
            group["totals"] = [a + b for a, b in zip(group["totals"], totals)]
            currency_totals.setdefault(currency.id, {"currency": currency, "totals": [0.0] * 4})
            currency_totals[currency.id]["totals"] = [a + b for a, b in zip(currency_totals[currency.id]["totals"], totals)]
            linked = invoice.invoice_line_ids.sale_line_ids.order_id.filtered(lambda o: o.id in allowed_orders)
            contracts = ", ".join(sorted(set(o.ps_contract_ref or o.name for o in linked)))
            description = invoice.ref or invoice.payment_reference or invoice.invoice_origin or ""
            if sign == -1:
                description = "Điều chỉnh giảm" + (": " + description if description else "")
            seq += 1
            for index, event in enumerate(events or [None]):
                group["items"].append({"kind": "item", "currency": currency,
                    "values": [seq, invoice.name, invoice.invoice_date, description if index == 0 else "Thanh toán / Đối trừ (tiếp)",
                        net if index == 0 else None, gross if index == 0 else None,
                        currency.round(event["amount"]) if event else 0.0, remaining if index == 0 else None,
                        event["name"] if event else "", event["date"] if event else None, contracts]})
        rows = []
        for group in groups.values():
            rows.append({"kind": "customer", "label": group["label"], "currency": group["currency"], "totals": group["totals"]})
            rows.extend(group["items"])
        for value in currency_totals.values():
            rows.append({"kind": "total", "label": "TỔNG CỘNG | " + value["currency"].name, **value})
        if len(rows) > 20000:
            raise UserError("Báo cáo có hơn 20.000 dòng. Hãy thu hẹp bộ lọc.")
        return {"wizard": self, "rows": rows, "headers": RECEIVABLE_HEADERS}

    def action_print_pdf(self):
        if self.report_type != "receivable":
            return super().action_print_pdf()
        self._get_receivable_data()
        return self.env.ref("ps_sale_report.action_sale_receivable_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "receivable":
            return super().action_export_xlsx()
        data = self._get_receivable_data()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False,
            "default_format_properties": {"font_name": "Times New Roman", "font_size": 11}})
        sheet = book.add_worksheet("Cong no hoa don KH")
        base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter"}
        text = book.add_format({**base, "text_wrap": True})
        integer = book.add_format({**base, "align": "center", "num_format": "0"})
        date_fmt = book.add_format({**base, "num_format": "dd/mm/yyyy"})
        heading = book.add_format({**base, "bold": True, "align": "center", "text_wrap": True, "bg_color": "#EDF1F6"})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        center = book.add_format({"align": "center"})
        sheet.merge_range(0, 0, 0, 10, self.company_id.name)
        sheet.merge_range(1, 0, 1, 10, "BÁO CÁO CÔNG NỢ THEO HÓA ĐƠN - KHÁCH HÀNG", title)
        sheet.set_row(1, 30)
        sheet.merge_range(2, 0, 2, 10, f"Từ ngày {self.date_from:%d/%m/%Y} đến ngày {self.date_to:%d/%m/%Y}", center)
        for col, width in enumerate([6, 26, 17, 45, 23, 23, 23, 23, 30, 20, 30]):
            sheet.set_column(col, col, width)
        for col, label in enumerate(RECEIVABLE_HEADERS):
            if col in (4, 5):
                sheet.write_string(5, col, label, heading)
            else:
                sheet.merge_range(4, col, 5, col, label, heading)
        sheet.merge_range(4, 4, 4, 5, "Giá trị hóa đơn", heading)
        sheet.set_row(4, 25)
        sheet.set_row(5, 30)
        formats = {}
        for row_index, row in enumerate(data["rows"], 6):
            digits = row["currency"].decimal_places
            if digits not in formats:
                number_format = "#,##0" + ("." + "0" * digits if digits else "")
                formats[digits] = {"number": book.add_format({**base, "num_format": number_format})}
                for kind, color in [("customer", "#0645AD"), ("total", "#B91C1C")]:
                    formats[digits][kind] = book.add_format({**base, "bold": True, "font_color": color, "text_wrap": True, "bg_color": "#EDF1F6"})
                    formats[digits][kind + "_number"] = book.add_format({**base, "bold": True, "font_color": color, "bg_color": "#EDF1F6", "num_format": number_format})
            if row["kind"] != "item":
                fmt = formats[digits][row["kind"]]
                sheet.merge_range(row_index, 0, row_index, 3, row["label"], fmt)
                for col, value in enumerate(row["totals"], 4):
                    sheet.write_number(row_index, col, value, formats[digits][row["kind"] + "_number"])
                sheet.merge_range(row_index, 8, row_index, 10, "", fmt)
                sheet.set_row(row_index, 32)
                continue
            for col, value in enumerate(row["values"]):
                fmt = integer if col == 0 else date_fmt if col in (2, 9) else formats[digits]["number"] if col in (4, 5, 6, 7) else text
                if value is None or value == "":
                    sheet.write_blank(row_index, col, None, fmt)
                elif col in (2, 9):
                    sheet.write_datetime(row_index, col, datetime.combine(value, time.min), fmt)
                elif col in (0, 4, 5, 6, 7):
                    sheet.write_number(row_index, col, value, fmt)
                else:
                    sheet.write_string(row_index, col, value, fmt)
            wrapped = max(max(1, (len(str(row["values"][c])) + width - 1) // width) for c, width in [(1, 24), (3, 40), (8, 25), (10, 25)])
            sheet.set_row(row_index, min(400, max(30, wrapped * 15)))
        last = len(data["rows"]) + 7
        self._write_xlsx_signature(book, sheet, last, 10)
        sheet.hide_gridlines(0)
        sheet.freeze_panes(6, 3)
        sheet.repeat_rows(4, 5)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.print_area(0, 0, last + 1, 10)
        sheet.set_footer("&RTrang &P / &N")
        book.close()
        filename = f"Cong_no_hoa_don_KH_{self.date_from}_{self.date_to}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self", "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
