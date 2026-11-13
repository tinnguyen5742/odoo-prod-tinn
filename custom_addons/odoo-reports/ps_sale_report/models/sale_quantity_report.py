from odoo import models


class SaleQuantityReport(models.AbstractModel):
    _name = "report.ps_sale_report.sale_quantity_pdf"
    _inherit = "report.ps_sale_report.sale_daily_pdf"
    _description = "Tổng hợp bán hàng theo M² / ĐVT gốc"

    def _get_dataset(self, wizard):
        return wizard._get_quantity_data()
