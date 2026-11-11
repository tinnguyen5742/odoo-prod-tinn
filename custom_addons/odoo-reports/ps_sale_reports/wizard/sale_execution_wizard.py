import base64
import io
from datetime import datetime, time

import xlsxwriter

from odoo import fields, models
from odoo.exceptions import UserError


EXECUTION_COLUMNS = [
    ("STT", "number"),
    ("Số SO", "text"),
    ("Ngày SO", "date"),
    ("Ngày YC giao", "date"),
    ("Tình trạng", "text"),
    ("Mã khách hàng", "text"),
    ("Tên khách hàng", "text"),
    ("Mã hàng", "text"),
    ("Tên hàng", "text"),
    ("ĐVT", "text"),
    ("Số lượng SO", "number"),
    ("Số đề nghị xuất kho", "text"),
    ("SL đề nghị", "number"),
    ("Số phiếu xuất", "text"),
    ("Số lượng xuất", "number"),
    ("Số PGH", "text"),
    ("Ngày giao hàng", "date"),
]


class SaleExecutionWizard(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    report_type = fields.Selection(
        selection_add=[
            (
                "execution",
                "Tình hình thực hiện đơn hàng bán",
            ),
        ],
        ondelete={"execution": "set default"},
    )

    def _get_domain(self):
        domain = super()._get_domain()

        if self.report_type == "execution":
            # Mẫu có cả SO chưa xác nhận và đã xác nhận.
            domain = [
                term
                for term in domain
                if term[0] != "order_id.state"
            ]

            domain += [
                (
                    "order_id.state",
                    "in",
                    ["draft", "sent", "sale"],
                ),
                ("product_id.type", "=", "consu"),
            ]

            if self.tracking_order_id:
                domain.append(
                    (
                        "order_id",
                        "=",
                        self.tracking_order_id.id,
                    )
                )

        return domain

    def _get_execution_data(self):
        self.ensure_one()

        if self.report_type != "execution":
            raise UserError(
                "Chọn Tình hình thực hiện đơn hàng bán."
            )

        lines = self.env["sale.order.line"].search(
            self._get_domain(),
            order="order_id, sequence, id",
            limit=10001,
        )

        if not lines:
            raise UserError(
                "Không có đơn hàng phù hợp với bộ lọc."
            )

        if len(lines) > 10000:
            raise UserError(
                "Có hơn 10.000 dòng SO. "
                "Hãy thu hẹp bộ lọc."
            )

        def local_date(value):
            if not value:
                return False

            return fields.Datetime.context_timestamp(
                self, value
            ).date()

        rows = []

        for line in lines:
            order = line.order_id
            partner = order.partner_id

            status = (
                "Đã xác nhận"
                if order.state == "sale"
                else "Chưa xác nhận"
            )

            common = [
                order.name,
                local_date(order.date_order),
                line.ps_requested_delivery_date,
                status,
                partner.ref or "",
                partner.name or "",
                line.product_id.default_code or "",
                line.product_id.with_context(
                    display_default_code=False
                ).display_name,
                line.product_uom_id.name,
            ]

            # Chỉ lấy lượt xuất ra khách hàng của đúng
            # sản phẩm và dòng SO; bỏ lượt trả hàng.
            moves = line.move_ids.filtered(
                lambda move:
                    move.state != "cancel"
                    and move.company_id == order.company_id
                    and move.product_id == line.product_id
                    and move.picking_id
                    and move.picking_id.picking_type_id.code
                    == "outgoing"
                    and move.location_dest_id.usage
                    == "customer"
                    and move.location_id.usage
                    != "customer"
                    and not move.origin_returned_move_id
            ).sorted(
                key=lambda move: (
                    move.picking_id.id,
                    move.id,
                )
            )

            # Dòng SO chưa có phiếu giao vẫn xuất hiện.
            details = list(moves) or [None]

            for index, move in enumerate(details):
                request_ref = ""
                request_qty = None
                picking_name = ""
                shipped_qty = None
                delivery_date = False

                if move:
                    request_ref = (
                        move.ps_execution_request_ref or ""
                    )

                    if request_ref:
                        request_qty = (
                            move.product_uom
                            ._compute_quantity(
                                move.ps_execution_request_qty,
                                line.product_uom_id,
                                round=False,
                            )
                        )

                    actual_date = local_date(move.date)

                    completed = (
                        move.state == "done"
                        and actual_date
                        and actual_date <= self.date_to
                    )

                    if completed:
                        picking_name = move.picking_id.name
                        delivery_date = actual_date

                        shipped_qty = (
                            move.product_uom
                            ._compute_quantity(
                                move.quantity,
                                line.product_uom_id,
                                round=False,
                            )
                        )

                rows.append(
                    [len(rows) + 1]
                    + common
                    + [
                        (
                            line.product_uom_qty
                            if index == 0
                            else None
                        ),
                        request_ref,
                        request_qty,
                        picking_name,
                        shipped_qty,
                        picking_name,
                        delivery_date,
                    ]
                )

                if len(rows) > 10000:
                    raise UserError(
                        "Có hơn 10.000 dòng chi tiết. "
                        "Hãy thu hẹp bộ lọc."
                    )

        return {
            "wizard": self,
            "columns": EXECUTION_COLUMNS,
            "rows": rows,
        }

    def action_print_pdf(self):
        if self.report_type != "execution":
            return super().action_print_pdf()

        self._get_execution_data()

        return self.env.ref(
            "ps_sale_reports.action_sale_execution_pdf"
        ).report_action(self, config=False)

    def action_export_xlsx(self):
        if self.report_type != "execution":
            return super().action_export_xlsx()

        data = self._get_execution_data()
        output = io.BytesIO()

        book = xlsxwriter.Workbook(
            output,
            {
                "in_memory": True,
                "strings_to_formulas": False,
                "strings_to_urls": False,
                "default_format_properties": {"font_name": "Times New Roman", "font_size": 11},
            },
        )

        sheet = book.add_worksheet(
            "Thuc hien don hang"
        )

        base = {
            "border": 1,
            "border_color": "#94A3B8",
            "valign": "vcenter",
        }

        formats = {
            "text": book.add_format({
                **base,
                "text_wrap": True,
            }),
            "number": book.add_format({
                **base,
                "num_format": "#,##0.00",
            }),
            "date": book.add_format({
                **base,
                "num_format": "dd/mm/yyyy",
            }),
        }

        integer = book.add_format({
            **base,
            "num_format": "0",
            "align": "center",
        })

        header = book.add_format({
            **base,
            "bold": True,
            "bg_color": "#EDF1F6",
            "align": "center",
            "text_wrap": True,
        })

        title = book.add_format({
            "bold": True,
            "font_size": 15,
            "align": "center",
        })

        meta = book.add_format({
            "text_wrap": True,
        })

        sheet.set_column(0, 0, 6)
        sheet.set_column(1, 7, 17)
        sheet.set_column(6, 6, 30)
        sheet.set_column(8, 8, 38)
        sheet.set_column(9, 9, 10)
        sheet.set_column(10, 16, 19)

        sheet.merge_range(
            0, 0, 0, 16,
            self.company_id.name,
            meta,
        )

        sheet.merge_range(
            1, 0, 1, 16,
            "TÌNH HÌNH THỰC HIỆN ĐƠN HÀNG",
            title,
        )
        sheet.set_row(1, 28)

        sheet.merge_range(
            2, 0, 2, 16,
            (
                f"Từ ngày {self.date_from:%d/%m/%Y} "
                f"đến ngày {self.date_to:%d/%m/%Y}"
            ),
            meta,
        )

        for col, (label, _) in enumerate(
            EXECUTION_COLUMNS
        ):
            sheet.write_string(
                4, col, label, header
            )

        sheet.set_row(4, 36)

        for row_number, values in enumerate(
            data["rows"], 5
        ):
            height = 2

            for col, value in enumerate(values):
                kind = EXECUTION_COLUMNS[col][1]
                fmt = formats[kind]

                if value is None or value is False or value == "":
                    sheet.write_blank(
                        row_number, col, None, fmt
                    )
                elif col == 0:
                    sheet.write_number(
                        row_number, col, value, integer
                    )
                elif kind == "number":
                    sheet.write_number(
                        row_number, col, value, fmt
                    )
                elif kind == "date":
                    sheet.write_datetime(
                        row_number,
                        col,
                        datetime.combine(
                            value, time.min
                        ),
                        fmt,
                    )
                else:
                    sheet.write_string(
                        row_number,
                        col,
                        str(value),
                        fmt,
                    )

                    height = max(
                        height,
                        (len(str(value)) + 24) // 25,
                    )

            sheet.set_row(
                row_number,
                min(300, height * 15),
            )

        last = len(data["rows"]) + 4

        self._write_xlsx_signature(book, sheet, last + 2, 16)

        sheet.freeze_panes(5, 0)
        sheet.repeat_rows(4)
        sheet.hide_gridlines(0)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.print_area(0, 0, last + 3, 16)

        book.close()

        filename = (
            f"Thuc_hien_don_hang_"
            f"{self.date_from}_{self.date_to}.xlsx"
        )

        self.write({
            "export_file": base64.b64encode(
                output.getvalue()
            ),
            "export_filename": filename,
        })

        return {
            "type": "ir.actions.act_url",
            "target": "self",
            "url": (
                f"/web/content/{self._name}/{self.id}"
                f"/export_file/{filename}?download=true"
            ),
        }