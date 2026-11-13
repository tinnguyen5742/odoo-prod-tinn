import base64
import io
from datetime import datetime, time

import xlsxwriter
from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


# One schema keeps PDF, Excel and data selection in the same column order as Word.
TRACKING_COLUMNS = [
    ("seq", "STT", "number", 5),
    ("salesperson", "Tên nhân viên", "text", 20),
    ("customer", "Tên khách hàng", "text", 28),
    ("so", "Số SO", "text", 15),
    ("po", "Số PO KH", "text", 18),
    ("so_date", "Ngày SO", "date", 14),
    ("specification", "QCSP", "text", 18),
    ("code", "Mã hàng", "text", 16),
    ("product", "Tên hàng hóa", "text", 35),
    ("quantity", "SL", "number", 14),
    ("uom", "ĐVT (KH)", "text", 12),
    ("limit", "Hạn mức", "number", 14),
    ("m2", "SL theo M²", "number", 14),
    ("requested_date", "Ngày KH YC giao", "date", 15),
    ("receipt_date", "Ngày nhập kho", "date", 15),
    ("confirmation_date", "Ngày xác nhận KH", "date", 15),
    ("delivered", "SL đã giao", "number", 14),
    ("stock", "Tồn kho", "number", 14),
    ("unproduced", "SL chưa SX", "number", 14),
    ("structure", "Cấu trúc SP", "text", 22),
    ("price", "Đơn giá", "number", 18),
    ("value", "Trị giá", "number", 20),
    ("note", "Ghi chú", "text", 30),
]
TRACKING_NOTE = (
    "Lọc theo ngày SO. SL đã giao, tồn kho và tiến độ MRP tại thời điểm chạy báo cáo. "
    "Tồn kho là tổng tồn thực tế trong các vị trí nội bộ của công ty, gồm cả hàng đã giữ chỗ; "
    "quy đổi về ĐVT (KH) và lặp lại nếu sản phẩm có nhiều dòng SO. "
    "SL chưa SX = tổng phần còn phải sản xuất của các lệnh MRP gắn đúng dòng SO; "
    "loại lệnh hủy, lệnh hoàn tất còn 0. Ô trống là chưa có lệnh MRP phù hợp. "
    "Hạn mức và SL theo M² để trống khi chưa khai báo. Trị giá sau chiết khấu, gồm thuế; "
    "đơn giá theo SO. Loại tiền ghi kèm Số SO. Không cộng tồn lặp hoặc số liệu khác ĐVT/loại tiền."
)


class SaleTrackingWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(selection_add=[("tracking", "Theo dõi đơn hàng")], ondelete={"tracking": "set default"})
    tracking_order_id = fields.Many2one("sale.order", "Số SO", check_company=True)
    tracking_so_prefix = fields.Char("Tiền tố SO")
    tracking_line_status = fields.Selection([
        ("all", "Tất cả"), ("open", "Chưa giao đủ"), ("delivered", "Đã giao đủ"),
    ], string="Tình trạng line", required=True, default="all")

    def _get_domain(self):
        domain = super()._get_domain()
        if self.report_type == "tracking":
            domain.append(("product_id.type", "=", "consu"))
            if self.salesperson_id:
                domain.append(("order_id.user_id", "=", self.salesperson_id.id))
            if self.tracking_order_id:
                domain.append(("order_id", "=", self.tracking_order_id.id))
            if self.tracking_so_prefix:
                # =like adds no surrounding wildcards; user input is a literal prefix.
                prefix = self.tracking_so_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                domain.append(("order_id.name", "=like", prefix + "%"))
        return domain

    def _get_tracking_lines(self):
        self.ensure_one()
        if self.report_type != "tracking":
            raise UserError("Chọn báo cáo Theo dõi đơn hàng.")
        lines = self.env["sale.order.line"].search(self._get_domain(), order="order_id, sequence, id", limit=10001)
        if len(lines) > 10000:
            raise UserError("Có hơn 10.000 dòng. Thu hẹp bộ lọc để xem hoặc xuất báo cáo.")
        if self.tracking_line_status != "all":
            wanted = self.tracking_line_status == "delivered"
            lines = lines.filtered(lambda line: (
                float_compare(line.qty_delivered, line.product_uom_qty,
                              precision_rounding=line.product_uom_id.rounding) >= 0
            ) == wanted)
        if not lines:
            raise UserError("Không có dòng đơn bán đã xác nhận phù hợp với bộ lọc.")
        return lines

    def action_view_orders(self):
        if self.report_type != "tracking":
            return super().action_view_orders()
        lines = self._get_tracking_lines()
        # Resolve progress now so ACL errors surface before navigating away.
        lines.mapped("ps_tracking_unproduced_qty")
        return {
            "type": "ir.actions.act_window", "name": "Theo dõi đơn hàng",
            "res_model": "sale.order.line", "view_mode": "list",
            "views": [(self.env.ref("ps_sale_report.view_sale_tracking_line_list").id, "list")],
            "domain": [("id", "in", lines.ids)], "context": dict(self.env.context), "target": "current",
        }

    def _get_tracking_data(self):
        lines = self._get_tracking_lines()
        rows = []
        for seq, line in enumerate(lines, 1):
            rows.append({
                "seq": seq, "line_id": line.id, "salesperson": line.order_id.user_id.name or "",
                "customer": line.order_id.partner_id.display_name,
                "so": f"{line.order_id.name} | {line.currency_id.name}",
                "po": line.order_id.client_order_ref or "",
                "so_date": fields.Datetime.context_timestamp(self, line.order_id.date_order).date(),
                "specification": line.ps_specification or "", "code": line.product_id.default_code or "",
                "product": line.product_id.with_context(display_default_code=False).display_name,
                "quantity": line.product_uom_qty, "uom": line.product_uom_id.name,
                "limit": line.ps_tracking_quantity_limit or None,
                "m2": line.ps_tracking_quantity_m2 if line.ps_tracking_m2_factor else None,
                "requested_date": line.ps_requested_delivery_date,
                "receipt_date": line.ps_actual_receipt_date,
                "confirmation_date": line.ps_customer_confirmation_date,
                "delivered": line.qty_delivered, "stock": line.ps_tracking_stock_qty,
                "unproduced": line.ps_tracking_unproduced_qty if line.ps_tracking_has_mrp else None,
                "structure": line.ps_product_structure or "", "price": line.price_unit,
                "value": line.price_total, "note": line.ps_report_note or "",
            })
        filters = []
        for label, value in [("Sales", self.salesperson_id.display_name),
                             ("Khách hàng", self.partner_id.display_name),
                             ("Hàng hóa", self.product_id.display_name),
                             ("SO", self.tracking_order_id.display_name),
                             ("Tiền tố SO", self.tracking_so_prefix)]:
            if value:
                filters.append(f"{label}: {value}")
        filters.append("Tình trạng: " + dict(self._fields["tracking_line_status"].selection)[self.tracking_line_status])
        return {"wizard": self, "rows": rows, "columns": TRACKING_COLUMNS,
                "filters": " | ".join(filters), "note": TRACKING_NOTE}

    def action_print_pdf(self):
        if self.report_type != "tracking":
            return super().action_print_pdf()
        self._get_tracking_data()
        return self.env.ref("ps_sale_report.action_sale_tracking_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "tracking":
            return super().action_export_xlsx()
        data = self._get_tracking_data()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False, "default_format_properties": {"font_name": "Times New Roman", "font_size": 11}})
        sheet = book.add_worksheet("Theo doi don hang")
        base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter", "text_wrap": True}
        formats = {"text": book.add_format(base),
                   "number": book.add_format({**base, "num_format": "#,##0.00"}),
                   "date": book.add_format({**base, "num_format": "dd/mm/yyyy"})}
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        meta = book.add_format({"text_wrap": True, "valign": "top"})
        header = book.add_format({**base, "bold": True, "align": "center", "bg_color": "#EDF1F6"})
        sheet.merge_range(0, 0, 0, 22, self.company_id.name, meta)
        sheet.merge_range(1, 0, 1, 22, "BÁO CÁO THEO DÕI ĐƠN HÀNG", title)
        sheet.set_row(1, 28)
        sheet.merge_range(2, 0, 2, 22, f"Từ ngày {self.date_from:%d/%m/%Y} đến ngày {self.date_to:%d/%m/%Y}", meta)
        sheet.merge_range(3, 0, 3, 22, data["filters"], meta)
        sheet.set_row(3, 30)
        for col, (_, label, _, width) in enumerate(TRACKING_COLUMNS):
            sheet.set_column(col, col, width)
            sheet.write_string(5, col, label, header)
        sheet.set_row(5, 34)
        for row, item in enumerate(data["rows"], 6):
            height = 2
            for col, (key, _, kind, width) in enumerate(TRACKING_COLUMNS):
                value, fmt = item[key], formats[kind]
                if value is None or value is False or value == "":
                    sheet.write_blank(row, col, None, fmt)
                elif kind == "date":
                    sheet.write_datetime(row, col, datetime.combine(value, time.min), fmt)
                elif kind == "number":
                    sheet.write_number(row, col, value, fmt)
                else:
                    sheet.write_string(row, col, str(value), fmt)
                    height = max(height, sum(max(1, (len(s) + width - 3) // (width - 2)) for s in str(value).splitlines()))
            sheet.set_row(row, min(400, height * 15))
        end = len(data["rows"]) + 7
        self._write_xlsx_signature(book, sheet, end, 22)
        sheet.freeze_panes(6, 4)
        sheet.autofilter(5, 0, len(data["rows"]) + 5, 22)
        sheet.repeat_rows(5)
        sheet.hide_gridlines(0)
        sheet.set_landscape()
        sheet.set_paper(9)
        # Keep text readable when printing 23 columns: paginate horizontally.
        sheet.set_print_scale(70)
        sheet.print_area(0, 0, end + 1, 22)
        book.close()
        filename = f"Theo_doi_don_hang_{self.date_from}_{self.date_to}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self",
                "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
