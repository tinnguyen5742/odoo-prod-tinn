import textwrap

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang


class SaleTrackingReport(models.AbstractModel):
    _name = "report.ps_sale_report.sale_tracking_pdf"
    _description = "Bản in theo dõi đơn hàng"

    def _paginate(self, dataset, paginate=True):
        weights = [2, 6, 8, 5, 4, 5, 4, 5, 10, 4, 3, 3, 4, 5, 5, 5, 4, 4, 4, 4, 5, 7, 6]
        columns = [(key, label, kind, width) for (key, label, kind, _), width
                   in zip(dataset["columns"], weights)]
        total_width = sum(weights)
        # Preserve all 23 columns in one table; only paginate vertically.
        pages, rows, used = [], [], 0
        for row in dataset["rows"]:
            wraps = []
            for key, _, kind, width in columns:
                chars = max(3, int(340 * width / total_width))
                value = row[key]
                text = str(value or "") if kind == "text" else ("00/00/0000" if kind == "date" else f"{value:,.2f}" if value is not None else "")
                wraps.append(sum(max(1, len(textwrap.wrap(s, chars))) for s in text.split("\n")))
            height = max(wraps) * 7 + 5
            if paginate and height > 250:
                raise UserError("Một dòng có nội dung quá dài cho PDF A4. Rút gọn ghi chú/quy cách hoặc xuất Excel.")
            if paginate and rows and used + height > 400:
                pages.append(rows)
                rows, used = [], 0
            rows.append(row)
            used += height
        if rows:
            pages.append(rows)
        return pages, columns

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["ps.sale.history.wizard"].browse(docids)
        docs.check_access("read")
        reports = []
        for wizard in docs:
            dataset = wizard._get_tracking_data()
            pages, columns = self._paginate(dataset, paginate=(data or {}).get("report_type") != "html")
            reports.append({**dataset, "pages": pages, "columns": columns})
        return {"doc_ids": docs.ids, "doc_model": docs._name, "docs": docs, "reports": reports,
                "format_date": lambda value: format_date(self.env, value, date_format="dd/MM/yyyy") if value else "",
                "format_number": lambda value: formatLang(self.env, value, digits=2)}
