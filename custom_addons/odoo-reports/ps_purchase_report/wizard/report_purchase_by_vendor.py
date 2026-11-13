from odoo import models, api

class ReportPurchaseByVendor(models.AbstractModel):
    # Tên định danh bắt buộc: "report." + tên module + tên template XML
    _name = 'report.ps_purchase_report.report_purchase_by_vendor_template'
    _description = 'Logic xử lý báo cáo mua hàng theo Vật tư NCC'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form_data')
        chosen_style = form_data.get('report_style', 'classic')
        date_from = form_data.get('date_from')
        date_to = form_data.get('date_to')
        partner_id = form_data.get('partner_id')

        # Điều kiện tìm kiếm (Domain): Đơn đã xác nhận và nằm trong khoảng thời gian
        domain = [
            ('order_id.state', 'in', ['purchase', 'done']),
            ('order_id.date_order', '>=', date_from),
            ('order_id.date_order', '<=', date_to),
        ]
        if partner_id:
            domain.append(('partner_id', '=', partner_id[0]))

        # Tìm toàn bộ chi tiết đơn mua hàng (Purchase Order Line) thỏa mãn điều kiện
        po_lines = self.env['purchase.order.line'].search(domain)

        # Gom nhóm dữ liệu theo Nhà cung cấp (Partner)
        grouped_data = {}
        for line in po_lines:
            vendor = line.partner_id
            if vendor not in grouped_data:
                grouped_data[vendor] = {
                    'lines': [],
                    'total_qty': 0.0,
                    'total_amount': 0.0
                }
            grouped_data[vendor]['lines'].append(line)
            grouped_data[vendor]['total_qty'] += line.product_qty
            grouped_data[vendor]['total_amount'] += line.price_subtotal

        # Trả dữ liệu về cho file XML QWeb để vẽ khung giao diện PDF
        return {
            'docs': docids,
            'date_from': date_from,
            'date_to': date_to,
            'grouped_data': grouped_data,
            'report_style': chosen_style,
        }