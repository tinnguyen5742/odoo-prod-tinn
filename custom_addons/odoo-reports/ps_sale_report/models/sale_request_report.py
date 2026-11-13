from odoo import models


class SaleRequestReport(models.AbstractModel):
    _name = "report.ps_sale_report.sale_request_pdf"
    _inherit = "report.ps_sale_report.sale_execution_pdf"
    _description = "Theo dõi đề nghị xuất bán"

    def _get_dataset(self, wizard):
        return wizard._get_request_data()

    def _wrap_columns(self):
        return [(1, 14), (2, 16), (3, 48), (4, 10), (6, 22), (8, 22)]

    def _row_height(self, wrapped):
        return wrapped * 10 + 6
