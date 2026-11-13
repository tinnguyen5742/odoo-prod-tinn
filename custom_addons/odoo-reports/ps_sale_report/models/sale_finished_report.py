import textwrap

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang


class SaleFinishedReport(models.AbstractModel):
    _name = "report.ps_sale_report.sale_finished_pdf"
    _description = "Doanh thu – Số lượng theo thành phẩm xuất bán"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["ps.sale.history.wizard"].browse(docids)
        docs.check_access("read")
        reports = []
        for wizard in docs:
            dataset = wizard._get_finished_data()
            if (data or {}).get("report_type") == "html":
                pages = [dataset["rows"]]
            else:
                def height(row):
                    wrapped = sum(max(1, len(textwrap.wrap(part, 68))) for part in row["label"].split("\n"))
                    if row["kind"] == "item":
                        wrapped = max(wrapped, len(textwrap.wrap(row["code"], 18)))
                    other_lines = 0 if row.get("continued") else sum(max(1, len(textwrap.wrap(other["uom"] + " 000,000.00", 23))) for other in row["others"])
                    return max(wrapped, other_lines, 1) * 10 + 5

                pages, page, used, sales, pending = [], [], 0, None, []
                for index, row in enumerate(dataset["rows"]):
                    if height(row) > 250:
                        raise UserError("Một dòng quá dài để in PDF A4. Rút gọn tên hàng hoặc xuất Excel.")
                    if row["kind"] == "sales":
                        pending = [row]
                        continue
                    block = pending + [row]
                    needed = sum(height(r) for r in block)
                    following = dataset["rows"][index + 1] if index + 1 < len(dataset["rows"]) else None
                    reserve = height(following) if following and following["kind"] == "total" else 0
                    if page and used + needed + reserve > 450:
                        pages.append(page)
                        page = [{**sales, "continued": True}] if sales and not pending and row["kind"] != "total" else []
                        used = sum(height(r) for r in page)
                    page.extend(block)
                    used += needed
                    if pending:
                        sales = pending[0]
                    pending = []
                if page:
                    pages.append(page)
            reports.append({**dataset, "pages": pages})
        return {"doc_ids": docs.ids, "doc_model": docs._name, "docs": docs, "reports": reports,
                "format_number": lambda value, digits=2: formatLang(self.env, value, digits=digits),
                "format_date": lambda value: format_date(self.env, value, date_format="dd/MM/yyyy")}
