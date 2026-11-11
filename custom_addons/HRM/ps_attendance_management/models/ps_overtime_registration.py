from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PsOvertimeRegistration(models.Model):
    _name = 'ps.overtime.registration'
    _description = 'Overtime Registration'
    _rec_name = 'x_name'
    _order = 'x_registration_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    x_name = fields.Char(
        string='Name',
        compute='_compute_x_name',
        store=True,
        tracking=True,
    )
    x_registration_date = fields.Date(
        string='Registration Date',
        default=fields.Date.today,
        required=True,
    )
    x_department_id = fields.Many2one(
        'hr.department',
        string='Department',
    )
    x_employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        help='Filter records by a specific employee.',
    )
    x_employee_ids = fields.Many2many(
        'hr.employee',
        string='Allowed Employees',
        compute='_compute_x_employee_ids',
        help='Employees filtered by the selected company and department.',
    )
    x_shift_id = fields.Many2one(
        'ps.work.shift',
        string='Work Shift',
        tracking=True,
        help='Default shift applied to loaded lines when no slot is found.',
    )
    x_date_from = fields.Date(
        string='Date From',
        required=True,
    )
    x_date_to = fields.Date(
        string='Date To',
        required=True,
    )
    x_time_from = fields.Float(
        string='Time From',
        help='Default start time applied to loaded lines (format 18.0 = 18:00).',
    )
    x_time_to = fields.Float(
        string='Time To',
        help='Default end time applied to loaded lines (format 20.0 = 20:00).',
    )
    x_overtime_hours = fields.Float(
        string='Overtime Hours',
        compute='_compute_x_overtime_hours',
        store=True,
    )
    x_notes = fields.Text(
        string='Notes',
    )
    x_state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
    )
    x_company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    x_line_ids = fields.One2many(
        'ps.overtime.registration.line',
        'x_registration_id',
        string='Registration Lines',
    )

    @api.depends('x_registration_date', 'x_department_id', 'x_employee_id')
    def _compute_x_name(self):
        # Sinh tên tự động: OT - Ngày - Bộ phận - Nhân viên
        for rec in self:
            parts = ['OT', str(rec.x_registration_date)]
            if rec.x_department_id:
                parts.append(rec.x_department_id.name)
            if rec.x_employee_id:
                parts.append(rec.x_employee_id.name)
            rec.x_name = ' - '.join(parts) or _('New Overtime Registration')

    @api.depends('x_company_id', 'x_department_id')
    def _compute_x_employee_ids(self):
        # Lọc nhân viên theo công ty và bộ phận đã chọn
        for rec in self:
            domain = [('company_id', '=', rec.x_company_id.id)]
            if rec.x_department_id:
                domain.append(('department_id', '=', rec.x_department_id.id))
            rec.x_employee_ids = self.env['hr.employee'].sudo().search(domain)

    @api.depends('x_line_ids.x_overtime_hours')
    def _compute_x_overtime_hours(self):
        # Tổng số giờ tăng ca(field đến giờ - từ giờ) 
        for rec in self:
            rec.x_overtime_hours = rec.x_time_to - rec.x_time_from

    @api.onchange('x_company_id')
    def _onchange_company_id(self):
        # Khi đổi công ty: xóa bộ phận, nhân viên cũ
        self.x_department_id = False
        self.x_employee_id = False

    def action_load_employees(self):
        # Hỗ trợ lấy nhân viên: nạp danh sách nhân viên vào dòng chi tiết theo lịch phân ca
        self.ensure_one()
        if not self.x_date_from or not self.x_date_to:
            self.x_line_ids = [fields.Command.clear()]
            message = _('Please enter both Date From and Date To.')
            message_type = 'warning'
        else:
            count = self._load_employee_lines()
            if count:
                message = _('Employee list updated according to the shift schedule.')
                message_type = 'success'
            else:
                message = _('No matching shift schedule found.')
                message_type = 'warning'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': message_type,
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                },
            },
        }

    def _load_employee_lines(self):
        # Nạp nhân viên theo lịch phân ca (ps.work.shift.slot) vào các dòng chi tiết.
        # Mỗi dòng = 1 nhân viên + 1 ngày + ca theo đúng slot tìm được.
        # Nếu nhân viên không có slot phù hợp trong khoảng ngày thì không tạo dòng.
        self.ensure_one()
        self.x_line_ids = [fields.Command.clear()]
        if not self.x_date_from or not self.x_date_to:
            return 0

        company_id = self.x_company_id.id if self.x_company_id else self.env.company.id
        employee_domain = [('company_id', '=', company_id)]
        if self.x_employee_id:
            employee_domain.append(('id', '=', self.x_employee_id.id))
        elif self.x_department_id:
            employee_domain.append(('department_id', '=', self.x_department_id.id))

        employees = self.env['hr.employee'].sudo().search(employee_domain)
        if not employees:
            return 0

        slot_domain = [
            ('x_employee_id', 'in', employees.ids),
            ('x_date', '>=', self.x_date_from),
            ('x_date', '<=', self.x_date_to),
        ]
        if self.x_shift_id:
            slot_domain.append(('x_shift_id', '=', self.x_shift_id.id))

        slots = self.env['ps.work.shift.slot'].sudo().search(slot_domain)
        if not slots:
            return 0

        commands = [fields.Command.clear()]
        for slot in slots:
            commands.append(fields.Command.create({
                'x_employee_id': slot.x_employee_id.id,
                'x_date_from': slot.x_date,
                'x_date_to': slot.x_date,
                'x_shift_id': slot.x_shift_id.id,
                'x_time_from': self.x_time_from,
                'x_time_to': self.x_time_to,
            }))
        self.x_line_ids = commands
        return len(slots)

    def _get_slot_recompute_data(self):
        """Trả về tập (employee_id, date) từ các dòng chi tiết để recompute slot."""
        self.ensure_one()
        data = set()
        for line in self.x_line_ids:
            if line.x_employee_id and line.x_date_from:
                data.add((line.x_employee_id.id, line.x_date_from))
        return data

    def action_confirm(self):
        # Xác nhận đăng ký: kiểm tra có dòng chi tiết, giờ hợp lệ và trùng lặp với các phiếu đã confirmed
        for rec in self:
            if not rec.x_line_ids:
                raise ValidationError(_('No employees have been assigned overtime.'))

            # Kiểm tra giờ ở header
            if not rec.x_time_from or not rec.x_time_to:
                raise ValidationError(_('Please enter the overtime start time and end time.'))
            if rec.x_time_to <= rec.x_time_from:
                raise ValidationError(_('Time To must be after Time From.'))

            # Kiểm tra giờ ở từng dòng chi tiết
            for line in rec.x_line_ids:
                if not line.x_time_from or not line.x_time_to:
                    raise ValidationError(_('Please enter the overtime start time and end time.'))
                if line.x_time_to <= line.x_time_from:
                    raise ValidationError(_('Time To must be after Time From.'))

            # Kiểm tra tăng ca không được nằm trong giờ làm việc của ca chính
            for line in rec.x_line_ids:
                if not line.x_shift_id:
                    raise ValidationError(_('Work shift is required on the detail line.'))
                if line.x_shift_id.overtime_overlaps(line.x_time_from, line.x_time_to):
                    shift = line.x_shift_id
                    raise ValidationError(
                        _(
                            'Overtime time of employee %(employee)s on %(date)s must not overlap with working hours of shift %(shift)s (%(shift_start)s - %(shift_end)s).',
                            employee=line.x_employee_id.name,
                            date=line.x_date_from,
                            shift=shift.x_shift_name,
                            shift_start=shift._format_time(shift.x_start_time),
                            shift_end=shift._format_time(shift.x_end_time),
                        )
                    )

            # Kiểm tra trùng lặp với các phiếu đã confirmed
            for line in rec.x_line_ids:
                if not line.x_employee_id or not line.x_date_from:
                    continue
                domain = [
                    ('x_registration_id', '!=', rec.id),
                    ('x_employee_id', '=', line.x_employee_id.id),
                    ('x_date_from', '=', line.x_date_from),
                    ('x_registration_id.x_state', '=', 'confirmed'),
                    ('x_time_from', '<', line.x_time_to),
                    ('x_time_to', '>', line.x_time_from),
                ]
                if self.env['ps.overtime.registration.line'].search_count(domain, limit=1):
                    raise ValidationError(
                        _(
                            'Employee %(employee)s already has a confirmed overtime registration on %(date)s that overlaps with this time range.',
                            employee=line.x_employee_id.name,
                            date=line.x_date_from,
                        )
                    )
        self.write({'x_state': 'confirmed'})
        self.env.flush_all()
        # Cập nhật lịch phân ca theo các dòng tăng ca vừa xác nhận
        Slot = self.env['ps.work.shift.slot']
        for rec in self:
            data = rec._get_slot_recompute_data()
            if data:
                Slot._recompute_overtime_for(
                    {d[0] for d in data},
                    {d[1] for d in data},
                )

    def action_draft(self):
        # Chuyển bản ghi về trạng thái bản nháp, xóa thông tin tăng ca khỏi lịch phân ca
        # và hiển thị thông báo
        self.ensure_one()
        data = self._get_slot_recompute_data()
        self.write({'x_state': 'draft'})
        self.env.flush_all()
        if data:
            self.env['ps.work.shift.slot']._recompute_overtime_for(
                {d[0] for d in data},
                {d[1] for d in data},
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('The overtime registration has been moved back to draft. You can now edit the information and confirm again.'),
                'type': 'warning',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                },
            }
        }

    def unlink(self):
        # Xóa dữ liệu tăng ca trên lịch phân ca trước khi xóa phiếu
        data = set()
        for rec in self:
            data.update(rec._get_slot_recompute_data())
        result = super(PsOvertimeRegistration, self).unlink()
        if data:
            self.env['ps.work.shift.slot']._recompute_overtime_for(
                {d[0] for d in data},
                {d[1] for d in data},
            )
        return result

    def write(self, vals):
        # Khi đã confirmed: chỉ cho phép chuyển về draft, không được sửa thông tin
        if not vals:
            return super(PsOvertimeRegistration, self).write(vals)
        for rec in self:
            if rec.x_state == 'confirmed':
                if set(vals.keys()) != {'x_state'} or vals.get('x_state') != 'draft':
                    raise ValidationError(
                        _('A confirmed overtime registration cannot be edited. Please set it back to draft first.')
                    )
        return super(PsOvertimeRegistration, self).write(vals)

    @api.constrains('x_date_from', 'x_date_to')
    def _check_date_range(self):
        # Kiểm tra đến ngày phải sau hoặc bằng từ ngày
        for rec in self:
            if rec.x_date_from and rec.x_date_to and rec.x_date_to < rec.x_date_from:
                raise ValidationError(_('Date To must be after Date From.'))

    @api.constrains('x_time_from', 'x_time_to')
    def _check_time_range(self):
        # Kiểm tra đến giờ phải sau từ giờ (chỉ áp dụng khi cả 2 đều có giá trị)
        for rec in self:
            if rec.x_time_from and rec.x_time_to and rec.x_time_to <= rec.x_time_from:
                raise ValidationError(_('Time To must be after Time From.'))

    @api.constrains('x_time_from', 'x_time_to')
    def _check_time_valid(self):
        for rec in self:
            if rec.x_time_from and (rec.x_time_from < 0 or rec.x_time_from > 24):
                raise ValidationError(_('Time From must be between 0:00 and 24:00.'))
            if rec.x_time_to and (rec.x_time_to < 0 or rec.x_time_to > 24):
                raise ValidationError(_('Time To must be between 0:00 and 24:00.'))

    @api.constrains('x_line_ids')
    def _check_line_overlap(self):
        # Kiểm tra trùng lặp trong cùng bản ghi: cùng nhân viên, cùng ngày, giờ giao nhau
        for rec in self:
            intervals = []
            for line in rec.x_line_ids:
                if not line.x_employee_id or not line.x_date_from or line.x_time_to <= line.x_time_from:
                    continue
                for other_employee_id, other_date, other_from, other_to in intervals:
                    if (other_employee_id == line.x_employee_id.id and
                            other_date == line.x_date_from and
                            other_from < line.x_time_to and
                            other_to > line.x_time_from):
                        raise ValidationError(
                            _(
                                'Employee %(employee)s has overlapping overtime lines on %(date)s.',
                                employee=line.x_employee_id.name,
                                date=line.x_date_from,
                            )
                        )
                intervals.append((line.x_employee_id.id, line.x_date_from, line.x_time_from, line.x_time_to))


class PsOvertimeRegistrationLine(models.Model):
    _name = 'ps.overtime.registration.line'
    _description = 'Overtime Registration Line'
    _order = 'x_date_from, id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    x_registration_id = fields.Many2one(
        'ps.overtime.registration',
        string='Registration',
        required=True,
        ondelete='cascade',
    )
    x_employee_ids = fields.Many2many(
        'hr.employee',
        string='Allowed Employees',
        related='x_registration_id.x_employee_ids',
        help='Employees filtered by the selected company and department.',
    )
    x_employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
    )
    x_employee_code = fields.Char(
        string='Employee Code',
        compute='_compute_x_employee_code',
    )
    x_department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='x_employee_id.department_id',
        store=True,
        readonly=True,
    )
    x_date_from = fields.Date(
        string='Date From',
        required=True,
    )
    x_date_to = fields.Date(
        string='Date To',
        required=True,
    )
    x_shift_id = fields.Many2one(
        'ps.work.shift',
        string='Work Shift',
        help='Ca làm việc gốc của nhân viên theo lịch phân ca.',
    )
    x_shift_display = fields.Char(
        string='Shift',
        compute='_compute_x_shift_display',
    )
    x_time_from = fields.Float(
        string='Time From',
        help='Overtime start time (format 18.0 = 18:00).',
    )
    x_time_to = fields.Float(
        string='Time To',
        help='Overtime end time (format 20.0 = 20:00).',
    )
    x_overtime_hours = fields.Float(
        string='Overtime Hours',
        compute='_compute_x_overtime_hours',
        store=True,
    )
    x_notes = fields.Char(
        string='Notes',
    )
    x_state = fields.Selection(
        related='x_registration_id.x_state',
        string='Status',
        store=True,
        readonly=True,
    )
    x_company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='x_registration_id.x_company_id',
        store=True,
        readonly=True,
    )

    @api.depends('x_employee_id')
    def _compute_x_employee_code(self):
        # Lấy mã nhân viên
        for line in self:
            emp = line.x_employee_id
            code = False
            if emp:
                code = getattr(emp, 'x_employee_code', False) or emp.barcode
            line.x_employee_code = code or ''

    @api.depends('x_shift_id')
    def _compute_x_shift_display(self):
        # Hiển thị tên ca kèm khung giờ: Tên ca (HH:MM - HH:MM)
        for line in self:
            shift = line.x_shift_id
            if shift:
                line.x_shift_display = (
                    f"{shift.x_shift_name} "
                    f"({shift._format_time(shift.x_start_time)} - "
                    f"{shift._format_time(shift.x_end_time)})"
                )
            else:
                line.x_shift_display = ''

    @api.depends('x_time_from', 'x_time_to', 'x_shift_id')
    def _compute_x_overtime_hours(self):
        # Tính số giờ tăng ca = đến giờ - từ giờ, có trừ nghỉ trưa nếu giao với khoảng tăng ca
        for line in self:
            if line.x_time_to <= line.x_time_from:
                line.x_overtime_hours = 0.0
                continue
            total = line.x_time_to - line.x_time_from
            lunch = 0.0
            shift = line.x_shift_id
            if shift and shift.x_has_lunch_break and shift.x_lunch_break_start and shift.x_lunch_break_end:
                ls = shift.x_lunch_break_start
                le = shift.x_lunch_break_end
                overlap_start = max(line.x_time_from, ls)
                overlap_end = min(line.x_time_to, le)
                if overlap_end > overlap_start:
                    lunch = overlap_end - overlap_start
            line.x_overtime_hours = max(total - lunch, 0.0)

    @api.constrains('x_date_from', 'x_date_to')
    def _check_date_range(self):
        # Kiểm tra đến ngày phải sau hoặc bằng từ ngày
        for line in self:
            if line.x_date_from and line.x_date_to and line.x_date_to < line.x_date_from:
                raise ValidationError(_('Date To must be after Date From.'))

    @api.constrains('x_time_from', 'x_time_to')
    def _check_time_range(self):
        # Kiểm tra đến giờ phải sau từ giờ (chỉ áp dụng khi cả 2 đều có giá trị)
        for line in self:
            if line.x_time_from and line.x_time_to and line.x_time_to <= line.x_time_from:
                raise ValidationError(_('Time To must be after Time From.'))

    @api.constrains('x_time_from', 'x_time_to')
    def _check_time_valid(self):
        for line in self:
            if line.x_time_from and (line.x_time_from < 0 or line.x_time_from > 24):
                raise ValidationError(_('Time From must be between 0:00 and 24:00.'))
            if line.x_time_to and (line.x_time_to < 0 or line.x_time_to > 24):
                raise ValidationError(_('Time To must be between 0:00 and 24:00.'))

    @api.model_create_multi
    def create(self, vals_list):
        # Không cho phép thêm dòng chi tiết khi phiếu đã confirmed
        for vals in vals_list:
            registration = self.env['ps.overtime.registration'].browse(vals.get('x_registration_id'))
            if registration.x_state == 'confirmed':
                raise ValidationError(_('Cannot add lines to a confirmed overtime registration.'))
        return super(PsOvertimeRegistrationLine, self).create(vals_list)

    def write(self, vals):
        # Không cho phép sửa dòng chi tiết khi phiếu đã confirmed
        if not vals:
            return super(PsOvertimeRegistrationLine, self).write(vals)
        for line in self:
            if line.x_registration_id.x_state == 'confirmed':
                raise ValidationError(_('Cannot edit lines of a confirmed overtime registration.'))
        return super(PsOvertimeRegistrationLine, self).write(vals)

    def unlink(self):
        # Khi xóa dòng của phiếu đã confirmed, cập nhật lại lịch phân ca
        data = set()
        for line in self:
            if line.x_registration_id.x_state == 'confirmed' and line.x_employee_id and line.x_date_from:
                data.add((line.x_employee_id.id, line.x_date_from))
        result = super(PsOvertimeRegistrationLine, self).unlink()
        if data:
            self.env['ps.work.shift.slot']._recompute_overtime_for(
                {d[0] for d in data},
                {d[1] for d in data},
            )
        return result
