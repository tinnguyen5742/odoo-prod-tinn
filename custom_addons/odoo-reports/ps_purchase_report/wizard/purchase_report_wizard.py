from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime

class PurchaseReportWizard(models.TransientModel):
    _name = 'purchase.report.wizard'
    _description = 'Cửa sổ xuất báo cáo mua hàng'

    report_type = fields.Selection([
        ('report_1', 'Tổng hợp giá trị mua hàng theo năm'),
        ('report_2', 'Tổng hợp mua hàng theo Vật tư NCC'),
        ('report_3', 'Bảng kê phiếu nhập mua theo PO'),
        ('report_4', 'Bảng kê tình hình thực hiện đơn hàng'),
        ('report_5', 'Báo cáo so sánh giá'),
        ('report_6', 'Báo cáo thống kê PO chưa nhận hàng'),
        ('report_7', 'Bảng kê chi tiết mua hàng theo nhà cung cấp'),
        ('report_8', 'Báo cáo kế hoạch giao hàng theo PO'),
        ('report_9', 'Báo cáo theo dõi yêu cầu mua hàng Full QT'),
        ('report_10', 'Báo cáo theo dõi yêu cầu mua hàng'),
    ], string='Loại báo cáo', required=True, default='report_1')

    report_style = fields.Selection([
        ('classic', 'Executive (Cổ điển & Trang trọng)'),
        ('modern', 'Dynamic Corporate (Hiện đại & Tươi sáng)'),
        ('minimalist', 'Minimalist Clean (Tối giản tinh tế)')
    ], string='Mẫu giao diện', default='modern', required=True)

    # Thêm trường chọn cấu hình chữ ký trên Wizard
    signature_type = fields.Selection([
        ('one', '1 Người ký (Chỉ Người lập)'),
        ('two', '2 Người ký (Người lập & Trưởng phòng Mua hàng)')
    ], string='Cấu hình chữ ký', default='one', required=True)

    primary_color = fields.Char(string='Mã màu chủ đạo (Hex)', default='#0056b3', help="Nhập mã màu Hex, ví dụ: #0056b3 cho xanh dương, #2e8b57 cho xanh lá...")
    date_from = fields.Date(
        string='Từ ngày', 
        required=True, 
        default=lambda self: fields.Date.context_today(self).replace(day=1)
    )
    date_to = fields.Date(
        string='Đến ngày', 
        required=True, 
        default=fields.Date.context_today
    )
    partner_id = fields.Many2one('res.partner', string='Nhà cung cấp (Mã KH)')
    product_id = fields.Many2one('product.product', string='Vật tư/Hàng hóa')

    def action_print_pdf(self):
        form_data = self.read()[0]
        data = {
            'form_data': form_data,
        }

        report_type = form_data.get('report_type')

        if report_type == 'report_1':
            return self.env.ref('ps_purchase_report.action_report_purchase_by_year').report_action(self, data=data)
        elif report_type == 'report_2':
            return self.env.ref('ps_purchase_report.action_report_purchase_by_vendor').report_action(self, data=data)
        elif report_type == 'report_3':
            return self.env.ref('ps_purchase_report.action_report_purchase_by_po').report_action(self, data=data)
        elif report_type == 'report_4':
            return self.env.ref('ps_purchase_report.action_report_purchase_execution').report_action(self, data=data)
        elif report_type == 'report_5':
            return self.env.ref('ps_purchase_report.action_report_price_comparison').report_action(self, data=data)
        elif report_type == 'report_6':
            return self.env.ref('ps_purchase_report.action_report_unreceived_po').report_action(self, data=data)
        elif report_type == 'report_7':
            return self.env.ref('ps_purchase_report.action_report_purchase_detail_vendor').report_action(self, data=data)
        elif report_type == 'report_8':
            return self.env.ref('ps_purchase_report.action_report_delivery_plan').report_action(self, data=data)
        elif report_type == 'report_9':
            return self.env.ref('ps_purchase_report.action_report_full_process').report_action(self, data=data)
        elif report_type == 'report_10':
            return self.env.ref('ps_purchase_report.action_report_tracking').report_action(self, data=data)
        else:
            raise UserError('Báo cáo này đang trong quá trình phát triển!')
    
    def action_export_excel(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Thông báo',
                'message': 'Tính năng xuất Excel đang được phát triển!',
                'type': 'info',
                'sticky': False,
            }
        }


# ================= BÁO CÁO 1 =================
class ReportPurchaseByYear(models.AbstractModel):
    _name = 'report.ps_purchase_report.report_purchase_by_year_template'
    _description = 'Logic xử lý Báo cáo Tổng hợp giá trị mua hàng theo năm'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form_data', {}) if data else {}
        report_style = form_data.get('report_style', 'modern')
        primary_color = form_data.get('primary_color', '#0056b3')
        date_from = form_data.get('date_from')
        
        year = datetime.strptime(str(date_from), '%Y-%m-%d').year if date_from else datetime.now().year
        date_start = f'{year}-01-01 00:00:00'
        date_end = f'{year}-12-31 23:59:59'

        domain = [
            ('order_id.state', 'in', ['purchase', 'done']),
            ('order_id.date_order', '>=', date_start),
            ('order_id.date_order', '<=', date_end),
        ]
        lines = self.env['purchase.order.line'].search(domain)

        matrix = {}
        monthly_totals = {m: 0.0 for m in range(1, 13)}
        grand_total = 0.0

        for line in lines:
            vendor = line.partner_id
            if not vendor:
                continue
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
            'report_style': report_style,
            'primary_color': primary_color,
            'year': year,
            'matrix': matrix,
            'monthly_totals': monthly_totals,
            'grand_total': grand_total,
            'company': self.env.company,
            'print_date': datetime.now().strftime('%d tháng %m năm %Y'),
        }


# ================= BÁO CÁO 3 =================
class ReportPurchaseByPo(models.AbstractModel):
    _name = 'report.ps_purchase_report.report_purchase_by_po_template'
    _description = 'Logic xử lý Bảng kê phiếu nhập mua theo PO'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form_data', {}) if data else {}
        date_from = form_data.get('date_from')
        date_to = form_data.get('date_to')
        partner_id = form_data.get('partner_id')
        report_style = form_data.get('report_style', 'modern')
        primary_color = form_data.get('primary_color', '#0056b3')

        domain = [('state', 'in', ['purchase', 'done'])]
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if partner_id:
            domain.append(('partner_id', '=', partner_id))

        orders = self.env['purchase.order'].search(domain, order='date_order asc')

        return {
            'docs': docids,
            'orders': orders,
            'date_from': date_from,
            'date_to': date_to,
            'report_style': report_style,
            'primary_color': primary_color,
            'company': self.env.company,
        }


# ================= BÁO CÁO 4 =================
class ReportPurchaseExecution(models.AbstractModel):
    _name = 'report.ps_purchase_report.report_purchase_execution_template'
    _description = 'Logic xử lý Bảng kê tình hình thực hiện đơn hàng'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form_data', {}) if data else {}
        date_from = form_data.get('date_from')
        date_to = form_data.get('date_to')
        partner_id = form_data.get('partner_id')
        product_id = form_data.get('product_id')
        report_style = form_data.get('report_style', 'modern')
        primary_color = form_data.get('primary_color', '#0056b3')

        domain = [('order_id.state', 'in', ['purchase', 'done'])]
        if date_from:
            domain.append(('order_id.date_order', '>=', date_from))
        if date_to:
            domain.append(('order_id.date_order', '<=', date_to))
        if partner_id:
            domain.append(('order_id.partner_id', '=', partner_id))
        if product_id:
            domain.append(('product_id', '=', product_id))

        lines = self.env['purchase.order.line'].search(domain, order='order_id asc')

        return {
            'docs': docids,
            'lines': lines,
            'date_from': date_from,
            'date_to': date_to,
            'report_style': report_style,
            'primary_color': primary_color,
            'company': self.env.company,
        }


# ================= BÁO CÁO 5 =================
class ReportPurchasePriceComparison(models.AbstractModel):
    _name = 'report.ps_purchase_report.report_price_comparison_template'
    _description = 'Logic xử lý Báo cáo so sánh giá mua hàng'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form_data', {}) if data else {}
        date_from = form_data.get('date_from')
        date_to = form_data.get('date_to')
        product_id = form_data.get('product_id')
        report_style = form_data.get('report_style', 'modern')
        primary_color = form_data.get('primary_color', '#0056b3')

        domain = [('order_id.state', 'in', ['purchase', 'done'])]
        if date_from:
            domain.append(('order_id.date_order', '>=', date_from))
        if date_to:
            domain.append(('order_id.date_order', '<=', date_to))
        if product_id:
            domain.append(('product_id', '=', product_id))

        lines = self.env['purchase.order.line'].search(domain, order='product_id, price_unit asc')

        return {
            'docs': docids,
            'lines': lines,
            'date_from': date_from,
            'date_to': date_to,
            'report_style': report_style,
            'primary_color': primary_color,
            'company': self.env.company,
        }


# ================= BÁO CÁO 6 =================
class ReportUnreceivedPurchase(models.AbstractModel):
    _name = 'report.ps_purchase_report.report_unreceived_po_template'
    _description = 'Logic xử lý Báo cáo thống kê PO chưa nhận hàng'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form_data', {}) if data else {}
        date_from = form_data.get('date_from')
        date_to = form_data.get('date_to')
        partner_id = form_data.get('partner_id')
        report_style = form_data.get('report_style', 'modern')
        primary_color = form_data.get('primary_color', '#0056b3')

        domain = [('state', 'in', ['purchase', 'done'])]
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if partner_id:
            domain.append(('partner_id', '=', partner_id))

        orders = self.env['purchase.order'].search(domain, order='date_order asc')
        unreceived_orders = orders.filtered(lambda po: any(line.qty_received < line.product_qty for line in po.order_line))

        return {
            'docs': docids,
            'orders': unreceived_orders,
            'date_from': date_from,
            'date_to': date_to,
            'report_style': report_style,
            'primary_color': primary_color,
            'company': self.env.company,
        }


# ================= BÁO CÁO 7 =================
class ReportPurchaseDetailByVendor(models.AbstractModel):
    _name = 'report.ps_purchase_report.purchase_detail_vendor_template'
    _description = 'Logic xử lý Bảng kê chi tiết mua hàng theo nhà cung cấp'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form_data', {}) if data else {}
        date_from = form_data.get('date_from')
        date_to = form_data.get('date_to')
        partner_id = form_data.get('partner_id')
        report_style = form_data.get('report_style', 'modern')
        primary_color = form_data.get('primary_color', '#0056b3')

        domain = [('state', 'in', ['purchase', 'done'])]
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if partner_id:
            domain.append(('partner_id', '=', partner_id))

        orders = self.env['purchase.order'].search(domain, order='partner_id, date_order asc')

        return {
            'docs': docids,
            'orders': orders,
            'date_from': date_from,
            'date_to': date_to,
            'report_style': report_style,
            'primary_color': primary_color,
            'company': self.env.company,
        }


# ================= BÁO CÁO 8 =================
class ReportPurchaseDeliveryPlan(models.AbstractModel):
    _name = 'report.ps_purchase_report.report_delivery_plan_template'
    _description = 'Logic xử lý Báo cáo kế hoạch giao hàng theo PO'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form_data', {}) if data else {}
        date_from = form_data.get('date_from')
        date_to = form_data.get('date_to')
        partner_id = form_data.get('partner_id')
        report_style = form_data.get('report_style', 'modern')
        primary_color = form_data.get('primary_color', '#0056b3')

        domain = [('order_id.state', 'in', ['purchase', 'done'])]
        if date_from:
            domain.append(('order_id.date_order', '>=', date_from))
        if date_to:
            domain.append(('order_id.date_order', '<=', date_to))
        if partner_id:
            domain.append(('order_id.partner_id', '=', partner_id))

        lines = self.env['purchase.order.line'].search(domain, order='date_planned asc')

        return {
            'docs': docids,
            'lines': lines,
            'date_from': date_from,
            'date_to': date_to,
            'report_style': report_style,
            'primary_color': primary_color,
            'company': self.env.company,
        }


# ================= BÁO CÁO 9 =================
class ReportPurchaseFullProcess(models.AbstractModel):
    _name = 'report.ps_purchase_report.report_full_process_template'
    _description = 'Logic xử lý Báo cáo theo dõi yêu cầu mua hàng Full quy trình'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form_data', {}) if data else {}
        date_from = form_data.get('date_from')
        date_to = form_data.get('date_to')
        partner_id = form_data.get('partner_id')
        report_style = form_data.get('report_style', 'modern')
        primary_color = form_data.get('primary_color', '#0056b3')

        domain = [('state', 'in', ['purchase', 'done', 'to approve'])]
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if partner_id:
            domain.append(('partner_id', '=', partner_id))

        lines = self.env['purchase.order.line'].search(domain, order='date_order asc')

        return {
            'docs': docids,
            'lines': lines,
            'date_from': date_from,
            'date_to': date_to,
            'report_style': report_style,
            'primary_color': primary_color,
            'company': self.env.company,
        }


# ================= BÁO CÁO 10 =================
class ReportPurchaseTracking(models.AbstractModel):
    _name = 'report.ps_purchase_report.report_tracking_template'
    _description = 'Logic xử lý Báo cáo theo dõi yêu cầu mua hàng'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form_data', {}) if data else {}
        date_from = form_data.get('date_from')
        date_to = form_data.get('date_to')
        partner_id = form_data.get('partner_id')
        report_style = form_data.get('report_style', 'modern')
        primary_color = form_data.get('primary_color', '#0056b3')

        domain = [('state', 'in', ['purchase', 'done', 'to approve'])]
        if date_from:
            domain.append(('date_order', '>=', date_from))
        if date_to:
            domain.append(('date_order', '<=', date_to))
        if partner_id:
            domain.append(('partner_id', '=', partner_id))

        lines = self.env['purchase.order.line'].search(domain, order='date_order asc')

        return {
            'docs': docids,
            'lines': lines,
            'date_from': date_from,
            'date_to': date_to,
            'report_style': report_style,
            'primary_color': primary_color,
            'company': self.env.company,
        }