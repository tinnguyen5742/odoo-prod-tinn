import base64
import io

import xlsxwriter
from odoo import fields, models
from odoo.exceptions import UserError


class SaleSalespersonWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(
        selection_add=[("salesperson", "Doanh thu – Số lượng theo Sales (SO)")],
        ondelete={"salesperson": "set default"},
    )

    def _get_domain(self):
        domain = super()._get_domain()
        if self.report_type == "salesperson":
            # A whole-Sales plan cannot be compared to a customer/product subset.
            domain = [term for term in domain if term[0] not in ("order_id.partner_id", "product_id")]
            if self.salesperson_id:
                domain.append(("order_id.user_id", "=", self.salesperson_id.id))
        return domain

    def _get_salesperson_data(self):
        self.ensure_one()
        if self.report_type != "salesperson":
            raise UserError("Chọn báo cáo Doanh thu – Số lượng theo Sales (SO).")
        # Base domain validates access, company, date range and confirmed SO state.
        domain = self._get_domain()
        # M² is computed on demand; cap input to keep screen/PDF/Excel consistent.
        lines = self.env["sale.order.line"].search(domain, order="order_id, sequence, id", limit=10001)
        if len(lines) > 10000:
            raise UserError("Có hơn 10.000 dòng SO. Thu hẹp khoảng ngày hoặc chọn Sales.")
        plan_domain = [
            ("company_id", "=", self.company_id.id),
            ("date_from", "=", self.date_from), ("date_to", "=", self.date_to),
        ]
        if self.salesperson_id:
            plan_domain.append(("salesperson_id", "=", self.salesperson_id.id))
        plans = self.env["ps.sale.salesperson.plan"].search(plan_domain)
        groups = {}

        def group_for(user):
            return groups.setdefault(user.id or 0, {
                "code": (user.ps_sales_code or "") if user else "",
                "salesperson": user.name if user else "Chưa phân công Sales",
                "user_id": user.id or 0, "planned_m2": None, "planned_revenue": None,
                "m2": 0.0, "other": {}, "revenue": 0.0, "has_so": False,
            })

        for plan in plans:
            item = group_for(plan.salesperson_id)
            item.update(planned_m2=plan.planned_m2, planned_revenue=plan.planned_revenue)
        currency = self.company_id.currency_id
        for line in lines:
            item = group_for(line.order_id.user_id)
            item["has_so"] = True
            so_date = fields.Datetime.context_timestamp(self, line.order_id.date_order).date()
            item["revenue"] += line.currency_id._convert(
                line.price_subtotal, currency, self.company_id, so_date,
            )
            # Use the M² conversion already introduced in report 7.
            if line.ps_tracking_m2_factor:
                item["m2"] += line.ps_tracking_quantity_m2
            else:
                # No M² factor: keep quantity in its base UOM, separated by UOM ID.
                # Never infer M² from a translated UOM name or assume factor 1.
                unit = line.ps_base_uom_id
                # Productless down-payment lines have no UOM. Keep their SO
                # value above, but do not create a quantity group with a False
                # label (which cannot be sorted or used in an Excel format).
                if unit:
                    qty = item["other"].setdefault(unit.id, {"uom": unit.display_name, "quantity": 0.0})
                    qty["quantity"] += line.ps_base_quantity
        if not groups:
            raise UserError("Không có SO hoặc kế hoạch phù hợp trong khoảng ngày đã chọn.")
        result = []
        for item in sorted(groups.values(), key=lambda g: (g["salesperson"].casefold(), g["user_id"])):
            item["revenue"] = currency.round(item["revenue"])
            item["delta_m2"] = item["m2"] - item["planned_m2"] if item["planned_m2"] is not None else None
            item["delta_revenue"] = currency.round(item["revenue"] - item["planned_revenue"]) if item["planned_revenue"] is not None else None
            item["others"] = sorted(item["other"].values(), key=lambda q: q["uom"])
            item["seq"] = len(result) + 1
            result.append(item)
        total_other = {}
        for item in result:
            for key, qty in item["other"].items():
                entry = total_other.setdefault(key, {"uom": qty["uom"], "quantity": 0.0})
                entry["quantity"] += qty["quantity"]
        all_planned = all(item["planned_m2"] is not None for item in result)
        # Do not present a partial plan as the total plan for all reported Sales.
        totals = {key: sum(item[key] for item in result) if all_planned else None
                  for key in ("planned_m2", "planned_revenue", "delta_m2", "delta_revenue")}
        totals.update(m2=sum(item["m2"] for item in result),
                      revenue=currency.round(sum(item["revenue"] for item in result)),
                      others=sorted(total_other.values(), key=lambda q: q["uom"]))
        return {"wizard": self, "rows": result, "totals": totals,
                "currency": currency, "missing_plan": [r["salesperson"] for r in result if r["planned_m2"] is None]}

    def action_print_pdf(self):
        if self.report_type != "salesperson":
            return super().action_print_pdf()
        self._get_salesperson_data()
        return self.env.ref("ps_sale_report.action_sale_salesperson_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "salesperson":
            return super().action_export_xlsx()
        data = self._get_salesperson_data()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False, "default_format_properties": {"font_name": "Times New Roman", "font_size": 11}})
        sheet = book.add_worksheet("Doanh thu Sales")
        base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter", "font_size": 11}
        header = book.add_format({**base, "bold": True, "bg_color": "#EDF1F6", "text_wrap": True, "align": "center"})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        meta = book.add_format({"text_wrap": True, "font_size": 11, "valign": "vcenter"})
        signature = book.add_format({"align": "right", "font_size": 10, "font_color": "#475569"})

        def make_formats(color, bold=False):
            props = {**base, "bg_color": color, "bold": bold}
            return {
                "text": book.add_format({**props, "text_wrap": True}),
                "number": book.add_format({**props, "num_format": "#,##0.00"}),
                "integer": book.add_format({**props, "num_format": "0", "align": "center"}),
                "props": props,
            }

        block_formats = [make_formats("#FFFFFF"), make_formats("#F6F8FC")]
        total_formats = make_formats("#EDF1F6", bold=True)
        unit_formats = {}

        def unit_format(formats, unit):
            key = (formats["props"]["bg_color"], formats["props"]["bold"], unit)
            if key not in unit_formats:
                literal = unit.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
                unit_formats[key] = book.add_format({**formats["props"], "num_format": '#,##0.00" ' + literal + '"'})
            return unit_formats[key]
        labels = ["STT", "Mã NV", "Tên nhân viên", "SL kế hoạch (M²)", "DT kế hoạch", "SL M²", "SL khác / ĐVT", "Doanh thu", "CL SL (M²)", "CL DT"]
        sheet.set_column(0, 0, 6)
        sheet.set_column(1, 1, 12)
        sheet.set_column(2, 2, 26)
        sheet.set_column(3, 4, 18)
        sheet.set_column(5, 5, 15)
        sheet.set_column(6, 6, 28)
        sheet.set_column(7, 9, 19)
        sheet.merge_range(0, 0, 0, 9, self.company_id.name, meta)
        sheet.merge_range(1, 0, 1, 9, "BÁO CÁO SẢN LƯỢNG - DOANH THU NHẬN ĐƠN HÀNG", title)
        sheet.set_row(1, 28)
        sheet.merge_range(2, 0, 2, 9, "(NHÂN VIÊN SALE)", title)
        sheet.merge_range(3, 0, 3, 9, f"Từ ngày {self.date_from:%d/%m/%Y} đến ngày {self.date_to:%d/%m/%Y} | Loại tiền: {data['currency'].name}", meta)
        for col, label in enumerate(labels):
            sheet.write_string(5, col, label, header)
        sheet.set_row(5, 36)

        def write_value(row, col, value, fmt):
            if value is None:
                sheet.write_blank(row, col, None, fmt)
            elif isinstance(value, (int, float)):
                sheet.write_number(row, col, value, fmt)
            else:
                sheet.write_string(row, col, str(value), fmt)

        def write_block_value(first, last, col, value, fmt):
            if first != last:
                sheet.merge_range(first, col, last, col, "", fmt)
            write_value(first, col, value, fmt)

        def write_other_quantities(first, quantities, formats):
            if not quantities:
                sheet.write_blank(first, 6, None, formats["number"])
            for offset, qty in enumerate(quantities):
                # Keep an actual numeric cell; its format displays the unit beside it.
                sheet.write_number(first + offset, 6, qty["quantity"], unit_format(formats, qty["uom"]))

        row = 6
        for index, item in enumerate(data["rows"]):
            formats = block_formats[index % 2]
            last = row + max(1, len(item["others"])) - 1
            values = [item[k] for k in ("seq", "code", "salesperson", "planned_m2", "planned_revenue", "m2")]
            values += ["", item["revenue"], item["delta_m2"], item["delta_revenue"]]
            for col, value in enumerate(values):
                if col == 6:
                    continue
                fmt = formats["integer"] if col == 0 else formats["text"] if col in (1, 2) else formats["number"]
                write_block_value(row, last, col, value, fmt)
            write_other_quantities(row, item["others"], formats)
            for detail_row in range(row, last + 1):
                sheet.set_row(detail_row, 26)
            row = last + 1
        totals = data["totals"]
        last = row + max(1, len(totals["others"])) - 1
        sheet.merge_range(row, 0, last, 2, "Tổng cộng", total_formats["text"])
        for col, key in [(3, "planned_m2"), (4, "planned_revenue"), (5, "m2"), (7, "revenue"), (8, "delta_m2"), (9, "delta_revenue")]:
            write_block_value(row, last, col, totals[key], total_formats["number"])
        write_other_quantities(row, totals["others"], total_formats)
        for detail_row in range(row, last + 1):
            sheet.set_row(detail_row, 26)
        row = last + 1
        self._write_xlsx_signature(book, sheet, row + 1, 9)
        sheet.hide_gridlines(0)
        sheet.freeze_panes(6, 0)
        sheet.repeat_rows(5)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.print_area(0, 0, row + 2, 9)
        book.close()
        filename = f"Doanh_thu_Sales_SO_{self.date_from}_{self.date_to}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self",
                "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
