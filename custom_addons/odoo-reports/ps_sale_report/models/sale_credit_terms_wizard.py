import base64
import io

import xlsxwriter
from odoo import fields, models
from odoo.exceptions import UserError


CREDIT_TERMS_COLUMNS = [("STT", "number"), ("Mã ĐTPN", "text"), ("Tên khách hàng", "text"),
    ("Thời hạn thanh toán", "text"), ("Hạn mức", "number"), ("Ghi chú", "text")]


class SaleCreditTermsWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(selection_add=[("credit_terms", "Bảng kê thời hạn công nợ bán ra"), ("transport",)], ondelete={"credit_terms": "set default"})

    def _credit_term_description(self, term):
        if not term:
            return "Chưa khai báo"
        lines = term.line_ids.sorted(lambda line: line.id)
        if len(lines) == 1 and lines.value == "percent" and lines.value_amount == 100 and lines.delay_type == "days_after" and not term.early_discount:
            return "Thanh toán ngay" if not lines.nb_days else "%s (ngày)" % lines.nb_days
        descriptions = []
        for line in lines:
            days = line.nb_days
            if line.delay_type == "days_after_end_of_month":
                delay = "%s ngày sau cuối tháng hóa đơn" % days
            elif line.delay_type == "days_after_end_of_next_month":
                delay = "%s ngày sau cuối tháng kế tiếp" % days
            elif line.delay_type == "days_end_of_month_on_the":
                try:
                    month_day = int(line.days_next_month)
                except (TypeError, ValueError):
                    month_day = 1
                delay = ("Sau %s ngày, ngày %s của tháng kế tiếp" % (days, month_day)) if month_day > 0 else ("Cuối tháng chứa ngày sau hóa đơn %s ngày" % days)
            else:
                delay = "Thanh toán ngay" if not days else "Sau %s ngày" % days
            portion = "%g%%" % line.value_amount if line.value == "percent" else "Cố định %g" % line.value_amount
            descriptions.append(portion + ": " + delay)
        if term.early_discount:
            descriptions.append("Chiết khấu thanh toán %g%% trong %s ngày" % (term.discount_percentage, term.discount_days))
        return term.name + ("\n" + "\n".join(descriptions) if descriptions else "")

    def _get_credit_terms_data(self):
        self.ensure_one()
        self.check_access("read")
        if self.company_id not in self.env.companies:
            raise UserError("Bạn không có quyền truy cập công ty đã chọn.")
        if not (self.env.user.has_group("account.group_account_invoice") or self.env.user.has_group("account.group_account_readonly")):
            raise UserError("Cần quyền đọc dữ liệu kế toán để xem hạn mức công nợ khách hàng.")
        Partner = self.env["res.partner"].with_company(self.company_id)
        if self.partner_id:
            ids = self.partner_id.commercial_partner_id.ids
        else:
            ids = set(Partner.search([("customer_rank", ">", 0), ("company_id", "in", [False, self.company_id.id])]).commercial_partner_id.ids)
            # Also include customers with visible quotations/SOs or invoices,
            # even when imported data has not updated customer_rank yet.
            for model, field, domain in [
                ("sale.order", "partner_id", [("company_id", "=", self.company_id.id), ("state", "!=", "cancel")]),
                ("account.move", "commercial_partner_id", [("company_id", "=", self.company_id.id),
                    ("move_type", "in", ["out_invoice", "out_refund"]), ("state", "!=", "cancel")]),
            ]:
                for (partner,) in self.env[model]._read_group(domain, [field], []):
                    if partner:
                        ids.add(partner.commercial_partner_id.id)
        partners = Partner.search([("id", "in", list(ids)), ("active", "=", True),
            ("company_id", "in", [False, self.company_id.id])], order="ref, name, id", limit=10001)
        if len(partners) > 10000:
            raise UserError("Có hơn 10.000 khách hàng. Hãy chọn khách hàng trước khi xuất.")
        if not partners:
            raise UserError("Không có khách hàng phù hợp với công ty và bộ lọc đã chọn.")
        rows = []
        for partner in partners:
            term = partner.property_payment_term_id
            if term.company_id and term.company_id != self.company_id:
                raise UserError("Điều khoản thanh toán của %s thuộc công ty khác. Hãy kiểm tra hồ sơ khách hàng." % partner.name)
            rows.append([len(rows) + 1, partner.ref or "", partner.name,
                self._credit_term_description(term), partner.credit_limit, partner.ps_sale_credit_note or ""])
        return {"wizard": self, "rows": rows, "columns": CREDIT_TERMS_COLUMNS, "currency": self.company_id.currency_id}

    def action_print_pdf(self):
        if self.report_type != "credit_terms":
            return super().action_print_pdf()
        self._get_credit_terms_data()
        return self.env.ref("ps_sale_report.action_sale_credit_terms_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "credit_terms":
            return super().action_export_xlsx()
        data = self._get_credit_terms_data()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False,
            "default_format_properties": {"font_name": "Times New Roman", "font_size": 11}})
        sheet = book.add_worksheet("Thoi han cong no ban ra")
        base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter"}
        text = book.add_format({**base, "text_wrap": True})
        integer = book.add_format({**base, "num_format": "0", "align": "center"})
        digits = data["currency"].decimal_places
        money = book.add_format({**base, "num_format": "#,##0" + ("." + "0" * digits if digits else "")})
        header = book.add_format({**base, "bold": True, "align": "center", "text_wrap": True, "bg_color": "#EDF1F6"})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        sheet.merge_range(0, 0, 0, 5, self.company_id.name)
        sheet.merge_range(1, 0, 1, 5, "BẢNG KÊ THỜI HẠN CÔNG NỢ BÁN RA", title)
        sheet.set_row(1, 30)
        sheet.merge_range(2, 0, 2, 5, "Ngày lập: %s | ĐVT tiền: %s" % (self.report_date.strftime("%d/%m/%Y"), data["currency"].name), book.add_format({"align": "center"}))
        widths = [6, 22, 58, 65, 25, 55]
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width)
            sheet.write_string(4, col, CREDIT_TERMS_COLUMNS[col][0], header)
        sheet.set_row(4, 30)
        for row_index, values in enumerate(data["rows"], 5):
            for col, value in enumerate(values):
                if col in (0, 4):
                    sheet.write_number(row_index, col, value, integer if col == 0 else money)
                else:
                    sheet.write_string(row_index, col, value, text)
            lines = max(sum(max(1, (len(p) + widths[c] - 3) // (widths[c] - 2)) for p in str(values[c]).split("\n")) for c in (1, 2, 3, 5))
            sheet.set_row(row_index, min(400, max(28, lines * 15)))
        last = len(data["rows"]) + 6
        self._write_xlsx_signature(book, sheet, last, 5)
        sheet.hide_gridlines(0)
        sheet.freeze_panes(5, 2)
        sheet.repeat_rows(4)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.print_area(0, 0, last + 1, 5)
        sheet.set_footer("&RTrang &P / &N")
        book.close()
        filename = f"Thoi_han_cong_no_ban_ra_{self.report_date}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self", "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
