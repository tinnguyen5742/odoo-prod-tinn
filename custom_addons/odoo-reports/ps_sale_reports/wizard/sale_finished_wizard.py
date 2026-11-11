import base64
import io

import xlsxwriter
from odoo import fields, models
from odoo.exceptions import UserError


class SaleFinishedWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(
        selection_add=[("finished", "Doanh thu – Số lượng theo thành phẩm xuất bán")],
        ondelete={"finished": "set default"},
    )

    def _get_finished_data(self):
        self.ensure_one()
        if self.report_type != "finished":
            raise UserError("Chọn báo cáo Doanh thu – Số lượng theo thành phẩm xuất bán.")
        filters = [("product_id", "=", self.product_id.id)] if self.product_id else []
        events = self._get_dispatch_quantities(self.date_from, self.date_to, filters)
        currency = self.company_id.currency_id
        groups = {}

        def new_totals():
            return {"m2": None, "others": {}, "revenue": 0.0}

        def add(target, m2, unit, quantity, revenue):
            if m2:
                target["m2"] = (target["m2"] or 0.0) + quantity
            else:
                other = target["others"].setdefault(unit.id, {"uom": unit.name, "quantity": 0.0})
                other["quantity"] += quantity
            target["revenue"] += revenue

        grand = new_totals()
        for event in events:
            line, day, shipped = event["line"], event["day"], event["quantity"]
            if not shipped:
                continue
            user, product = line.order_id.user_id, line.product_id
            quantity = line.product_uom_id._compute_quantity(shipped, product.uom_id, round=False)
            metric = bool(line.ps_tracking_m2_factor)
            if metric:
                quantity *= line.ps_tracking_m2_factor
            revenue = line.currency_id._convert(
                line.price_subtotal / line.product_uom_qty * shipped, currency, self.company_id, day,
            )
            group = groups.setdefault(user.id or 0, {"user": user, "items": {}, **new_totals()})
            item = group["items"].setdefault(product.id, {"product": product, **new_totals()})
            for target in (item, group, grand):
                add(target, metric, product.uom_id, quantity, revenue)
        if not groups:
            raise UserError("Không có phiếu giao hoàn tất hoặc phiếu trả cập nhật SO phù hợp trong khoảng ngày đã chọn.")

        def values(total):
            return {"m2": total["m2"], "others": sorted(total["others"].values(), key=lambda v: v["uom"]),
                    "revenue": currency.round(total["revenue"])}

        rows, seq = [], 0
        for group in sorted(groups.values(), key=lambda g: ((g["user"].name or "").casefold(), g["user"].id or 0)):
            user = group["user"]
            label = "NV Sales: " + ((user.ps_sales_code + " - " if user.ps_sales_code else "") + user.name if user else "Chưa phân công Sales")
            rows.append({"kind": "sales", "label": label, **values(group)})
            for item in sorted(group["items"].values(), key=lambda i: ((i["product"].default_code or "").casefold(), i["product"].name.casefold(), i["product"].id)):
                seq += 1
                product = item["product"]
                rows.append({"kind": "item", "seq": seq, "product_id": product.id,
                             "code": product.default_code or "", "label": product.name, **values(item)})
        rows.append({"kind": "total", "label": "TỔNG CỘNG", **values(grand)})
        return {"wizard": self, "rows": rows, "currency": currency,
                "sales_filter": self.salesperson_id.name or "", "product_filter": self.product_id.display_name or ""}

    def action_print_pdf(self):
        if self.report_type != "finished":
            return super().action_print_pdf()
        self._get_finished_data()
        return self.env.ref("ps_sale_reports.action_sale_finished_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "finished":
            return super().action_export_xlsx()
        data = self._get_finished_data()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False,
            "strings_to_urls": False, "default_format_properties": {"font_name": "Times New Roman", "font_size": 11}})
        sheet = book.add_worksheet("DT SL thanh pham xuat ban")
        money_fmt = "#,##0" + ("." + "0" * data["currency"].decimal_places if data["currency"].decimal_places else "")
        styles = {}
        for kind in ("item", "sales", "total"):
            base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter"}
            if kind != "item":
                base.update(bold=True)
            if kind == "sales":
                base["font_color"] = "#0645AD"
            elif kind == "total":
                base["bg_color"] = "#EDF1F6"
            styles[kind] = {
                "text": book.add_format({**base, "text_wrap": True}),
                "integer": book.add_format({**base, "num_format": "0", "align": "center"}),
                "quantity": book.add_format({**base, "num_format": "#,##0.00"}),
                "money": book.add_format({**base, "num_format": money_fmt}),
                "base": base,
            }
        heading = book.add_format({"border": 1, "border_color": "#94A3B8", "bold": True, "bg_color": "#EDF1F6", "align": "center", "valign": "vcenter"})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        centered = book.add_format({"align": "center", "italic": True})
        meta = book.add_format({"text_wrap": True})
        for col, width in enumerate([7, 20, 65, 20, 24, 25]):
            sheet.set_column(col, col, width)
        sheet.merge_range(0, 0, 0, 5, self.company_id.name, meta)
        sheet.merge_range(1, 0, 1, 5, "BÁO CÁO DOANH THU – SỐ LƯỢNG XUẤT BÁN", title)
        sheet.set_row(1, 28)
        sheet.merge_range(2, 0, 2, 5, "(Thành phẩm)", centered)
        sheet.merge_range(3, 0, 3, 5, f"Từ ngày {self.date_from:%d/%m/%Y} đến ngày {self.date_to:%d/%m/%Y} | ĐVT tiền: {data['currency'].name}", centered)
        filters = [label + value for label, value in [("Sales: ", data["sales_filter"]), ("Sản phẩm: ", data["product_filter"])] if value]
        sheet.merge_range(4, 0, 4, 5, " | ".join(filters), meta)
        for col, label in [(0, "STT"), (1, "Mã HH"), (2, "Tên hàng hóa"), (5, "Doanh thu")]:
            sheet.merge_range(6, col, 7, col, label, heading)
        sheet.merge_range(6, 3, 6, 4, "Số lượng", heading)
        sheet.write_string(7, 3, "M²", heading)
        sheet.write_string(7, 4, "Khác / ĐVT", heading)
        row, other_formats = 8, {}

        def write_block(start, end, col, value, fmt):
            if start != end:
                sheet.merge_range(start, col, end, col, "" if value is None else value, fmt)
            elif value is None:
                sheet.write_blank(start, col, None, fmt)
            elif isinstance(value, (int, float)):
                sheet.write_number(start, col, value, fmt)
            else:
                sheet.write_string(start, col, value, fmt)

        for entry in data["rows"]:
            style = styles[entry["kind"]]
            last = row + max(1, len(entry["others"])) - 1
            if entry["kind"] == "item":
                for col, value in [(0, entry["seq"]), (1, entry["code"]), (2, entry["label"])]:
                    write_block(row, last, col, value, style["integer"] if col == 0 else style["text"])
            else:
                sheet.merge_range(row, 0, last, 2, entry["label"], style["text"])
            write_block(row, last, 3, entry["m2"], style["quantity"])
            write_block(row, last, 5, entry["revenue"], style["money"])
            if entry["others"]:
                for offset, other in enumerate(entry["others"]):
                    key = (entry["kind"], other["uom"])
                    if key not in other_formats:
                        unit = other["uom"].replace("\\", "\\\\").replace('"', '\\"')
                        other_formats[key] = book.add_format({**style["base"], "num_format": '#,##0.00 "' + unit + '"'})
                    sheet.write_number(row + offset, 4, other["quantity"], other_formats[key])
            else:
                sheet.write_blank(row, 4, None, style["quantity"])
            height = max(26, min(300, 15 * max(1, (len(entry["label"]) + 58) // 59)))
            for line in range(row, last + 1):
                sheet.set_row(line, height)
            row = last + 1
        self._write_xlsx_signature(book, sheet, row + 1, 5)
        sheet.freeze_panes(8, 0)
        sheet.repeat_rows(6, 7)
        sheet.hide_gridlines(0)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.print_area(0, 0, row + 2, 5)
        sheet.set_footer("&RTrang &P / &N")
        book.close()
        filename = f"Doanh_thu_SL_thanh_pham_xuat_ban_{self.date_from}_{self.date_to}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self",
                "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
