from odoo import models
from odoo.tools.misc import formatLang


class SaleCreditTermsReport(models.AbstractModel):
    _name = "report.ps_sale_report.sale_credit_terms_pdf"
    _inherit = "report.ps_sale_report.sale_execution_pdf"
    _description = "Bảng kê thời hạn công nợ bán ra"

    def _get_dataset(self, wizard):
        return wizard._get_credit_terms_data()

    def _wrap_columns(self):
        return [(1, 18), (2, 48), (3, 36), (5, 27)]

    def _row_height(self, wrapped):
        return wrapped * 9 + 8

    def _get_report_values(self, docids, data=None):
        values = super()._get_report_values(docids, data=data)
        values["format_limit"] = lambda amount, currency: formatLang(self.env, amount, digits=currency.decimal_places)
        return values
