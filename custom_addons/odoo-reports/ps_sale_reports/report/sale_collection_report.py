import textwrap

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang


class SaleCollectionReport(models.AbstractModel):
    _name = "report.ps_sale_reports.sale_collection_pdf"
    _description = "Thu tiền khách hàng - Số dư từng hóa đơn"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["ps.sale.history.wizard"].browse(docids)
        docs.check_access("read")
        reports = []
        for wizard in docs:
            dataset = wizard._get_collection_data()
            if (data or {}).get("report_type") == "html":
                pages = [dataset["rows"]]
            else:
                pages, page, pending, context, used = [], [], [], {}, 0

                def height(row):
                    texts = [(row["values"][1], 25), (row["values"][3], 72)] if "values" in row else [(row["label"], 95)]
                    wrapped = max(sum(max(1, len(textwrap.wrap(part, width))) for part in str(v or "").split("\n")) for v, width in texts)
                    value = wrapped * 9 + 8
                    if value > 250:
                        raise UserError("Một dòng thu tiền quá dài cho PDF A4. Rút gọn diễn giải hoặc xuất Excel.")
                    return value

                for index, row in enumerate(dataset["rows"]):
                    if row["kind"] in ("customer", "currency", "invoice"):
                        pending.append(row)
                        continue
                    block = pending + [row]
                    next_row = dataset["rows"][index + 1] if index + 1 < len(dataset["rows"]) else None
                    reserve = height(next_row) if next_row and next_row["kind"] in ("total", "advance_total") and row["kind"] in ("item", "advance") else 0
                    if page and used + sum(height(r) for r in block) + reserve > 445:
                        pages.append(page)
                        kinds = {r["kind"] for r in pending}
                        ancestors = [] if row["kind"] in ("total", "advance_total") or "customer" in kinds else ["customer"] if "currency" in kinds else ["customer", "currency"] if "invoice" in kinds else ["customer", "currency", "invoice"]
                        page = [{**context[k], "continued": True} for k in ancestors if k in context]
                        used = sum(height(r) for r in page)
                    page.extend(block)
                    used += sum(height(r) for r in block)
                    for heading in pending:
                        kind = heading["kind"]
                        if kind == "customer":
                            context = {kind: heading}
                        elif kind == "currency":
                            context = {k: v for k, v in context.items() if k == "customer"}
                            context[kind] = heading
                        else:
                            context[kind] = heading
                    pending = []
                if page:
                    pages.append(page)
            reports.append({**dataset, "pages": pages})
        return {"doc_ids": docs.ids, "doc_model": docs._name, "docs": docs, "reports": reports,
            "format_number": lambda value, digits=2: formatLang(self.env, value, digits=digits),
            "format_date": lambda value: format_date(self.env, value, date_format="dd/MM/yyyy") if value else ""}
