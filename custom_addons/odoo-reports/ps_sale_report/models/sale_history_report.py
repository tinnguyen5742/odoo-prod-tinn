import textwrap

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang


class SaleHistoryReport(models.AbstractModel):
    _name = "report.ps_sale_report.sale_history_pdf"
    _description = "Bản in lịch sử đặt hàng"

    def _paginate_groups(self, groups, paginate=True):
        if not paginate:
            return [{**group, "offset": 0} for group in groups]
        # wkhtmltopdf can overlap a repeated THEAD with the next row when it
        # splits a long table. Keep each table on one page and repeat SO metadata.
        pages = []
        for group in groups:
            chunk, used, offset = [], 0, 0
            for line in group["lines"]:
                texts = [
                    (line.product_id.default_code, 12), (line.product_id.name, 30),
                    (line.ps_specification, 14), (line.product_uom_id.name, 6),
                    (line.ps_base_uom_id.name, 6), (line.ps_production_ref, 12),
                    (line.ps_production_number, 11), (line.ps_customer_po, 12),
                    (line.ps_report_note, 15),
                ]
                wrapped = max(sum(max(1, len(textwrap.wrap(part, width=width)))
                                  for part in str(value or "").split("\n"))
                              for value, width in texts)
                height = max(2, wrapped) * 10 + 7
                if height > 330:
                    raise UserError("Một dòng quá dài để in trên một trang. Rút gọn tên hàng, quy cách hoặc ghi chú trước khi in PDF.")
                if chunk and (used + height > 330 or len(chunk) >= 12):
                    pages.append({"order": group["order"], "lines": chunk, "offset": offset})
                    offset += len(chunk)
                    chunk, used = [], 0
                chunk.append(line)
                used += height
            if chunk:
                pages.append({"order": group["order"], "lines": chunk, "offset": offset})
        return pages

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["ps.sale.history.wizard"].browse(docids)
        docs.check_access("read")
        return {
            "doc_ids": docs.ids,
            "doc_model": docs._name,
            "docs": docs,
            "print_date": fields.Date.context_today(self),
            "reports": [{"wizard": wizard, "pages": self._paginate_groups(
                wizard._get_report_groups(), paginate=(data or {}).get("report_type") != "html",
            )} for wizard in docs],
            "format_date": lambda value: format_date(self.env, value, date_format="dd/MM/yyyy") if value else "",
            "format_number": lambda value: formatLang(self.env, value, digits=2),
        }
