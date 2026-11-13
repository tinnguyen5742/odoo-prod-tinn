import textwrap

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang


class SaleSalespersonReport(models.AbstractModel):
    _name = "report.ps_sale_report.sale_salesperson_pdf"
    _description = "Doanh thu - Số lượng theo Sales (SO)"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["ps.sale.history.wizard"].browse(docids)
        docs.check_access("read")
        reports = []
        for wizard in docs:
            dataset = wizard._get_salesperson_data()
            rows = dataset["rows"]
            pages = []
            if (data or {}).get("report_type") == "html":
                pages = [rows]
            else:
                footer_height = 55 + sum(max(1, len(textwrap.wrap(q["uom"], 15))) for q in dataset["totals"]["others"]) * 10
                budget = 410 - footer_height
                if budget < 80:
                    raise UserError("Quá nhiều đơn vị tính cho PDF A4. Hãy xuất Excel.")
                chunk, used = [], 0
                for row in rows:
                    height = max(len(textwrap.wrap(row["salesperson"], 30)),
                                 sum(max(1, len(textwrap.wrap(q["uom"], 15))) for q in row["others"]), 1) * 10 + 8
                    if height > budget:
                        raise UserError("Một Sales có quá nhiều đơn vị tính cho PDF A4. Hãy xuất Excel.")
                    if chunk and used + height > budget:
                        pages.append(chunk)
                        chunk, used = [], 0
                    chunk.append(row)
                    used += height
                if chunk:
                    pages.append(chunk)
            reports.append({**dataset, "pages": pages})
        return {"doc_ids": docs.ids, "doc_model": docs._name, "docs": docs, "reports": reports,
                "format_number": lambda value: formatLang(self.env, value, digits=2) if value is not None else "",
                "format_date": lambda value: format_date(self.env, value, date_format="dd/MM/yyyy") if value else ""}
