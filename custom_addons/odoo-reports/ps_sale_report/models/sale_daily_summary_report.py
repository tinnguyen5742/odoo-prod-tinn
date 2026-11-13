from odoo import models


class SaleDailySummaryReport(models.AbstractModel):
    _name = "report.ps_sale_report.sale_daily_summary_pdf"
    _inherit = "report.ps_sale_report.sale_daily_pdf"
    _description = "Tổng hợp bán hàng theo ngày"

    def _get_dataset(self, wizard):
        return wizard._get_daily_summary_data()
