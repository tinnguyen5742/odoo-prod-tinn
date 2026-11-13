import textwrap

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang


class SaleDailyReport(models.AbstractModel):
    _name = "report.ps_sale_report.sale_daily_pdf"
    _description = "Chi tiết bán hàng theo ngày (xuất bán)"

    def _get_dataset(self, wizard):
        return wizard._get_daily_data()

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["ps.sale.history.wizard"].browse(docids)
        docs.check_access("read")
        reports = []
        for wizard in docs:
            dataset = self._get_dataset(wizard)
            if (data or {}).get("report_type") == "html":
                pages = [dataset["rows"]]
            else:
                pages, page, used, context, pending = [], [], 0, {}, []

                def row_height(row):
                    texts = [(row["values"][1], 55), (row["values"][8], 28)] if row["kind"] == "item" else [(row["label"], 95)]
                    wrapped = max(sum(max(1, len(textwrap.wrap(part, width))) for part in str(value).split("\n")) for value, width in texts)
                    wrapped = max(wrapped, len(row.get("quantities", [])))
                    return 10 * wrapped + 7

                budget = dataset.get("page_budget", 445)
                for index, row in enumerate(dataset["rows"]):
                    if row_height(row) > 250:
                        raise UserError("Một dòng quá dài để in PDF A4. Rút gọn tên hàng/ghi chú hoặc xuất Excel.")
                    if row["kind"] in ("day", "customer", "document"):
                        pending.append(row)
                        continue
                    # Paginate a complete heading chain with its first item.
                    # Repeat only ancestors that are not already in that chain.
                    block = pending + [row]
                    height = sum(row_height(r) for r in block)
                    # Keep the final total with the last item when possible.
                    next_row = dataset["rows"][index + 1] if index + 1 < len(dataset["rows"]) else None
                    reserve = row_height(next_row) if row["kind"] == "item" and next_row and next_row["kind"] == "total" else 0
                    if page and used + height + reserve > budget:
                        pages.append(page)
                        kinds = [r["kind"] for r in pending]
                        repeat = [] if "day" in kinds or row["kind"] == "total" else ["day"] if "customer" in kinds else ["day", "customer"] if "document" in kinds else ["day", "customer", "document"]
                        page = [{**context[k], "continued": True} for k in repeat if k in context]
                        used = sum(row_height(r) for r in page)
                    page.extend(block)
                    used += height
                    for heading in pending:
                        if heading["kind"] == "day":
                            context = {"day": heading}
                        elif heading["kind"] == "customer":
                            context = {k: v for k, v in context.items() if k == "day"}
                            context["customer"] = heading
                        else:
                            context["document"] = heading
                    pending = []
                if page:
                    pages.append(page)
            reports.append({**dataset, "pages": pages})
        return {"doc_ids": docs.ids, "doc_model": docs._name, "docs": docs, "reports": reports,
                "format_date": lambda v: format_date(self.env, v, date_format="dd/MM/yyyy"),
                "format_number": lambda v, digits=2: formatLang(self.env, v, digits=digits)}
