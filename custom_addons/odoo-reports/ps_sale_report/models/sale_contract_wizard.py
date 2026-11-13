import base64
import io
from datetime import datetime, time

import xlsxwriter

from odoo import fields, models
from odoo.exceptions import UserError


class SaleContractWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    salesperson_id = fields.Many2one(
        "res.users", "Nhân viên Sales", domain=[("share", "=", False)],
    )
    region_id = fields.Many2one("res.country.state", "Khu vực / tỉnh thành")
    report_date = fields.Date("Ngày lập", required=True, default=fields.Date.context_today)

    def _get_domain(self):
        domain = super()._get_domain()
        if self.report_type == "contract":
            if self.salesperson_id:
                domain.append(("order_id.user_id", "=", self.salesperson_id.id))
            if self.region_id:
                domain.append(("order_id.partner_id.state_id", "=", self.region_id.id))
        return domain

    def _get_contract_data(self):
        self.ensure_one()
        if self.report_type != "contract":
            raise UserError("Chọn Tình hình thực hiện hợp đồng trước khi xuất mẫu này.")
        lines = self.env["sale.order.line"].with_context(
            ps_contract_date_to=fields.Date.to_string(self.date_to),
        ).search(self._get_domain(), order="order_id, sequence, id", limit=10001)
        if not lines:
            raise UserError("Không có đơn hàng đã xác nhận phù hợp với bộ lọc. Báo cáo hợp đồng chỉ lấy hàng hóa.")
        if len(lines) > 10000:
            raise UserError("Có hơn 10.000 dòng. Thu hẹp bộ lọc trước khi in hoặc xuất Excel.")
        groups = {}
        orders = {}
        for line in lines:
            order = line.order_id
            customer = groups.setdefault(order.partner_id.id, {
                "partner": order.partner_id, "orders": [],
            })
            if order.id not in orders:
                orders[order.id] = {
                    "order": order, "currency": order.currency_id, "rows": [],
                    "ordered_total": 0.0, "delivered_total": 0.0,
                }
                customer["orders"].append(orders[order.id])
            block = orders[order.id]
            promised = line.ps_contract_promised_date
            promised_date = fields.Datetime.context_timestamp(self, promised).date() if promised else False
            product_name = line.product_id.with_context(display_default_code=False).display_name
            if line.product_id.default_code:
                product_name = f"[{line.product_id.default_code}] {product_name}"
            block["rows"].append({
                "line_id": line.id, "seq": len(block["rows"]) + 1,
                "product": product_name,
                "uom": line.product_uom_id.name, "currency": line.currency_id.name,
                "ordered_qty": line.product_uom_qty, "unit_price": line.price_unit,
                "ordered_value": line.price_total, "promised_date": promised_date,
                "delivered_qty": line.ps_contract_delivered_qty,
                "delivered_value": line.ps_contract_delivered_value,
                "delivery_date": line.ps_contract_last_delivery_date,
                "remaining_qty": line.ps_contract_remaining_qty,
            })
            block["ordered_total"] += line.price_total
            block["delivered_total"] += line.ps_contract_delivered_value
        customers = sorted(groups.values(), key=lambda g: (g["partner"].name or "").casefold())
        for customer in customers:
            customer["orders"].sort(key=lambda g: (g["order"].date_order, g["order"].id))
        filters = []
        if self.partner_id:
            filters.append("Khách hàng: " + self.partner_id.display_name)
        if self.region_id:
            filters.append("Khu vực: " + self.region_id.display_name)
        if self.salesperson_id:
            filters.append("Sales: " + self.salesperson_id.name)
        if self.product_id:
            filters.append("Hàng hóa: " + self.product_id.display_name)
        return {"wizard": self, "customers": customers, "filters": " | ".join(filters)}

    def action_print_pdf(self):
        if self.report_type != "contract":
            return super().action_print_pdf()
        self._get_contract_data()
        return self.env.ref("ps_sale_report.action_sale_contract_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "contract":
            return super().action_export_xlsx()
        data = self._get_contract_data()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {
            "in_memory": True, "strings_to_formulas": False, "strings_to_urls": False, "default_format_properties": {"font_name": "Times New Roman", "font_size": 11},
        })
        sheet = book.add_worksheet("Thuc hien hop dong")
        base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter"}
        text = book.add_format({**base, "text_wrap": True})
        number = book.add_format({**base, "num_format": "#,##0.00"})
        integer = book.add_format({**base, "num_format": "0", "align": "center"})
        date_fmt = book.add_format({**base, "num_format": "dd/mm/yyyy", "align": "center"})
        header = book.add_format({**base, "bold": True, "align": "center", "text_wrap": True, "bg_color": "#EDF1F6"})
        customer_fmt = book.add_format({**base, "bold": True, "font_color": "#0645AD", "text_wrap": True})
        order_fmt = book.add_format({**base, "bold": True, "font_color": "#B91C1C", "text_wrap": True})
        order_num = book.add_format({**base, "bold": True, "font_color": "#B91C1C", "num_format": "#,##0.00"})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        meta = book.add_format({"text_wrap": True, "valign": "top"})
        sheet.set_column(0, 0, 6)
        sheet.set_column(1, 1, 46)
        sheet.set_column(2, 3, 11)
        sheet.set_column(4, 6, 18)
        sheet.set_column(7, 7, 17)
        sheet.set_column(8, 9, 18)
        sheet.set_column(10, 10, 17)
        sheet.set_column(11, 11, 18)
        sheet.merge_range(0, 0, 0, 11, self.company_id.name, meta)
        sheet.merge_range(1, 0, 1, 11, "BÁO CÁO TÌNH HÌNH THỰC HIỆN ĐƠN HÀNG", title)
        sheet.set_row(1, 27)
        sheet.merge_range(2, 0, 2, 11, f"Từ ngày {self.date_from:%d/%m/%Y} đến ngày {self.date_to:%d/%m/%Y}", meta)
        sheet.merge_range(3, 0, 3, 11, data["filters"], meta)
        sheet.set_row(3, 30)
        sheet.merge_range(5, 0, 6, 0, "STT", header)
        sheet.merge_range(5, 1, 6, 1, "Mặt hàng", header)
        sheet.merge_range(5, 2, 6, 2, "ĐVT", header)
        sheet.merge_range(5, 3, 6, 3, "Loại tiền", header)
        sheet.merge_range(5, 4, 5, 7, "Đơn hàng", header)
        sheet.merge_range(5, 8, 5, 10, "Thực hiện", header)
        sheet.merge_range(5, 11, 6, 11, "Còn lại", header)
        for col, label in enumerate(["Số lượng", "Đơn giá", "Trị giá", "Ngày giao", "Số lượng", "Trị giá", "Ngày giao"], 4):
            sheet.write_string(6, col, label, header)
        sheet.set_row(5, 24)
        sheet.set_row(6, 30)
        row = 7
        for customer in data["customers"]:
            partner = customer["partner"]
            label = f"{partner.ref or ''}: {partner.name} - {(partner.contact_address or '').replace(chr(10), ', ')}"
            sheet.merge_range(row, 0, row, 11, label, customer_fmt)
            sheet.set_row(row, 30)
            row += 1
            for block in customer["orders"]:
                order = block["order"]
                label = f"Số SO: {order.name} | Hợp đồng: {order.ps_contract_ref or ''} | {block['currency'].name}"
                sheet.merge_range(row, 0, row, 5, label, order_fmt)
                for col in range(6, 12):
                    sheet.write_blank(row, col, None, order_fmt)
                sheet.write_number(row, 6, block["ordered_total"], order_num)
                sheet.write_number(row, 9, block["delivered_total"], order_num)
                sheet.set_row(row, 25)
                row += 1
                for item in block["rows"]:
                    values = [item[key] for key in ["seq", "product", "uom", "currency", "ordered_qty", "unit_price",
                        "ordered_value", "promised_date", "delivered_qty", "delivered_value", "delivery_date", "remaining_qty"]]
                    for col, value in enumerate(values):
                        if col in (7, 10):
                            if value:
                                sheet.write_datetime(row, col, datetime.combine(value, time.min), date_fmt)
                            else:
                                sheet.write_blank(row, col, None, date_fmt)
                        elif col == 0:
                            sheet.write_number(row, col, value, integer)
                        elif col in (4, 5, 6, 8, 9, 11):
                            sheet.write_number(row, col, value, number)
                        else:
                            sheet.write_string(row, col, str(value or ""), text)
                    sheet.set_row(row, max(30, min(300, 15 * ((len(item["product"]) + 39) // 40))))
                    row += 1
        sheet.merge_range(row + 1, 0, row + 2, 11,
            "Ngày lọc là ngày SO. Thực hiện lũy kế đến ngày kết thúc. Trị giá gồm thuế, sau chiết khấu; "
            "trị giá thực hiện quy đổi theo giá SO. Không cộng số lượng khác ĐVT hoặc giá trị khác loại tiền.", meta)
        self._write_xlsx_signature(book, sheet, row + 3, 11)
        sheet.freeze_panes(7, 2)
        sheet.repeat_rows(5, 6)
        sheet.hide_gridlines(0)
        sheet.set_landscape()
        sheet.set_paper(9)  # A4
        sheet.fit_to_pages(1, 0)
        sheet.set_footer("&RTrang &P / &N")
        sheet.print_area(0, 0, row + 4, 11)
        book.close()
        filename = f"Tinh_hinh_thuc_hien_hop_dong_{self.date_from}_{self.date_to}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self",
                "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
