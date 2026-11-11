import textwrap

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang


class SaleInventoryReport(models.AbstractModel):
    _name = "report.ps_sale_reports.sale_inventory_pdf"
    _description = "Nhập Xuất Tồn chi tiết theo SO"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["ps.sale.history.wizard"].browse(docids)
        docs.check_access("read")
        reports = []
        for wizard in docs:
            dataset = wizard._get_inventory_data()
            if (data or {}).get("report_type") == "html":
                pages = [dataset["rows"]]
            else:
                def height(row):
                    texts = [(row["label"], 120)] if "label" in row else [
                        (row["values"][col], width) for col, width in [(2, 12), (3, 16), (4, 21), (5, 24), (6, 8)]
                    ]
                    wrapped = max(sum(max(1, len(textwrap.wrap(part, width))) for part in str(value or "").split("\n")) for value, width in texts)
                    # 7.5pt table text, 1.25 line height and 3px padding.
                    return wrapped * 9.5 + 5

                # A4 ngang: tận dụng phần bảng, chừa chữ ký ở khối cuối.
                # Đo trên PDF thực tế để tránh đẩy vài dòng sang trang thừa.
                page_budget, signature_height = 500, 40
                levels = ("warehouse", "product", "order")
                pages, page, used, context, pending = [], [], 0, {}, []
                for row_index, row in enumerate(dataset["rows"]):
                    if height(row) > 250:
                        raise UserError("Một dòng quá dài để in PDF A4. Rút gọn thông tin hoặc xuất Excel.")
                    if row["kind"] in levels:
                        pending.append(row)
                        continue
                    block = pending + [row]
                    needed = sum(height(r) for r in block)
                    reserve = signature_height if row_index == len(dataset["rows"]) - 1 else 0
                    if page and used + needed + reserve > page_budget:
                        pages.append(page)
                        first_level = min((levels.index(r["kind"]) for r in pending), default=len(levels))
                        page = [{**context[k], "continued": True} for k in levels[:first_level] if k in context]
                        used = sum(height(r) for r in page)
                    if used + needed + reserve > page_budget:
                        raise UserError("Thông tin nhóm và dòng quá dài cho PDF A4. Rút gọn thông tin hoặc xuất Excel.")
                    page.extend(block)
                    used += needed
                    for heading in pending:
                        level = levels.index(heading["kind"])
                        context = {k: v for k, v in context.items() if levels.index(k) < level}
                        context[heading["kind"]] = heading
                    pending = []
                if page:
                    pages.append(page)
            reports.append({**dataset, "pages": pages})
        return {"doc_ids": docs.ids, "doc_model": docs._name, "docs": docs, "reports": reports,
                "format_date": lambda value: format_date(self.env, value, date_format="dd/MM/yyyy") if value else "",
                "format_number": lambda value: formatLang(self.env, value, digits=2)}
