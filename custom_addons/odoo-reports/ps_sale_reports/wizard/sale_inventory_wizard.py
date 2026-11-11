import base64
import io
from datetime import datetime, time, timedelta

import pytz
import xlsxwriter
from odoo import fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero


INVENTORY_COLUMNS = [
    ("STT", "number"), ("Ngày", "date"), ("Số SO", "text"), ("Lệnh SX", "text"),
    ("Chứng từ", "text"), ("Vị trí đối ứng", "text"), ("ĐVT", "text"),
    ("Tồn đầu", "number"), ("Nhập", "number"), ("Xuất", "number"), ("Tồn cuối", "number"),
]


class SaleInventoryWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(
        selection_add=[("inventory", "Nhập Xuất Tồn chi tiết theo SO"), ("finished",)],
        ondelete={"inventory": "set default"},
    )
    inventory_warehouse_id = fields.Many2one("stock.warehouse", string="Kho", check_company=True)

    def _inventory_move_flows(self, move, warehouse_ids):
        """PHẦN 12: lượng thực tế theo từng kho, quy về ĐVT gốc sản phẩm.

        Dòng chi tiết là nguồn vị trí và số lượng thực tế. Không dùng lượng
        yêu cầu hoặc tồn hiện tại để dựng lại lịch sử. Cộng các lot/bin của
        cùng dịch chuyển thành một dòng/kho; bỏ chuyển bin trong cùng kho.
        """
        details = [
            (line.quantity, line.product_uom_id, line.location_id, line.location_dest_id)
            for line in move.move_line_ids
        ]
        if not details:
            # Imported legacy done moves can have no detailed operations.
            details = [(move.quantity, move.product_uom, move.location_id, move.location_dest_id)]
        flows = {}
        for quantity, uom, source_location, destination_location in details:
            quantity = uom._compute_quantity(quantity, move.product_id.uom_id, round=False)
            if not quantity:
                continue
            source = source_location.warehouse_id if source_location.usage == "internal" else self.env["stock.warehouse"]
            destination = destination_location.warehouse_id if destination_location.usage == "internal" else self.env["stock.warehouse"]
            if source == destination:
                continue
            for warehouse, direction, opposite in (
                (source, "outgoing", destination_location),
                (destination, "incoming", source_location),
            ):
                if warehouse.id not in warehouse_ids:
                    continue
                flow = flows.setdefault(warehouse.id, {
                    "warehouse": warehouse, "incoming": 0.0, "outgoing": 0.0, "opposites": [],
                })
                flow[direction] += quantity
                label = opposite.complete_name or opposite.name or ""
                if label and label not in flow["opposites"]:
                    flow["opposites"].append(label)
        return list(flows.values())

    def _get_inventory_data(self):
        """Kho → sản phẩm → SO; chỉ liên kết rõ một SO, không phân bổ giả.

        Tồn đầu = nhập - xuất trước kỳ; số dư từng dòng = số dư trước đó
        + nhập - xuất. Ngày và quyền truy cập áp dụng giống nhau cho toàn bộ
        lịch sử, bản xem, PDF và Excel.
        """
        self.ensure_one()
        self.check_access("read")
        if self.report_type != "inventory":
            raise UserError("Chọn báo cáo Nhập Xuất Tồn chi tiết theo SO.")
        if self.company_id not in self.env.companies:
            raise ValidationError("Bạn không có quyền truy cập công ty đã chọn.")
        warehouses = self.env["stock.warehouse"].search([("company_id", "=", self.company_id.id)])
        if self.inventory_warehouse_id:
            warehouses &= self.inventory_warehouse_id
        if not warehouses:
            raise UserError("Không có kho phù hợp trong công ty đã chọn.")
        timezone = pytz.timezone(self.env.context.get("tz") or self.env.user.tz or "UTC")
        start = timezone.localize(datetime.combine(self.date_from, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        end = timezone.localize(datetime.combine(self.date_to + timedelta(days=1), time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        domain = [
            ("company_id", "=", self.company_id.id), ("state", "=", "done"), ("date", "<", end),
            ("product_id.type", "=", "consu"),
            "|", "|", "|",
            ("location_id.warehouse_id", "in", warehouses.ids),
            ("location_dest_id.warehouse_id", "in", warehouses.ids),
            ("move_line_ids.location_id.warehouse_id", "in", warehouses.ids),
            ("move_line_ids.location_dest_id.warehouse_id", "in", warehouses.ids),
        ]
        if self.product_id:
            domain.append(("product_id", "=", self.product_id.id))
        # Opening balances require history before the start, not current quants.
        moves = self.env["stock.move"].search(domain, order="date, id", limit=20001)
        if len(moves) > 20000:
            raise UserError("Có hơn 20.000 dịch chuyển cần đối chiếu tồn đầu. Hãy chọn kho hoặc sản phẩm cụ thể.")
        candidates, order_ids = [], set()
        warehouse_ids = set(warehouses.ids)
        linked_cache = {}

        def linked_lines(move):
            if move.id in linked_cache:
                return linked_cache[move.id]
            direct = move.sale_line_id | move.production_id.sale_line_id | move.raw_material_production_id.sale_line_id
            if direct:
                result = direct
            else:
                # Follow native MTO/MRP chains; Source Document text alone is
                # not an allocation and must not attach shared stock to an SO.
                connected = move.browse(move._rollup_move_origs() | move._rollup_move_dests())
                result = (move._get_sale_order_lines() | connected.production_id.sale_line_id
                          | connected.raw_material_production_id.sale_line_id)
            linked_cache[move.id] = result
            return result

        for move in moves:
            flows = self._inventory_move_flows(move, warehouse_ids)
            if not flows:
                continue
            production = move.production_id or move.raw_material_production_id
            linked = linked_lines(move)
            if not linked and move.origin_returned_move_id:
                origin = move.origin_returned_move_id
                linked = linked_lines(origin)
            related_orders = linked.order_id
            # Never allocate an undivided stock quantity across several SOs.
            if len(related_orders) != 1:
                continue
            order_id = related_orders.id
            order_ids.add(order_id)
            candidates.append((move, production, order_id, flows))
        order_domain = [("id", "in", list(order_ids)), ("company_id", "=", self.company_id.id)]
        if self.tracking_order_id:
            order_domain.append(("id", "=", self.tracking_order_id.id))
        if self.partner_id:
            order_domain.append(("partner_id", "child_of", self.partner_id.id))
        # Stock rules can permit wider SOL access than the SO itself.
        orders = {order.id: order for order in self.env["sale.order"].search(order_domain)}
        groups = {}
        for move, production, order_id, flows in candidates:
            if order_id not in orders:
                continue
            product, order = move.product_id, orders[order_id]
            for flow in flows:
                warehouse = flow["warehouse"]
                key = (warehouse.id, product.id, order.id)
                group = groups.setdefault(key, {"warehouse": warehouse, "product": product, "order": order,
                                                "opening": 0.0, "events": []})
                if move.date < start:
                    group["opening"] += flow["incoming"] - flow["outgoing"]
                else:
                    group["events"].append({"date": move.date, "id": move.id,
                        "incoming": flow["incoming"], "outgoing": flow["outgoing"], "production": production.name or "",
                        "document": move.picking_id.name or move.reference or "",
                        "opposite": "\n".join(flow["opposites"])})
        rows, seq, previous_warehouse, previous_product = [], 0, None, None
        for group in sorted(groups.values(), key=lambda g: (g["warehouse"].name.casefold(), g["warehouse"].id,
                            (g["product"].default_code or "").casefold(), g["product"].display_name.casefold(),
                            g["product"].id, g["order"].name, g["order"].id)):
            warehouse, product, order = group["warehouse"], group["product"], group["order"]
            if not group["events"] and float_is_zero(group["opening"], precision_rounding=product.uom_id.rounding):
                continue
            if warehouse.id != previous_warehouse:
                rows.append({"kind": "warehouse", "label": warehouse.display_name})
                previous_warehouse, previous_product = warehouse.id, None
            if product.id != previous_product:
                rows.append({"kind": "product", "label": product.display_name + " – " + product.uom_id.name})
                previous_product = product.id
            rows.append({"kind": "order", "label": "SO: " + order.name + " | " + order.partner_id.name})
            opening, balance = group["opening"], group["opening"]
            for event in sorted(group["events"], key=lambda v: (v["date"], v["id"])):
                seq += 1
                qty_in, qty_out = event["incoming"], event["outgoing"]
                after = balance + qty_in - qty_out
                day = fields.Datetime.context_timestamp(self, event["date"]).date()
                rows.append({"kind": "item", "values": [seq, day, order.name, event["production"],
                    event["document"], event["opposite"], product.uom_id.name, balance, qty_in, qty_out, after]})
                balance = after
            if not group["events"]:
                seq += 1
                rows.append({"kind": "item", "values": [seq, self.date_from, order.name, "", "Dư đầu kỳ", "",
                    product.uom_id.name, opening, 0.0, 0.0, opening]})
            if len(rows) > 10000:
                raise UserError("Có hơn 10.000 dòng kết quả. Thu hẹp bộ lọc kho, SO, khách hàng hoặc sản phẩm.")
        if not rows:
            raise UserError("Không có tồn đầu hoặc dịch chuyển kho hoàn tất gắn rõ một SO phù hợp với bộ lọc.")
        return {"wizard": self, "rows": rows, "columns": INVENTORY_COLUMNS,
                "filters": [label + value for label, value in [
                    ("Kho: ", self.inventory_warehouse_id.display_name or ""), ("SO: ", self.tracking_order_id.name or ""),
                    ("Khách hàng: ", self.partner_id.display_name or ""), ("Sản phẩm: ", self.product_id.display_name or ""),
                ] if value]}

    def action_print_pdf(self):
        if self.report_type != "inventory":
            return super().action_print_pdf()
        self._get_inventory_data()
        return self.env.ref("ps_sale_reports.action_sale_inventory_pdf").report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "inventory":
            return super().action_export_xlsx()
        data = self._get_inventory_data()
        output = io.BytesIO()
        book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False,
            "strings_to_urls": False, "default_format_properties": {"font_name": "Times New Roman", "font_size": 11}})
        sheet = book.add_worksheet("NXT chi tiet theo SO")
        base = {"border": 1, "border_color": "#94A3B8", "valign": "vcenter"}
        text = book.add_format({**base, "text_wrap": True})
        number = book.add_format({**base, "num_format": "#,##0.00"})
        integer = book.add_format({**base, "num_format": "0", "align": "center"})
        date = book.add_format({**base, "num_format": "dd/mm/yyyy"})
        group = book.add_format({**base, "bold": True, "font_color": "#0645AD", "text_wrap": True})
        heading = book.add_format({**base, "bold": True, "align": "center", "bg_color": "#EDF1F6", "text_wrap": True})
        title = book.add_format({"bold": True, "font_size": 15, "align": "center"})
        meta = book.add_format({"text_wrap": True})
        center = book.add_format({"italic": True, "align": "center"})
        for col, width in enumerate([6, 15, 18, 22, 26, 32, 12, 18, 18, 18, 18]):
            sheet.set_column(col, col, width)
        sheet.merge_range(0, 0, 0, 10, self.company_id.name, meta)
        sheet.merge_range(1, 0, 1, 10, "BÁO CÁO NHẬP XUẤT TỒN CHI TIẾT THEO SO", title)
        sheet.set_row(1, 28)
        sheet.merge_range(2, 0, 2, 10, f"Từ ngày {self.date_from:%d/%m/%Y} đến ngày {self.date_to:%d/%m/%Y}", center)
        sheet.merge_range(3, 0, 3, 10, " | ".join(data["filters"]), meta)
        sheet.set_row(3, 30 if data["filters"] else 15)
        for col, (label, kind) in enumerate(INVENTORY_COLUMNS):
            sheet.write_string(5, col, label, heading)
        sheet.set_row(5, 30)
        for row, entry in enumerate(data["rows"], 6):
            if entry["kind"] != "item":
                sheet.merge_range(row, 0, row, 10, entry["label"], group)
                sheet.set_row(row, max(24, min(300, 15 * ((len(entry["label"]) + 140) // 141))))
                continue
            for col, value in enumerate(entry["values"]):
                fmt = text
                if INVENTORY_COLUMNS[col][1] == "number":
                    fmt = integer if col == 0 else number
                elif col == 1:
                    fmt = date
                if value is None or value is False or value == "":
                    sheet.write_blank(row, col, None, fmt)
                elif col == 1:
                    sheet.write_datetime(row, col, datetime.combine(value, time.min), fmt)
                elif INVENTORY_COLUMNS[col][1] == "number":
                    sheet.write_number(row, col, value, fmt)
                else:
                    sheet.write_string(row, col, value, fmt)
            height = max(2, max(sum(max(1, (len(part) + width - 1) // width) for part in str(entry["values"][col]).split("\n"))
                              for col, width in [(2, 16), (3, 20), (4, 24), (5, 29), (6, 10)]))
            sheet.set_row(row, min(300, height * 15))
        last = len(data["rows"]) + 7
        self._write_xlsx_signature(book, sheet, last, 10)
        sheet.freeze_panes(6, 0)
        sheet.repeat_rows(5)
        sheet.hide_gridlines(0)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.print_area(0, 0, last + 1, 10)
        sheet.set_footer("&RTrang &P / &N")
        book.close()
        filename = f"Nhap_xuat_ton_chi_tiet_theo_SO_{self.date_from}_{self.date_to}.xlsx"
        self.write({"export_file": base64.b64encode(output.getvalue()), "export_filename": filename})
        return {"type": "ir.actions.act_url", "target": "self",
                "url": f"/web/content/{self._name}/{self.id}/export_file/{filename}?download=true"}
