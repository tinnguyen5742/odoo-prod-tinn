from odoo import models


class SaleDeliveryReport(models.AbstractModel):
    _name = "report.ps_sale_report.sale_delivery_pdf"
    _inherit = "report.ps_sale_report.sale_execution_pdf"
    _description = "Dự kiến kế hoạch giao hàng"

    def _get_dataset(self, wizard):
        return wizard._get_delivery_data()

    def _wrap_columns(self):
        return [(0, 10), (1, 16), (2, 21), (3, 6), (9, 10), (10, 10), (11, 10), (12, 12), (15, 20), (16, 12)]

    def _row_height(self, wrapped):
        # Calibrated against the narrower 6.5pt delivery table, including
        # multiline addresses. Reusing execution's larger rows wastes paper.
        return wrapped * 6.5 + 6
