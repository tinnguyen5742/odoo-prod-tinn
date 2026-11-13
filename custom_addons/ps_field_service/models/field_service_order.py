from odoo import models, fields, api, Command


class FieldServiceOrder(models.Model):
    _name = 'field.service.order'
    _description = 'Phiếu dịch vụ hiện trường'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sla_deadline asc, priority desc, id desc'

    name = fields.Char(string='Mã phiếu', required=True, copy=False, readonly=True, default='New')
    customer_id = fields.Many2one('res.partner', string='Khách hàng', required=True, tracking=True)
    address = fields.Char(string='Địa điểm thực hiện', related='customer_id.contact_address', store=True, readonly=False)

    # 1. Định vị GPS & Khu vực
    latitude = fields.Float(string='Vĩ độ (Latitude)', digits=(16, 8))
    longitude = fields.Float(string='Kinh độ (Longitude)', digits=(16, 8))
    area_id = fields.Many2one('field.service.area', string='Khu vực dịch vụ')
    technician_id = fields.Many2one(
        'res.users',
        string='Kỹ thuật viên phụ trách',
        domain="[('service_area_id', '=', area_id)]",
        tracking=True
    )

    state = fields.Selection([
        ('draft', 'Mới tạo'),
        ('assigned', 'Đã phân công'),
        ('in_progress', 'Đang xử lý'),
        ('done', 'Đã hoàn thành'),
        ('cancel', 'Đã hủy')
    ], string='Trạng thái', default='draft', tracking=True)

    # 2. Quản lý thiết bị của khách hàng (Asset Tracking)
    asset_id = fields.Many2one('customer.asset', string='Thiết bị / Máy móc cần bảo trì', tracking=True)

    priority = fields.Selection([
        ('0', 'Thấp'),
        ('1', 'Bình thường'),
        ('2', 'Cao'),
        ('3', 'Khẩn cấp')
    ], string='Mức độ ưu tiên', default='1', tracking=True)

    scheduled_date = fields.Datetime(string='Thời gian hẹn', tracking=True)
    description = fields.Text(string='Mô tả chi tiết sự cố & Tài liệu kỹ thuật')

    # Vật tư kho trên xe
    line_ids = fields.One2many('field.service.line', 'order_id', string='Vật tư / Linh kiện sử dụng')

    # 3. Chi phí phát sinh tại hiện trường (Expense tracking)
    expense_ids = fields.One2many('field.service.expense', 'order_id', string='Chi phí phát sinh')
    total_expense = fields.Float(string='Tổng chi phí phát sinh', compute='_compute_total_expense', store=True)

    # 4. Liên kết Hóa đơn tự động sinh ra khi hoàn thành
    invoice_id = fields.Many2one('account.move', string='Hóa đơn liên quan', readonly=True, copy=False)

    # SLA & KPI
    sla_deadline = fields.Datetime(string='Hạn chót SLA (Cam kết)', tracking=True)
    is_sla_failed = fields.Boolean(string='Vi phạm SLA', compute='_compute_sla_status', store=True)
    is_under_warranty = fields.Boolean(string='Còn hạn bảo hành thiết bị', default=True, tracking=True)

    first_time_fix = fields.Boolean(string='Sửa chữa thành công lần đầu (FTFR)', default=True, tracking=True)
    processing_hours = fields.Float(string='Thời gian xử lý (Giờ)', tracking=True)

    customer_signature = fields.Image(string='Chữ ký khách hàng xác nhận', copy=False, attachment=True)
    resolution_notes = fields.Text(string='Ghi chú kết quả sửa chữa', tracking=True)

    def action_open_google_maps(self):
        self.ensure_one()
        # Lấy địa chỉ từ khách hàng hoặc trường địa chỉ trên phiếu
        address_to_search = self.address or (self.customer_id and self.customer_id.contact_address)
        if not address_to_search:
            return

        # Thay thế khoảng trắng bằng dấu cộng để chuẩn hóa URL tìm kiếm của Google Maps
        formatted_address = address_to_search.replace('\n', ' ').replace(' ', '+')
        url = f"https://www.google.com/maps/search/?api=1&query={formatted_address}"

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_batch_optimize_route(self):
        """Hàm xử lý tối ưu tuyến đường cho danh sách được chọn"""
        for record in self:
            if record.technician_id:
                target_date = record.scheduled_date and record.scheduled_date.strftime('%Y-%m-%d') or fields.Date.today().strftime('%Y-%m-%d')
                record.action_optimize_route_by_area(record.technician_id.id, target_date)
        return True

    @api.depends('expense_ids.amount')
    def _compute_total_expense(self):
        for rec in self:
            rec.total_expense = sum(expense.amount for expense in rec.expense_ids)

    @api.depends('sla_deadline', 'state')
    def _compute_sla_status(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.sla_deadline and rec.state not in ('done', 'cancel'):
                rec.is_sla_failed = now > rec.sla_deadline
            else:
                rec.is_sla_failed = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('field.service.order') or 'FSO/'
        return super().create(vals_list)

    def action_assign(self):
        for rec in self:
            rec.state = 'assigned'

    def action_in_progress(self):
        for rec in self:
            rec.state = 'in_progress'

    # Tự động tạo Hóa đơn (Invoice) khi bấm Hoàn thành & Nghiệm thu
    def action_done(self):
        for rec in self:
            rec.state = 'done'

            invoice_lines = []
            for line in rec.line_ids:
                invoice_lines.append(Command.create({
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                    'price_unit': line.product_id.lst_price,
                    'name': line.note or line.product_id.name,
                }))

            # Tìm tài khoản doanh thu mặc định nếu có chi phí phát sinh
            income_account = False
            if rec.expense_ids:
                income_account = self.env['account.account'].search([
                    ('company_id', '=', (rec.customer_id.company_id or self.env.company).id),
                    ('account_type', 'in', ('income', 'income_other'))
                ], limit=1)

            for exp in rec.expense_ids:
                exp_data = {
                    'name': f"Phí phát sinh: {exp.name}",
                    'quantity': 1.0,
                    'price_unit': exp.amount,
                }
                if income_account:
                    exp_data['account_id'] = income_account.id
                invoice_lines.append(Command.create(exp_data))

            if invoice_lines:
                move_vals = {
                    'move_type': 'out_invoice',
                    'partner_id': rec.customer_id.id,
                    'invoice_date': fields.Date.today(),
                    'invoice_line_ids': invoice_lines,
                }
                invoice = self.env['account.move'].create(move_vals)
                rec.invoice_id = invoice.id

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancel'

    # Hàm tính toán khoảng cách GPS hỗ trợ Tối ưu hóa lộ trình
    @api.model
    def action_optimize_route_by_area(self, technician_id, target_date):
        """
        Thuật toán tối ưu tuyến đường dựa trên Khu vực dịch vụ (Area)
        khi sử dụng địa chỉ văn bản thay cho tọa độ GPS.
        """
        orders = self.search([
            ('technician_id', '=', technician_id),
            ('scheduled_date', '>=', f"{target_date} 00:00:00"),
            ('scheduled_date', '<=', f"{target_date} 23:59:59"),
            ('state', 'in', ['draft', 'assigned'])
        ])

        if not orders:
            return True

        # Sắp xếp các phiếu công tác theo nhóm Khu vực (area_id)
        sorted_orders = sorted(orders, key=lambda o: o.area_id.id if o.area_id else 0)

        # Tự động cập nhật mức độ ưu tiên (priority) theo thứ tự nhóm khu vực đã gom
        for index, ord_rec in enumerate(sorted_orders):
            priority_val = str(min(3, max(1, 3 - int(index / 3))))
            ord_rec.priority = priority_val

        return True


# Model quản lý thiết bị của khách hàng (Customer Asset)
class CustomerAsset(models.Model):
    _name = 'customer.asset'
    _description = 'Thiết bị / Tài sản khách hàng'

    name = fields.Char(string='Tên thiết bị / Model', required=True)
    serial_no = fields.Char(string='Số Serial / Barcode', required=True)
    partner_id = fields.Many2one('res.partner', string='Khách hàng sở hữu', required=True)
    install_date = fields.Date(string='Ngày lắp đặt')
    warranty_expiry_date = fields.Date(string='Hạn bảo hành')


# Model chi phí phát sinh tại hiện trường
class FieldServiceExpense(models.Model):
    _name = 'field.service.expense'
    _description = 'Chi phí phát sinh hiện trường'

    order_id = fields.Many2one('field.service.order', string='Phiếu dịch vụ', required=True, ondelete='cascade')
    name = fields.Char(string='Mô tả chi phí (Xăng xe, Cầu đường...)', required=True)
    amount = fields.Float(string='Số tiền', required=True)
    note = fields.Char(string='Ghi chú')


class FieldServiceLine(models.Model):
    _name = 'field.service.line'
    _description = 'Chi tiết vật tư dịch vụ'

    order_id = fields.Many2one('field.service.order', string='Phiếu dịch vụ', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Linh kiện / Phụ tùng', required=True)
    quantity = fields.Float(string='Số lượng', default=1.0)
    note = fields.Char(string='Ghi chú kỹ thuật')
