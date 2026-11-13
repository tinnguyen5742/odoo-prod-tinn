import base64
import io
from datetime import datetime, time, timedelta

import pytz
import xlsxwriter
from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


DELIVERY_COLUMNS = [
    ("Số đơn hàng", "text"), ("Tên khách hàng", "text"), ("Quy cách", "text"), ("ĐVT", "text"),
    ("Đơn hàng", "number"), ("Đã giao", "number"), ("Còn lại", "number"),
    ("Xuất dự kiến", "number"), ("Xuất thực tế", "number"), ("Phân xưởng", "text"),
    ("Tuyến đường", "text"), ("PTVC", "text"), ("Trạng thái", "text"),
    ("Dự kiến ngày", "date"), ("Dự kiến giờ", "text"), ("Địa chỉ", "text"), ("Ghi chú", "text"),
]


class SaleDeliveryWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(selection_add=[("delivery", "Kế hoạch giao hàng")], ondelete={"delivery": "set default"})

    def _get_delivery_data(self):
        self.ensure_one()
        self.check_access("read")
        if self.company_id not in self.env.companies:
            raise UserError("Công ty không thuộc phạm vi đang được phép truy cập.")
        tz = pytz.timezone(self.env.context.get("tz") or self.env.user.tz or "UTC")
        start = tz.localize(datetime.combine(self.date_from, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        end = tz.localize(datetime.combine(self.date_to + timedelta(days=1), time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        order_domain = [("company_id", "=", self.company_id.id), ("state", "=", "sale")]
        if self.partner_id:
            order_domain.append(("partner_id", "child_of", self.partner_id.id))
        if self.tracking_order_id:
            order_domain.append(("id", "=", self.tracking_order_id.id))
        orders = self.env["sale.order"].search(order_domain)
        domain = [("order_id", "in", orders.ids), ("state", "!=", "cancel"),
                  ("planned_datetime", ">=", start), ("planned_datetime", "<", end)]
        if self.product_id:
            domain.append(("sale_line_id.product_id", "=", self.product_id.id))
        plans = self.env["ps.sale.delivery.plan"].search(domain, limit=10001)
        if len(plans) > 10000:
            raise UserError("Có hơn 10.000 đợt giao. Hãy thu hẹp bộ lọc.")
        if not plans:
            raise UserError("Không có kế hoạch giao hàng trong khoảng ngày dự kiến đã chọn.")
        delivered = plans.sale_line_id.with_context(accrual_entry_date=self.report_date)._prepare_qty_delivered()
        rows = []
        for plan in plans:
            line = plan.sale_line_id
            actual = plan._actual_quantity(self.report_date)
            done = delivered.get(line, 0.0)
            status = "Đã giao đủ" if float_compare(actual, plan.planned_qty, precision_rounding=line.product_uom_id.rounding) >= 0 else "Giao một phần" if actual else dict(plan._fields["state"].selection)[plan.state]
            local = fields.Datetime.context_timestamp(self, plan.planned_datetime)
            rows.append([plan.order_id.name, plan.order_id.partner_id.name,
                         line.ps_specification or line.product_id.display_name, line.product_uom_id.name,
                         line.product_uom_qty, done, line.product_uom_qty - done, plan.planned_qty, actual,
                         plan.workshop or "", plan.route or "", plan.vehicle or "", status,
                         local.date(), local.strftime("%H:%M"), plan.address or "", plan.note or ""])
        return {"wizard": self, "rows": rows, "columns": DELIVERY_COLUMNS}

    def action_print_pdf(self):
        if self.report_type != "delivery":
            return super().action_print_pdf()
        self._get_delivery_data()
        return self.env.ref("ps_sale_report.action_sale_delivery_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "delivery":
            return super().action_export_xlsx()
        data = self._get_delivery_data()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False,
            "default_format_properties": {"font_name": "Times New Roman", "font_size": 11}})
        sheet = book.add_worksheet("Ke hoach giao hang")
        base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter"}
        text = book.add_format({**base, "text_wrap": True})
        number = book.add_format({**base, "num_format": "#,##0.00"})
        date = book.add_format({**base, "num_format": "dd/mm/yyyy", "align": "center"})
        hour = book.add_format({**base, "num_format": "hh:mm", "align": "center"})
        heading = book.add_format({**base, "bold": True, "align": "center", "bg_color": "#EDF1F6", "text_wrap": True})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        center = book.add_format({"align": "center"})
        widths = [16, 30, 42, 10, 14, 14, 14, 14, 14, 20, 22, 22, 20, 16, 14, 45, 35]
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width)
        sheet.merge_range(0, 0, 0, 16, self.company_id.name)
        sheet.merge_range(1, 0, 1, 16, "DỰ KIẾN KẾ HOẠCH GIAO HÀNG", title)
        sheet.set_row(1, 30)
        sheet.merge_range(2, 0, 2, 16, f"Từ ngày {self.date_from:%d/%m/%Y} đến ngày {self.date_to:%d/%m/%Y}", center)
        for first, last, label in [(4, 8, "Số lượng"), (12, 14, "Thời gian giao hàng")]:
            sheet.merge_range(4, first, 4, last, label, heading)
        for col, (label, kind) in enumerate(DELIVERY_COLUMNS):
            if col in range(4, 9) or col in range(12, 15):
                sheet.write_string(5, col, label, heading)
            else:
                sheet.merge_range(4, col, 5, col, label, heading)
        sheet.set_row(4, 25)
        sheet.set_row(5, 30)
        for row_index, values in enumerate(data["rows"], 6):
            for col, value in enumerate(values):
                kind = DELIVERY_COLUMNS[col][1]
                if col == 14:
                    parts = value.split(":")
                    sheet.write_number(row_index, col, (int(parts[0]) * 60 + int(parts[1])) / 1440, hour)
                elif kind == "date":
                    sheet.write_datetime(row_index, col, datetime.combine(value, time.min), date)
                elif kind == "number":
                    sheet.write_number(row_index, col, value, number)
                else:
                    sheet.write_string(row_index, col, value, text)
            lines = max(max(1, sum(max(1, (len(p) + widths[c] - 2) // (widths[c] - 1)) for p in str(v).split("\n"))) for c, v in enumerate(values))
            sheet.set_row(row_index, min(400, max(30, lines * 15)))
        last = len(data["rows"]) + 7
        self._write_xlsx_signature(book, sheet, last, 16)
        sheet.hide_gridlines(0)
        sheet.freeze_panes(6, 2)
        sheet.repeat_rows(4, 5)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.print_area(0, 0, last + 1, 16)
        sheet.set_footer("&RTrang &P / &N")
        book.close()
        filename = f"Ke_hoach_giao_hang_{self.date_from}_{self.date_to}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self", "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
