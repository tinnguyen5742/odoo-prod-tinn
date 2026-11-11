import textwrap

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang


class SaleTransportReport(models.AbstractModel):
    _name = "report.ps_sale_reports.sale_transport_pdf"
    _description = "Bảng kê chi tiết vận chuyển"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["ps.sale.history.wizard"].browse(docids)
        docs.check_access("read")
        reports = []
        for wizard in docs:
            dataset = wizard._get_transport_data()
            rows = dataset["rows"]
            if (data or {}).get("report_type") == "html":
                pages = [rows]
            else:
                pages, page, used, carrier = [], [], 0, None

                def height(row):
                    # Match the rendered 7pt column widths so long warehouse
                    # names do not force a new page while usable space remains.
                    texts = [(row["values"][c], width) for c, width in [(2, 20), (3, 28), (4, 32), (5, 28), (9, 10)]] if row["kind"] == "item" else [(row["label"], 95)]
                    wrapped = max(sum(max(1, len(textwrap.wrap(part, width))) for part in str(value).split("\n")) for value, width in texts)
                    value = wrapped * 8 + 7
                    if value > 250:
                        raise UserError("Một dòng vận chuyển quá dài cho A4. Rút gọn nội dung hoặc xuất Excel.")
                    return value

                for index, row in enumerate(rows):
                    reserve = height(rows[index + 1]) if row["kind"] == "carrier" and index + 1 < len(rows) else 0
                    if row["kind"] == "item" and index + 1 < len(rows) and rows[index + 1]["kind"] == "total":
                        reserve = height(rows[index + 1])
                    if page and used + height(row) + reserve > 445:
                        pages.append(page)
                        page = [{**carrier, "continued": True}] if carrier and row["kind"] == "item" else []
                        used = sum(height(r) for r in page)
                    page.append(row)
                    used += height(row)
                    if row["kind"] == "carrier":
                        carrier = row
                if page:
                    pages.append(page)
            reports.append({**dataset, "pages": pages})
        return {"doc_ids": docs.ids, "doc_model": docs._name, "docs": docs, "reports": reports,
            "format_number": lambda value, digits=2: formatLang(self.env, value, digits=digits),
            "format_date": lambda value: format_date(self.env, value, date_format="dd/MM/yyyy")}
