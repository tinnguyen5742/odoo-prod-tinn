import base64
import io
from datetime import datetime, timedelta

import pytz
import xlsxwriter
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleYearlyWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(
        selection_add=[("yearly", "Doanh thu trong năm theo KH (xuất bán)"), ("contract",)],
        ondelete={"yearly": "set default"},
    )
    report_year = fields.Integer("Năm", required=True, default=lambda self: fields.Date.context_today(self).year)
    yearly_display_unit = fields.Selection(
        [("unit", "Đơn vị tiền công ty"), ("million", "Triệu đơn vị tiền công ty")],
        string="Đơn vị hiển thị", required=True, default="unit",
    )

    @api.constrains("report_year")
    def _check_report_year(self):
        for wizard in self:
            if not 1900 <= wizard.report_year <= 9998:
                raise ValidationError("Năm báo cáo phải nằm trong khoảng 1900–9998.")

    def _get_yearly_data(self):
        self.ensure_one()
        self.check_access("read")
        if self.report_type != "yearly":
            raise UserError("Chọn Doanh thu trong năm theo KH (xuất bán).")
        if self.company_id not in self.env.companies:
            raise ValidationError("Bạn không có quyền truy cập công ty đã chọn.")
        self._check_report_year()
        timezone = pytz.timezone(self.env.context.get("tz") or self.env.user.tz or "UTC")
        start = timezone.localize(datetime(self.report_year, 1, 1)).astimezone(pytz.UTC).replace(tzinfo=None)
        end = timezone.localize(datetime(self.report_year + 1, 1, 1)).astimezone(pytz.UTC).replace(tzinfo=None)
        event_domain = [
            ("company_id", "=", self.company_id.id), ("state", "=", "done"),
            ("date", ">=", start), ("date", "<", end),
            "|", ("location_id.usage", "=", "customer"), ("location_dest_id.usage", "=", "customer"),
        ]
        # Apply SO access rules explicitly: stock users can have broader read
        # access to sale.order.line than to sale.order itself.
        # No SO-date filter: old SOs can have deliveries or returns in this year.
        line_domain = [
            ("display_type", "=", False), ("company_id", "=", self.company_id.id),
            ("product_id.type", "=", "consu"), ("move_ids", "any", event_domain),
        ]
        if self.salesperson_id:
            line_domain.append(("order_id.user_id", "=", self.salesperson_id.id))
        orders = self.env["sale.order"].search([
            ("company_id", "=", self.company_id.id), ("order_line", "any", line_domain),
        ], limit=10001)
        if len(orders) > 10000:
            raise UserError("Có hơn 10.000 SO phát sinh giao/trả trong năm. Hãy lọc theo Sales.")
        lines = self.env["sale.order.line"].with_context(accrual_entry_date=False).search(
            line_domain + [("order_id", "in", orders.ids)], limit=10001,
        )
        if len(lines) > 10000:
            raise UserError("Có hơn 10.000 dòng SO phát sinh giao/trả trong năm. Hãy lọc theo Sales.")
        events = self.env["stock.move"].search(
            event_domain + [("sale_line_id", "in", lines.ids)], order="date, id", limit=10001,
        ) if lines else self.env["stock.move"]
        if len(events) > 10000:
            raise UserError("Có hơn 10.000 dòng giao/trả trong năm. Hãy lọc theo Sales.")
        grouped_events = {}
        for move in events:
            grouped_events.setdefault(move.sale_line_id.id, self.env["stock.move"])
            grouped_events[move.sale_line_id.id] |= move
        boms = self.env["mrp.bom"]._bom_find(
            lines.product_id, company_id=self.company_id.id, bom_type="phantom",
        ) if lines else {}
        currency = self.company_id.currency_id
        customers = {}
        for line in lines:
            events_for_line = grouped_events.get(line.id, self.env["stock.move"])
            used_boms = line.move_ids.bom_line_id.bom_id.filtered(
                lambda bom: bom.type == "phantom" and (bom.product_id == line.product_id
                or (not bom.product_id and bom.product_tmpl_id == line.product_id.product_tmpl_id))
            )
            daily_qty = {}
            if used_boms or boms.get(line.product_id):
                # A kit's components do not share the sold product's UOM. Use
                # Odoo's delivered-kit calculation, taking its change per day.
                days = sorted({fields.Datetime.context_timestamp(self, m.date).date() for m in events_for_line})
                for day in days:
                    today_line = line.with_context(accrual_entry_date=fields.Date.to_string(day))
                    prior_line = line.with_context(accrual_entry_date=fields.Date.to_string(day - timedelta(days=1)))
                    daily_qty[day] = (today_line._prepare_qty_delivered().get(today_line, 0.0)
                                      - prior_line._prepare_qty_delivered().get(prior_line, 0.0))
            else:
                outgoing, incoming = line._get_outgoing_incoming_moves()
                for sign, moves in [(1, outgoing & events_for_line), (-1, incoming & events_for_line)]:
                    for move in moves:
                        if sign == -1 and (not move.origin_returned_move_id
                            and not move.location_id._is_outgoing() and line.product_uom_qty > 0
                            and not move.picking_id.return_id):
                            continue
                        day = fields.Datetime.context_timestamp(self, move.date).date()
                        qty = move.product_uom._compute_quantity(move.quantity, line.product_uom_id, round=False)
                        daily_qty[day] = daily_qty.get(day, 0.0) + sign * qty
            if not daily_qty:
                continue
            if not line.product_uom_qty:
                raise UserError(f"Dòng SO {line.order_id.name} / {line.product_id.display_name} có số đặt bằng 0. Kiểm tra trước khi tính giá xuất bán.")
            partner = line.order_id.partner_id
            label = f"({partner.ref}) - {partner.name}" if partner.ref else partner.name
            customer = customers.setdefault(partner.id, {
                "partner_id": partner.id, "label": label, "months": [None] * 12,
            })
            unit_price = line.price_subtotal / line.product_uom_qty
            for day, quantity in daily_qty.items():
                amount = line.currency_id._convert(unit_price * quantity, currency, self.company_id, day)
                month = day.month - 1
                customer["months"][month] = (customer["months"][month] or 0.0) + amount
        if not customers:
            raise UserError("Không có phiếu giao hoàn tất hoặc phiếu trả cập nhật SO phù hợp trong năm đã chọn.")
        rows = sorted(customers.values(), key=lambda item: (item["label"].casefold(), item["partner_id"]))
        totals = [None] * 12
        for row in rows:
            row["months"] = [currency.round(value) if value is not None else None for value in row["months"]]
            row["total"] = currency.round(sum(value or 0 for value in row["months"]))
            for month, value in enumerate(row["months"]):
                if value is not None:
                    totals[month] = (totals[month] or 0.0) + value
        totals = [currency.round(value) if value is not None else None for value in totals]
        million = self.yearly_display_unit == "million"
        return {
            "wizard": self, "rows": rows, "totals": totals,
            "grand_total": currency.round(sum(value or 0 for value in totals)),
            "currency": currency, "divisor": 1000000 if million else 1,
            "digits": 1 if million else currency.decimal_places,
            "unit_label": ("Triệu đồng" if currency.name == "VND" else "Triệu " + currency.name) if million else currency.name,
            "sales_filter": self.salesperson_id.name if self.salesperson_id else "",
        }

    def action_print_pdf(self):
        if self.report_type != "yearly":
            return super().action_print_pdf()
        self._get_yearly_data()
        return self.env.ref("ps_sale_report.action_sale_yearly_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "yearly":
            return super().action_export_xlsx()
        data = self._get_yearly_data()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False, "default_format_properties": {"font_name": "Times New Roman", "font_size": 11}})
        sheet = book.add_worksheet("Doanh thu nam theo KH")
        base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter"}
        base_format = "#,##0" + ("." + "0" * data["digits"] if data["digits"] else "")
        threshold = f"{0.5 * 10 ** (-data['digits']):.{data['digits'] + 1}f}"
        zero = "0" + ("." + "0" * data["digits"] if data["digits"] else "")
        # Display tiny scaled negatives as 0.0, while preserving exact numeric
        # values in Excel for further calculations.
        num_format = f'[>={threshold}]{base_format};[<=-{threshold}]-{base_format};"{zero}"'
        text = book.add_format({**base, "text_wrap": True})
        number = book.add_format({**base, "num_format": num_format})
        total_text = book.add_format({**base, "bold": True, "text_wrap": True, "bg_color": "#EDF1F6"})
        total_number = book.add_format({**base, "bold": True, "num_format": num_format, "bg_color": "#EDF1F6"})
        header = book.add_format({**base, "bold": True, "bg_color": "#EDF1F6", "align": "center"})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        centered = book.add_format({"align": "center", "font_size": 11})
        meta = book.add_format({"font_size": 11})
        signature = book.add_format({"align": "right", "font_size": 10})
        sheet.set_column(0, 0, 48)
        sheet.set_column(1, 12, 15)
        sheet.set_column(13, 13, 18)
        sheet.merge_range(0, 0, 0, 13, self.company_id.name, meta)
        sheet.merge_range(1, 0, 1, 13, "BÁO CÁO DOANH THU BÁN HÀNG TRONG NĂM THEO KHÁCH HÀNG", title)
        sheet.set_row(1, 28)
        sheet.merge_range(2, 0, 2, 13, "(THEO XUẤT BÁN)", centered)
        sheet.merge_range(3, 0, 3, 13, f"Năm: {self.report_year} | ĐVT: {data['unit_label']}", centered)
        sheet.merge_range(4, 0, 4, 13, "Sales: " + data["sales_filter"] if data["sales_filter"] else "", meta)
        for col, label in enumerate(["Khách hàng"] + [f"T{i}" for i in range(1, 13)] + ["Cả năm"]):
            sheet.write_string(6, col, label, header)
        sheet.set_row(6, 28)

        def write_amount(row, col, value, fmt):
            if value is None:
                sheet.write_blank(row, col, None, fmt)
            else:
                sheet.write_number(row, col, value / data["divisor"], fmt)

        for row, item in enumerate(data["rows"], 7):
            sheet.write_string(row, 0, item["label"], text)
            for col, value in enumerate(item["months"] + [item["total"]], 1):
                write_amount(row, col, value, number)
            sheet.set_row(row, max(26, min(300, 15 * ((len(item["label"]) + 43) // 44))))
        last = len(data["rows"]) + 7
        sheet.write_string(last, 0, "TỔNG CỘNG", total_text)
        for col, value in enumerate(data["totals"] + [data["grand_total"]], 1):
            write_amount(last, col, value, total_number)
        sheet.set_row(last, 28)
        self._write_xlsx_signature(book, sheet, last + 2, 13)
        sheet.freeze_panes(7, 0)
        sheet.repeat_rows(6)
        sheet.hide_gridlines(0)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.set_margins(0.25, 0.25, 0.35, 0.35)
        sheet.print_area(0, 0, last + 3, 13)
        book.close()
        filename = f"Doanh_thu_nam_theo_KH_xuat_ban_{self.report_year}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self",
                "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
