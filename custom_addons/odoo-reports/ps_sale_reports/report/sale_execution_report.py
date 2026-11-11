import textwrap

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang


class SaleExecutionReport(models.AbstractModel):
    _name = "report.ps_sale_reports.sale_execution_pdf"
    _description = "Tình hình thực hiện đơn hàng bán"

    def _get_dataset(self, wizard):
        return wizard._get_execution_data()

    def _wrap_columns(self):
        return [(1, 14), (6, 18), (7, 14), (8, 22), (11, 16), (13, 16), (15, 16)]

    def _row_height(self, wrapped):
        return wrapped * 8 + 6

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env[
            "ps.sale.history.wizard"
        ].browse(docids)

        docs.check_access("read")
        reports = []

        for wizard in docs:
            dataset = self._get_dataset(wizard)
            rows = dataset["rows"]

            if (data or {}).get("report_type") == "html":
                pages = [rows]
            else:
                pages = []
                chunk = []
                used = 0

                for row in rows:
                    wrapped = max(
                        max(
                            1,
                            len(
                                textwrap.wrap(
                                    str(row[col] or ""),
                                    width=width,
                                )
                            ),
                        )
                        for col, width in self._wrap_columns()
                    )

                    height = self._row_height(wrapped)

                    if height > 250:
                        raise UserError(
                            "Một dòng quá dài cho PDF A4. "
                            "Hãy xuất Excel."
                        )

                    if chunk and used + height > 330:
                        pages.append(chunk)
                        chunk = []
                        used = 0

                    chunk.append(row)
                    used += height

                if chunk:
                    pages.append(chunk)

            reports.append({
                **dataset,
                "pages": pages,
            })

        return {
            "doc_ids": docs.ids,
            "doc_model": docs._name,
            "docs": docs,
            "reports": reports,
            "format_number": lambda value: formatLang(
                self.env, value, digits=2
            ),
            "format_date": lambda value: (
                format_date(
                    self.env,
                    value,
                    date_format="dd/MM/yyyy",
                )
                if value else ""
            ),
        }
