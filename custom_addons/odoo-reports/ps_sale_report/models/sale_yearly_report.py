import textwrap

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_round
from odoo.tools.misc import format_date, formatLang


class SaleYearlyReport(models.AbstractModel):
    _name = "report.ps_sale_report.sale_yearly_pdf"
    _description = "Doanh thu bán hàng trong năm theo khách hàng (xuất bán)"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["ps.sale.history.wizard"].browse(docids)
        docs.check_access("read")
        reports = []
        for wizard in docs:
            dataset = wizard._get_yearly_data()
            if (data or {}).get("report_type") == "html":
                pages = [dataset["rows"]]
            else:
                pages, chunk, used = [], [], 0
                for row in dataset["rows"]:
                    height = sum(max(1, len(textwrap.wrap(part, 80))) for part in row["label"].split("\n")) * 9 + 6
                    if height > 250:
                        raise UserError("Tên khách hàng quá dài cho PDF A4. Hãy xuất Excel.")
                    if chunk and used + height > 390:
                        pages.append(chunk)
                        chunk, used = [], 0
                    chunk.append(row)
                    used += height
                if chunk:
                    pages.append(chunk)
            reports.append({**dataset, "pages": pages})
        return {
            "doc_ids": docs.ids, "doc_model": docs._name, "docs": docs, "reports": reports,
            "format_amount": lambda value, report: formatLang(self.env,
                float_round(value / report["divisor"], precision_digits=report["digits"]) + 0.0,
                digits=report["digits"]) if value is not None else "",
            "format_date": lambda value: format_date(self.env, value, date_format="dd/MM/yyyy") if value else "",
        }
