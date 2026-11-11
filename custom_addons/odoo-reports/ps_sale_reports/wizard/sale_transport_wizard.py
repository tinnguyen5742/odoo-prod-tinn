import base64
import io
from datetime import datetime, time, timedelta

import pytz
import xlsxwriter
from odoo import fields, models
from odoo.exceptions import UserError


TRANSPORT_HEADERS = ["STT", "Ngày CT", "Số phiếu vận chuyển", "Tuyến đường / Nơi đến", "Kho nhận",
    "Mã - Tên khách hàng", "Đơn hàng", "Kg", "Thùng / Bao / Kiện", "ĐVT", "Đơn giá VC", "Trung chuyển", "Phí khác", "Thành tiền"]


class SaleTransportWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(selection_add=[("transport", "Bảng kê chi tiết vận chuyển")], ondelete={"transport": "set default"})
    transport_owner_id = fields.Many2one("res.partner", string="Chủ xe / Đơn vị vận chuyển", check_company=True)

    def _get_transport_data(self):
        self.ensure_one()
        self.check_access("read")
        if self.company_id not in self.env.companies:
            raise UserError("Bạn không có quyền truy cập công ty đã chọn.")
        tz = pytz.timezone(self.env.context.get("tz") or self.env.user.tz or "UTC")
        start = tz.localize(datetime.combine(self.date_from, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        end = tz.localize(datetime.combine(self.date_to + timedelta(days=1), time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        domain = [("company_id", "=", self.company_id.id), ("state", "!=", "cancel"),
                  ("order_id.state", "=", "sale"), ("planned_datetime", ">=", start), ("planned_datetime", "<", end)]
        if self.partner_id:
            domain.append(("order_id.partner_id", "child_of", self.partner_id.id))
        if self.transport_owner_id:
            domain.append(("transport_owner_id", "=", self.transport_owner_id.id))
        plans = self.env["ps.sale.delivery.plan"].search(domain, order="transport_owner_id, planned_datetime, id", limit=10001)
        if len(plans) > 10000:
            raise UserError("Có hơn 10.000 đợt vận chuyển. Hãy thu hẹp bộ lọc.")
        # Respect SO visibility even when another installed module broadens
        # delivery-plan access. Never use sudo for report source records.
        orders = self.env["sale.order"].search([("id", "in", plans.order_id.ids)])
        plans = plans.filtered(lambda p: p.order_id in orders)
        if not plans:
            raise UserError("Không có đợt giao hàng trong khoảng ngày dự kiến và bộ lọc đã chọn. Hãy nhập Kế hoạch giao hàng trên SO trước.")
        groups = {}
        seq = 0
        totals = [0.0, 0.0, 0.0]
        for plan in plans:
            owner = plan.transport_owner_id
            group = groups.setdefault(owner.id or 0, {"label": "PTVC: " + (owner.display_name or "Chưa khai báo"), "totals": [0.0, 0.0, 0.0], "items": []})
            partner = plan.order_id.partner_id
            customer = ((partner.ref + " - ") if partner.ref else "") + partner.name
            pickings = plan.move_ids.filtered(lambda m: m.state != "cancel").picking_id
            reference = plan.transport_reference or ", ".join(pickings.sorted("name").mapped("name"))
            seq += 1
            group["items"].append({"kind": "item", "order_uom": plan.uom_id.name,
                "values": [seq, fields.Datetime.context_timestamp(self, plan.planned_datetime).date(), reference,
                    plan.route or plan.address or "", plan.transport_receiving_name or "", customer, plan.planned_qty,
                    plan.transport_weight, plan.transport_packages, plan.transport_charge_unit or "",
                    plan.transport_unit_price, plan.transport_transfer_fee, plan.transport_other_fee, plan.transport_amount]})
            sums = [plan.transport_weight, plan.transport_packages, plan.transport_amount]
            group["totals"] = [a + b for a, b in zip(group["totals"], sums)]
            totals = [a + b for a, b in zip(totals, sums)]
        rows = []
        for group in groups.values():
            rows.append({"kind": "carrier", "label": group["label"], "totals": group["totals"]})
            rows.extend(group["items"])
        rows.append({"kind": "total", "label": "TỔNG CỘNG", "totals": totals})
        return {"wizard": self, "rows": rows, "headers": TRANSPORT_HEADERS, "currency": self.company_id.currency_id}

    def action_print_pdf(self):
        if self.report_type != "transport":
            return super().action_print_pdf()
        self._get_transport_data()
        return self.env.ref("ps_sale_reports.action_sale_transport_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "transport":
            return super().action_export_xlsx()
        data = self._get_transport_data()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False,
            "default_format_properties": {"font_name": "Times New Roman", "font_size": 11}})
        sheet = book.add_worksheet("Chi tiet van chuyen")
        base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter"}
        text = book.add_format({**base, "text_wrap": True})
        numbers = {2: book.add_format({**base, "num_format": "#,##0.00"}),
            3: book.add_format({**base, "num_format": "#,##0.000"}),
            0: book.add_format({**base, "num_format": "0", "align": "center"})}
        money_format = "#,##0" + ("." + "0" * data["currency"].decimal_places if data["currency"].decimal_places else "")
        money = book.add_format({**base, "num_format": money_format})
        date_fmt = book.add_format({**base, "num_format": "dd/mm/yyyy", "align": "center"})
        header = book.add_format({**base, "bold": True, "align": "center", "text_wrap": True, "bg_color": "#EDF1F6"})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        center = book.add_format({"align": "center"})
        sheet.merge_range(0, 0, 0, 13, self.company_id.name)
        sheet.merge_range(1, 0, 1, 13, "BẢNG KÊ CHI TIẾT VẬN CHUYỂN", title)
        sheet.set_row(1, 30)
        sheet.merge_range(2, 0, 2, 13, f"Từ ngày {self.date_from:%d/%m/%Y} đến ngày {self.date_to:%d/%m/%Y}", center)
        sheet.merge_range(3, 0, 3, 13, "ĐVT tiền: " + data["currency"].name, book.add_format({"align": "right"}))
        widths = [6, 16, 25, 32, 38, 38, 23, 17, 18, 16, 22, 22, 22, 25]
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width)
        sheet.merge_range(4, 0, 4, 5, "", header)
        sheet.merge_range(4, 6, 4, 8, "Số lượng / Trọng lượng / Thể tích", header)
        sheet.merge_range(4, 9, 4, 12, "Chi phí vận chuyển dịch vụ thuê", header)
        sheet.write_blank(4, 13, None, header)
        for col, label in enumerate(TRANSPORT_HEADERS):
            sheet.write_string(5, col, label, header)
        sheet.set_row(4, 25)
        sheet.set_row(5, 35)
        unit_formats = {}
        for row_index, row in enumerate(data["rows"], 6):
            if row["kind"] != "item":
                color = "#0645AD" if row["kind"] == "carrier" else "#B91C1C"
                summary = book.add_format({**base, "bold": True, "font_color": color, "bg_color": "#EDF1F6", "text_wrap": True})
                sheet.merge_range(row_index, 0, row_index, 6, row["label"], summary)
                for col, value, fmt in [(7, row["totals"][0], "#,##0.000"), (8, row["totals"][1], "#,##0.00"), (13, row["totals"][2], money_format)]:
                    sheet.write_number(row_index, col, value, book.add_format({**base, "bold": True, "font_color": color, "bg_color": "#EDF1F6", "num_format": fmt}))
                sheet.merge_range(row_index, 9, row_index, 12, "", summary)
                sheet.set_row(row_index, 28)
                continue
            values = row["values"]
            unit = row["order_uom"].replace('"', "'").replace("\\", "/")
            if unit not in unit_formats:
                unit_formats[unit] = book.add_format({**base, "num_format": '#,##0.00 "' + unit + '"'})
            for col, value in enumerate(values):
                if col == 1:
                    sheet.write_datetime(row_index, col, datetime.combine(value, time.min), date_fmt)
                elif col == 0 or col in (6, 7, 8, 10, 11, 12, 13):
                    fmt = numbers[0] if col == 0 else unit_formats[unit] if col == 6 else numbers[3] if col == 7 else numbers[2] if col == 8 else money
                    sheet.write_number(row_index, col, value, fmt)
                else:
                    sheet.write_string(row_index, col, value, text)
            height = max(max(1, sum(max(1, (len(p) + widths[c] - 2) // (widths[c] - 1)) for p in str(values[c]).split("\n"))) for c in (2, 3, 4, 5, 9))
            sheet.set_row(row_index, min(400, max(30, height * 15)))
        last = len(data["rows"]) + 7
        self._write_xlsx_signature(book, sheet, last, 13)
        sheet.hide_gridlines(0)
        sheet.freeze_panes(6, 3)
        sheet.repeat_rows(4, 5)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.print_area(0, 0, last + 1, 13)
        sheet.set_footer("&RTrang &P / &N")
        book.close()
        filename = f"Chi_tiet_van_chuyen_{self.date_from}_{self.date_to}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self", "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
