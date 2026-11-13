import base64
import io

import xlsxwriter
from odoo import fields, models
from odoo.exceptions import UserError


REQUEST_COLUMNS = [
    ("STT", "number"), ("Số SO", "text"), ("Mã hàng", "text"), ("Tên hàng", "text"),
    ("ĐVT", "text"), ("Số lượng SO", "number"), ("Số đề nghị xuất kho", "text"),
    ("Số lượng đề nghị", "number"), ("Số phiếu xuất", "text"), ("Số lượng xuất", "number"),
]


class SaleRequestWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(
        selection_add=[("request", "Theo dõi đề nghị xuất bán"), ("finished",)],
        ondelete={"request": "set default"},
    )

    def _get_request_data(self):
        self.ensure_one()
        if self.report_type != "request":
            raise UserError("Chọn báo cáo Theo dõi đề nghị xuất bán.")
        # Keep the existing date/company validation and timezone-aware SO range.
        domain = [term for term in self._get_domain() if term[0] not in ("order_id.state", "order_id.partner_id")]
        domain += [("order_id.state", "in", ["draft", "sent", "sale"]), ("product_id.type", "=", "consu")]
        if self.tracking_order_id:
            domain.append(("order_id", "=", self.tracking_order_id.id))
        # Apply SO rules explicitly even if stock grants broader SOL access.
        orders = self.env["sale.order"].search([
            ("company_id", "=", self.company_id.id), ("order_line", "any", domain),
        ], limit=10001)
        lines = self.env["sale.order.line"].search(
            domain + [("order_id", "in", orders.ids)], order="order_id, sequence, id", limit=10001,
        )
        if not lines:
            raise UserError("Không có dòng hàng hóa SO phù hợp với bộ lọc ngày SO đã chọn.")
        moves = self.env["stock.move"].search([
            ("sale_line_id", "in", lines.ids), ("company_id", "=", self.company_id.id),
            ("state", "!=", "cancel"), ("picking_id.picking_type_id.code", "=", "outgoing"),
            ("location_dest_id.usage", "=", "customer"), ("location_id.usage", "!=", "customer"),
            ("origin_returned_move_id", "=", False),
        ], order="picking_id, id", limit=10001)
        if max(len(orders), len(lines), len(moves)) > 10000:
            raise UserError("Có hơn 10.000 SO, dòng SO hoặc dòng kho. Hãy thu hẹp bộ lọc.")
        by_line = {}
        for move in moves:
            by_line.setdefault(move.sale_line_id.id, []).append(move)
        rows = []

        def append(line, move=None, so_quantity=None, component=False):
            product = move.product_id if component else line.product_id
            uom = move.product_uom if component else line.product_uom_id
            name = product.with_context(display_default_code=False).display_name
            if component:
                name += " (theo SO: " + line.product_id.name + ")"
            ref, request_qty, picking, shipped = "", None, "", None
            if move:
                ref = move.ps_execution_request_ref or ""
                if ref:
                    request_qty = move.product_uom._compute_quantity(move.ps_execution_request_qty, uom, round=False)
                done_day = fields.Datetime.context_timestamp(self, move.date).date() if move.date else None
                if move.state == "done" and done_day and done_day <= self.date_to:
                    picking = move.picking_id.name
                    shipped = move.product_uom._compute_quantity(move.quantity, uom, round=False)
            rows.append([len(rows) + 1, line.order_id.name, product.default_code or "", name,
                         uom.name, so_quantity, ref, request_qty, picking, shipped])
            if len(rows) > 10000:
                raise UserError("Có hơn 10.000 dòng báo cáo. Hãy thu hẹp bộ lọc.")

        for line in lines:
            line_moves = by_line.get(line.id, [])
            same_product = [move for move in line_moves if move.product_id == line.product_id]
            for index, move in enumerate(same_product or [None]):
                append(line, move, line.product_uom_qty if index == 0 else None)
            # Kit requests are entered on component moves. Keep those quantities
            # in their own UOM instead of treating components as sold kits.
            for move in line_moves:
                if move.product_id != line.product_id:
                    append(line, move, component=True)
        return {"wizard": self, "rows": rows, "columns": REQUEST_COLUMNS,
                "order_filter": self.tracking_order_id.name or "", "product_filter": self.product_id.display_name or ""}

    def action_print_pdf(self):
        if self.report_type != "request":
            return super().action_print_pdf()
        self._get_request_data()
        return self.env.ref("ps_sale_report.action_sale_request_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "request":
            return super().action_export_xlsx()
        data = self._get_request_data()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False,
            "strings_to_urls": False, "default_format_properties": {"font_name": "Times New Roman", "font_size": 11}})
        sheet = book.add_worksheet("Theo doi de nghi xuat ban")
        base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter"}
        text = book.add_format({**base, "text_wrap": True})
        number = book.add_format({**base, "num_format": "#,##0.00"})
        integer = book.add_format({**base, "align": "center", "num_format": "0"})
        heading = book.add_format({**base, "bold": True, "align": "center", "bg_color": "#EDF1F6", "text_wrap": True})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        centered = book.add_format({"italic": True, "align": "center"})
        meta = book.add_format({"text_wrap": True})
        for col, width in enumerate([6, 18, 20, 55, 12, 18, 27, 20, 27, 20]):
            sheet.set_column(col, col, width)
        sheet.merge_range(0, 0, 0, 9, self.company_id.name, meta)
        sheet.merge_range(1, 0, 1, 9, "THEO DÕI ĐỀ NGHỊ XUẤT BÁN", title)
        sheet.set_row(1, 28)
        sheet.merge_range(2, 0, 2, 9, f"Từ ngày {self.date_from:%d/%m/%Y} đến ngày {self.date_to:%d/%m/%Y}", centered)
        filters = [label + value for label, value in [("SO: ", data["order_filter"]), ("Sản phẩm: ", data["product_filter"])] if value]
        sheet.merge_range(3, 0, 3, 9, " | ".join(filters), meta)
        for col, (label, kind) in enumerate(REQUEST_COLUMNS):
            sheet.write_string(5, col, label, heading)
        sheet.set_row(5, 32)
        for row, values in enumerate(data["rows"], 6):
            for col, value in enumerate(values):
                fmt = integer if col == 0 else number if REQUEST_COLUMNS[col][1] == "number" else text
                if value is None or value is False or value == "":
                    sheet.write_blank(row, col, None, fmt)
                elif REQUEST_COLUMNS[col][1] == "number":
                    sheet.write_number(row, col, value, fmt)
                else:
                    sheet.write_string(row, col, value, fmt)
            height = max(2, max(sum(max(1, (len(part) + width - 1) // width) for part in str(values[col]).split("\n"))
                              for col, width in [(1, 16), (2, 18), (3, 50), (4, 10), (6, 24), (8, 24)]))
            sheet.set_row(row, min(300, height * 15))
        last = len(data["rows"]) + 7
        self._write_xlsx_signature(book, sheet, last, 9)
        sheet.hide_gridlines(0)
        sheet.freeze_panes(6, 0)
        sheet.repeat_rows(5)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.print_area(0, 0, last + 1, 9)
        sheet.set_footer("&RTrang &P / &N")
        book.close()
        filename = f"Theo_doi_de_nghi_xuat_ban_{self.date_from}_{self.date_to}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self",
                "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
