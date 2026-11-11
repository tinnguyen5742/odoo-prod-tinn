from odoo import models, api

class ReportPoNotReceived(models.AbstractModel):
    _name = 'report.custom_purchase.report_po_not_received_template'
    _description = 'Mã xử lý dữ liệu cho báo cáo PO chưa nhận'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form_data')
        date_to = form_data.get('date_to')
        partner_id = form_data.get('partner_id')

        # Logic tìm các PO chưa nhận đủ hàng (qty_received < product_qty)
        domain = [('state', 'in', ['purchase', 'done'])]
        if partner_id:
            domain.append(('partner_id', '=', partner_id[0]))
            
        po_lines = self.env['purchase.order.line'].search(domain).filtered(
            lambda l: l.qty_received < l.product_qty
        )

        # Gom nhóm theo PO giống mẫu báo cáo của bạn
        grouped_data = {}
        for line in po_lines:
            po = line.order_id
            if po not in grouped_data:
                grouped_data[po] = []
            grouped_data[po].append(line)

        return {
            'docs': docids,
            'date_to': date_to,
            'grouped_data': grouped_data,
        }