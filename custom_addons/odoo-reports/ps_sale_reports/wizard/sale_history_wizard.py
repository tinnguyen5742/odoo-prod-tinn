import base64
import io
import re
from datetime import datetime, time, timedelta

import pytz
import xlsxwriter

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleHistoryWizard(models.TransientModel):
    _name = "ps.sale.history.wizard"
    _description = "Bộ lọc lịch sử đặt hàng"
    _check_company_auto = True

    report_type = fields.Selection(
        [
            ("history", "Lịch sử đặt hàng"),
            ("contract", "Tình hình thực hiện hợp đồng"),
        ],
        string="Loại báo cáo",
        required=True,
        default="history",
    )

    company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        string="Từ ngày",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="Đến ngày",
        required=True,
        default=fields.Date.context_today,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Khách hàng",
        check_company=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Sản phẩm",
        check_company=True,
    )
    include_quotations = fields.Boolean(
        string="Bao gồm báo giá",
        default=True,
    )
    export_file = fields.Binary("Tệp Excel", readonly=True, attachment=False)
    export_filename = fields.Char("Tên tệp", readonly=True)

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(
                    "Từ ngày không được lớn hơn đến ngày."
                )

    def _signature_date_text(self):
        self.ensure_one()
        value = self.report_date if self.report_type != "history" else fields.Date.context_today(self)
        return f"Ngày {value.day:02d} tháng {value.month:02d} năm {value.year}"

    def _signature_department(self):
        self.ensure_one()
        return {
            "receivable": "Phòng kế toán",
            "collection": "Phòng kế toán",
            "credit_terms": "Phòng kế toán",
            "inventory": "Bộ phận kho",
            "delivery": "Bộ phận giao hàng",
            "transport": "Bộ phận vận chuyển",
        }.get(self.report_type, "Phòng kinh doanh")

    def _write_xlsx_signature(self, book, sheet, row, last_col):
        """Shared signature block matching the Word report samples."""
        left_end = max(1, (last_col + 1) // 3 - 1)
        right_start = max(left_end + 2, (last_col + 1) * 2 // 3)
        bold = book.add_format({"bold": True, "align": "center", "valign": "vcenter"})
        date = book.add_format({"italic": True, "align": "center", "valign": "vcenter"})
        sheet.merge_range(row, 0, row + 1, left_end, self._signature_department(), bold)
        sheet.merge_range(row, right_start, row, last_col, self._signature_date_text(), date)
        sheet.merge_range(row + 1, right_start, row + 1, last_col, "Người lập", bold)
        sheet.set_row(row, 22)
        sheet.set_row(row + 1, 22)

    def _get_domain(self):
        self.ensure_one()
        self.check_access("read")

        if self.company_id not in self.env.companies:
            raise ValidationError(
                "Bạn không có quyền truy cập công ty đã chọn."
            )

        # Chuyển khoảng ngày theo múi giờ người dùng sang UTC.
        timezone = pytz.timezone(self.env.context.get("tz") or self.env.user.tz or "UTC")
        start = timezone.localize(
            datetime.combine(self.date_from, time.min)
        )
        end = timezone.localize(
            datetime.combine(
                self.date_to + timedelta(days=1),
                time.min,
            )
        )
        start_utc = start.astimezone(pytz.UTC).replace(tzinfo=None)
        end_utc = end.astimezone(pytz.UTC).replace(tzinfo=None)

        states = ["sale"]
        if (
            self.report_type == "history"
            and self.include_quotations
        ):
            states += ["draft", "sent"]

        domain = [
            ("display_type", "=", False),
            ("order_id.company_id", "=", self.company_id.id),
            ("order_id.state", "in", states),
            ("order_id.date_order", ">=", start_utc),
            ("order_id.date_order", "<", end_utc),
        ]

        if self.partner_id:
            domain.append(
                ("order_id.partner_id", "child_of", self.partner_id.id)
            )

        if self.product_id:
            domain.append(
                ("product_id", "=", self.product_id.id)
            )

        if self.report_type == "contract":
            domain.append(
                ("product_id.type", "=", "consu")
            )

        return domain

    def action_view_orders(self):
        domain = self._get_domain()

        if self.report_type == "contract":
            view = self.env.ref(
                "ps_sale_reports.view_sale_contract_line_list"
            )
            title = "Tình hình thực hiện hợp đồng"
            context = {
                **self.env.context,
                "ps_contract_date_to": fields.Date.to_string(
                    self.date_to
                ),
                "group_by": [
                    "ps_contract_customer_id",
                    "order_id",
                ],
            }
        else:
            view = self.env.ref(
                "ps_sale_reports.view_sale_history_line_list"
            )
            title = "Lịch sử đặt hàng"
            context = dict(self.env.context)

        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "sale.order.line",
            "view_mode": "list",
            "views": [(view.id, "list")],
            "domain": domain,
            "context": context,
            "target": "current",
        }

    def _get_report_groups(self):
        """Shared selection for PDF and XLSX; preserve normal SO record rules."""
        if self.report_type != "history":
            raise UserError("In PDF và xuất Excel hiện áp dụng cho báo cáo Lịch sử đặt hàng.")
        lines = self.env["sale.order.line"].search(
            self._get_domain(), order="order_id, sequence, id", limit=10001,
        )
        if not lines:
            raise UserError("Không có dữ liệu phù hợp. Kiểm tra bộ lọc và tùy chọn Bao gồm báo giá.")
        if len(lines) > 10000:
            raise UserError("Có hơn 10.000 dòng. Thu hẹp bộ lọc trước khi in hoặc xuất Excel.")
        groups = {}
        for line in lines:
            group = groups.setdefault(line.order_id.id, {"order": line.order_id, "lines": []})
            group["lines"].append(line)
        return list(groups.values())

    def action_preview_pdf(self):
        self.ensure_one()
        # Odoo's native HTML report viewer provides the control panel and Print
        # button; printing uses this same report's registered PDF action.
        # report_action replaces active_ids with wizard IDs but leaves the
        # source active_model unchanged. The viewer then tries to open an SO
        # or picking with the wizard ID when restoring its breadcrumbs.
        wizard = self.with_context(
            active_model=self._name, active_id=self.id, active_ids=self.ids,
        )
        action = wizard.action_print_pdf()
        action.update({"report_type": "qweb-html", "target": "current"})
        return action

    def action_print_pdf(self):
        self._get_report_groups()
        return self.env.ref("ps_sale_reports.action_sale_history_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        groups = self._get_report_groups()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {
            "in_memory": True, "strings_to_formulas": False, "strings_to_urls": False, "default_format_properties": {"font_name": "Times New Roman", "font_size": 11},
        })
        border = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter"}
        text = book.add_format({**border, "text_wrap": True})
        number = book.add_format({**border, "num_format": "#,##0.00"})
        integer = book.add_format({**border, "align": "center", "num_format": "0"})
        date_format = book.add_format({**border, "num_format": "dd/mm/yyyy"})
        heading = book.add_format({**border, "bold": True, "text_wrap": True,
                                   "align": "center", "bg_color": "#EDF1F6"})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        meta = book.add_format({"text_wrap": True, "valign": "top"})
        headers = ["STT", "Mã nhập kho", "Tên vật tư", "QCSP", "ĐVT", "Đơn giá",
                   "SL giao dịch", "SL gốc", "ĐVT gốc", "Ngày YC nhập kho", "Ngày xác nhận nhập kho",
                   "LSX tham chiếu", "LSX", "Số PO khách hàng", "Ghi chú"]
        used_names = set()
        for group in groups:
            order = group["order"]
            partner = order.partner_id
            # Excel limits sheet names to 31 characters and forbids these symbols.
            base_name = re.sub(r"[\[\]:*?/\\\x00-\x1f]", "_", order.name or f"SO_{order.id}")
            base_name = base_name.strip("'")[:31].rstrip("'") or f"SO_{order.id}"
            if base_name.casefold() == "history":
                base_name = "SO_History"
            sheet_name, suffix_number = base_name, 1
            while sheet_name.casefold() in used_names:
                suffix_number += 1
                suffix = f"_{suffix_number}"
                sheet_name = base_name[:31 - len(suffix)].rstrip("'") + suffix
            used_names.add(sheet_name.casefold())
            sheet = book.add_worksheet(sheet_name)
            sheet.set_column(0, 0, 6)
            sheet.set_column(1, 1, 17)
            sheet.set_column(2, 2, 40)
            sheet.set_column(3, 3, 22)
            sheet.set_column(4, 4, 10)
            sheet.set_column(5, 7, 17)
            sheet.set_column(8, 8, 10)
            sheet.set_column(9, 10, 19)
            sheet.set_column(11, 13, 21)
            sheet.set_column(14, 14, 32)
            row = 0
            sheet.merge_range(row, 0, row, 14, "LỊCH SỬ ĐẶT HÀNG", title)
            sheet.set_row(row, 28)
            sheet.merge_range(row + 1, 0, row + 1, 14, self.company_id.name, meta)
            sheet.merge_range(row + 2, 0, row + 2, 4, "Số đơn đặt hàng: " + order.name, meta)
            sheet.merge_range(row + 2, 5, row + 2, 9, "Số hợp đồng: " + (order.ps_contract_ref or ""), meta)
            sheet.merge_range(row + 2, 10, row + 2, 14, "Người lập: " + self.env.user.name, meta)
            sheet.merge_range(row + 3, 0, row + 3, 14, "Khách hàng: " + partner.display_name, meta)
            sheet.merge_range(row + 4, 0, row + 4, 14, "Địa chỉ: " + (partner.contact_address or "").replace("\n", ", "), meta)
            sheet.set_row(row + 4, 30)
            sheet.merge_range(row + 5, 0, row + 5, 14,
                f"Điện thoại: {partner.phone or ''}    Loại tiền: {order.currency_id.name}    "
                f"Từ ngày {self.date_from:%d/%m/%Y} đến ngày {self.date_to:%d/%m/%Y}", meta)
            row += 7
            for col, value in enumerate(headers):
                sheet.write_string(row, col, value, heading)
            sheet.set_row(row, 34)
            row += 1
            for seq, line in enumerate(group["lines"], 1):
                values = [seq, line.product_id.default_code or "", line.product_id.name or "",
                    line.ps_specification or "", line.product_uom_id.name or "", line.price_unit,
                    line.product_uom_qty, line.ps_base_quantity, line.ps_base_uom_id.name or "",
                    line.ps_requested_receipt_date, line.ps_confirmed_receipt_date,
                    line.ps_production_ref or "", line.ps_production_number or "",
                    line.ps_customer_po or "", line.ps_report_note or ""]
                for col, value in enumerate(values):
                    if col in (9, 10):
                        if value:
                            sheet.write_datetime(row, col, datetime.combine(value, time.min), date_format)
                        else:
                            sheet.write_blank(row, col, None, date_format)
                    elif col in (0, 5, 6, 7):
                        sheet.write_number(row, col, value, integer if col == 0 else number)
                    else:
                        sheet.write_string(row, col, value, text)
                # Explicit height prevents wrapped content being clipped after merged header rows.
                height = max(2, max((len(str(values[c])) + width - 1) // width
                    + str(values[c]).count("\n") for c, width in [(2, 36), (3, 19), (14, 29)]))
                sheet.set_row(row, min(300, 15 * height))
                row += 1
            self._write_xlsx_signature(book, sheet, row + 1, 14)
            sheet.set_landscape()
            sheet.set_paper(8)  # A3
            sheet.fit_to_pages(1, 0)
            sheet.set_margins(0.25, 0.25, 0.4, 0.4)
            sheet.set_footer("&LLịch sử đặt hàng&RTrang &P / &N")
            sheet.print_area(0, 0, row + 2, 14)
            sheet.hide_gridlines(0)
        book.close()
        filename = f"Lich_su_dat_hang_{self.date_from}_{self.date_to}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self",
                "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
