import textwrap

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang


class SaleContractReport(models.AbstractModel):
    _name = "report.ps_sale_reports.sale_contract_pdf"
    _description = "Bản in tình hình thực hiện hợp đồng"

    def _paginate(self, data, paginate=True):
        pages = []
        sections, used, last_partner = [], 0, None

        def flush():
            nonlocal sections, used, last_partner
            if sections:
                pages.append({"sections": sections})
            sections, used, last_partner = [], 0, None

        for customer in data["customers"]:
            partner = customer["partner"]
            partner_label = f"{partner.ref or ''}: {partner.name} - {(partner.contact_address or '').replace(chr(10), ', ')}"
            partner_height = 8.5 * max(1, len(textwrap.wrap(partner_label, 170))) + 5
            for block in customer["orders"]:
                current = None
                for item in block["rows"]:
                    row_height = max(1, len(textwrap.wrap(item["product"], 60))) * 8.5 + 5
                    if paginate and row_height > 260:
                        raise UserError("Tên mặt hàng quá dài cho một trang PDF. Rút gọn tên mặt hàng trước khi in.")
                    overhead = (partner_height if partner.id != last_partner else 0) + 14 if current is None else 0
                    if paginate and sections and used + overhead + row_height > 410:
                        flush()
                        current = None
                    if current is None:
                        show_partner = partner.id != last_partner
                        current = {
                            "partner_label": partner_label, "show_partner": show_partner,
                            "order": block["order"], "currency": block["currency"],
                            "ordered_total": block["ordered_total"], "delivered_total": block["delivered_total"],
                            "continued": item["seq"] != 1, "rows": [],
                        }
                        sections.append(current)
                        used += (partner_height if show_partner else 0) + 14
                        last_partner = partner.id
                    current["rows"].append(item)
                    used += row_height
        flush()
        return pages

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["ps.sale.history.wizard"].browse(docids)
        docs.check_access("read")
        reports = []
        for wizard in docs:
            dataset = wizard._get_contract_data()
            reports.append({"wizard": wizard, "filters": dataset["filters"],
                            "pages": self._paginate(dataset, paginate=(data or {}).get("report_type") != "html")})
        return {
            "doc_ids": docs.ids, "doc_model": docs._name, "docs": docs, "reports": reports,
            "format_date": lambda value: format_date(self.env, value, date_format="dd/MM/yyyy") if value else "",
            "format_number": lambda value: formatLang(self.env, value, digits=2),
        }
