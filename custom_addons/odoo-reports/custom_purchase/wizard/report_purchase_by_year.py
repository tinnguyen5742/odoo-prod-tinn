from odoo import models, api
from datetime import datetime

class ReportPurchaseByYear(models.AbstractModel):
    _name = 'report.custom_purchase.report_purchase_by_year_template'
    _description = 'Logic xử lý Báo cáo Tổng hợp giá trị mua hàng theo năm'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form_data', {})
        date_from = form_data.get('date_from')
        
        # Lấy năm từ date_from (hoặc mặc định năm hiện tại)
        if date_from:
            year = datetime.strptime(str(date_from), '%Y-%m-%d').year
        else:
            year = datetime.now().year

        # Điều kiện tìm các đơn mua hàng đã xác nhận trong năm đó
        date_start = f'{year}-01-01 00:00:00'
        date_end = f'{year}-12-31 23:59:59'

        domain = [
            ('order_id.state', 'in', ['purchase', 'done']),
            ('order_id.date_order', '>=', date_start),
            ('order_id.date_order', '<=', date_end),
        ]

        lines = self.env['purchase.order.line'].search(domain)

        # Cấu trúc dữ liệu ma trận: { partner: { 1: 0, 2: 0, ..., 12: 0, 'total': 0 } }
        matrix = {}
        monthly_totals = {m: 0.0 for m in range(1, 13)}
        grand_total = 0.0

        for line in lines:
            vendor = line.partner_id
            month = line.order_id.date_order.month
            amount = line.price_subtotal

            if vendor not in matrix:
                matrix[vendor] = {m: 0.0 for m in range(1, 13)}
                matrix[vendor]['total'] = 0.0

            matrix[vendor][month] += amount
            matrix[vendor]['total'] += amount
            monthly_totals[month] += amount
            grand_total += amount

        return {
            'docs': docids,
            'year': year,
            'matrix': matrix,
            'monthly_totals': monthly_totals,
            'grand_total': grand_total,
            'company': self.env.company,
            'print_date': datetime.now().strftime('%d tháng %m năm %Y'),
        }