from datetime import timedelta
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PsWorkScheduleRegistration(models.Model):
    _name = 'ps.work.schedule.registration'
    _description = 'Work Schedule Registration'
    _rec_name = 'x_name'
    _order = 'x_year desc, x_registration_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    x_name = fields.Char(
        string='Name',
        compute='_compute_x_name',
        store=True,
        tracking=True,
    )
    x_registration_type = fields.Selection(
        [
            ('week', 'Week'),
            ('month', 'Month'),
            ('day', 'Day'),
        ],
        string='Registration Type',
        default='week',
        required=True,
        tracking=True,
    )
    x_year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.today().year,
        tracking=True,
    )
    x_registration_date = fields.Date(
        string='Registration Date',
        default=fields.Date.today,
        required=True,
        tracking=True,
    )
    x_department_id = fields.Many2one(
        'hr.department',
        string='Department',
        tracking=True,
    )
    x_employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        tracking=True,
        help='Filter records by a specific employee.',
    )
    x_employee_ids = fields.Many2many(
        'hr.employee',
        string='Allowed Employees',
        compute='_compute_x_employee_ids',
        help='Danh sách nhân viên được lọc theo công ty và bộ phận.',
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
        default=lambda self: self.env.company,
        tracking=True,
    )
    x_line_ids = fields.One2many(
        'ps.work.schedule.registration.line',
        'x_registration_id',
        string='Registration Lines',
    )
    x_notes = fields.Text(
        string='Notes',
        tracking=True,
    )

    # Nhóm "Phân ca"
    x_assignment_mode = fields.Selection(
        [
            ('static', 'Fixed Shift'),
            ('rotation', 'Rotation'),
        ],
        string='Assignment Mode',
        default='static',
        required=True,
        tracking=True,
        help='Static: employee keeps a fixed shift (office/part-time). '
             'Rotation: employee follows a cycle rotation (production).',
    )
    x_fixed_shift_id = fields.Many2one(
        'ps.work.shift',
        string='Fixed Shift',
        tracking=True,
        help='Shift assigned when mode is Fixed Shift.',
    )
    x_rotation_id = fields.Many2one(
        'ps.shift.rotation',
        string='Rotation',
        tracking=True,
        help='Cycle rotation applied when mode is Rotation.',
    )

    # Các trường hỗ trợ áp dụng nhanh khoảng thời gian
    x_apply_all_week_ids = fields.Many2many(
        'ps.work.week',
        string='Áp dụng cho các tuần',
        default=lambda self: self.env['ps.work.week']._get_current_week(self.env.company.id),
        help='Chọn nhiều tuần để áp dụng cho tất cả nhân viên (loại đăng ký Tuần).',
    )
    x_apply_all_month_ids = fields.Many2many(
        'ps.work.month',
        string='Áp dụng cho các tháng',
        default=lambda self: self.env['ps.work.month'].search([('x_value', '=', str(fields.Date.today().month))]).ids,
        help='Chọn nhiều tháng để áp dụng cho tất cả nhân viên (loại đăng ký Tháng).',
    )
    x_apply_all_date_from = fields.Date(
        string='Apply All Date From',
        help='Set this start date for all detail lines when registration type is Day.',
    )
    x_apply_all_date_to = fields.Date(
        string='Apply All Date To',
        help='Set this end date for all detail lines when registration type is Day.',
    )

    @api.depends('x_registration_type', 'x_year', 'x_department_id', 'x_employee_id')
    def _compute_x_name(self):
        # Sinh tên tự động: [Loại] - Năm - Bộ phận - Nhân viên
        for rec in self:
            type_label = dict(rec._fields['x_registration_type'].selection).get(rec.x_registration_type, '')
            parts = [f"[{type_label}]", str(rec.x_year)]
            if rec.x_department_id:
                parts.append(rec.x_department_id.name)
            if rec.x_employee_id:
                parts.append(rec.x_employee_id.name)
            rec.x_name = ' - '.join(parts) or _('New Registration')

    @api.depends('x_company_id', 'x_department_id')
    def _compute_x_employee_ids(self):
        # Lọc nhân viên theo công ty và bộ phận đã chọn (lọc chặt theo công ty)
        # Dùng sudo() để bypass record rule đa công ty, luôn lấy đúng dữ liệu công ty đã chọn
        for rec in self:
            domain = [('company_id', '=', rec.x_company_id.id)]
            if rec.x_department_id:
                domain.append(('department_id', '=', rec.x_department_id.id))
            rec.x_employee_ids = self.env['hr.employee'].sudo().search(domain)

    @api.onchange('x_company_id')
    def _onchange_company_id(self):
        # Khi đổi công ty: xóa bộ phận / nhân viên cũ và nạp lại danh sách nhân viên theo công ty mới
        self.x_department_id = False
        self.x_employee_id = False
        self._load_employee_lines()

    @api.onchange('x_department_id', 'x_employee_id')
    def _onchange_department_id(self):
        # Khi chọn bộ phận / nhân viên: tự động nạp danh sách nhân viên vào các dòng chi tiết
        self._load_employee_lines()

    def _load_employee_lines(self):
        # Nạp nhân viên (theo bộ phận hoặc theo nhân viên cụ thể) vào các dòng chi tiết
        company_id = self.x_company_id.id if self.x_company_id else self.env.company.id
        domain = [('company_id', '=', company_id)]
        if self.x_employee_id:
            domain.append(('id', '=', self.x_employee_id.id))
        elif self.x_department_id:
            domain.append(('department_id', '=', self.x_department_id.id))
        else:
            self.x_line_ids = [fields.Command.clear()]
            return
        # Dùng sudo() để bypass record rule đa công ty
        employees = self.env['hr.employee'].sudo().search(domain)
        # Áp dụng giá trị header mặc định cho các dòng mới
        # Với loại Tuần: tạo 1 dòng cho mỗi tuần đã chọn
        commands = [fields.Command.clear()]
        for emp in employees:
            if self.x_registration_type == 'week':
                if self.x_apply_all_week_ids:
                    for week in self.x_apply_all_week_ids:
                        commands.append(fields.Command.create({
                            'x_employee_id': emp.id,
                            'x_week_id': week.id,
                        }))
                else:
                    commands.append(fields.Command.create({'x_employee_id': emp.id}))
            elif self.x_registration_type == 'month':
                if self.x_apply_all_month_ids:
                    for month in self.x_apply_all_month_ids:
                        commands.append(fields.Command.create({
                            'x_employee_id': emp.id,
                            'x_month': month.id,
                        }))
                else:
                    commands.append(fields.Command.create({'x_employee_id': emp.id}))
            else:
                vals = {'x_employee_id': emp.id}
                if self.x_registration_type == 'day':
                    if self.x_apply_all_date_from:
                        vals['x_date_from'] = self.x_apply_all_date_from
                    if self.x_apply_all_date_to:
                        vals['x_date_to'] = self.x_apply_all_date_to
                commands.append(fields.Command.create(vals))
        self.x_line_ids = commands

    @api.onchange('x_year')
    def _onchange_year(self):
        # Khi đổi năm: xóa giá trị tuần đã chọn, đảm bảo danh sách tuần của năm mới đã được sinh
        if self.x_year:
            self.env['ps.work.week']._generate_weeks_for_year(self.x_year, self.x_company_id.id or self.env.company.id)
        self.x_apply_all_week_ids = [(5, 0, 0)]
        for line in self.x_line_ids:
            line.x_week_id = False
        return {'domain': {'x_apply_all_week_ids': [('x_year', '=', self.x_year)]}}

    def action_refresh_weeks(self):
        # Sinh lại tuần cho năm hiện tại (không xoá tuần các năm khác để tránh phá dữ liệu confirmed)
        self.ensure_one()
        if not self.x_year:
            return True
        company = self.x_company_id or self.env.company
        self.env['ps.work.week']._generate_weeks_for_year(self.x_year, company.id)
        self.x_apply_all_week_ids = [(5, 0, 0)]
        for line in self.x_line_ids:
            line.x_week_id = False
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.onchange('x_assignment_mode')
    def _onchange_assignment_mode(self):
        # Khi đổi chế độ phân ca: xóa giá trị không phù hợp
        if self.x_assignment_mode == 'static':
            self.x_rotation_id = False
        elif self.x_assignment_mode == 'rotation':
            self.x_fixed_shift_id = False

    @api.onchange('x_apply_all_week_ids')
    def _onchange_apply_all_week(self):
        # Khi chọn tuần ở header: xóa dòng cũ và tạo lại dòng chi tiết theo các tuần đã chọn
        if self.x_registration_type == 'week':
            self._load_employee_lines()

    @api.onchange('x_apply_all_month_ids')
    def _onchange_apply_all_month(self):
        # Khi chọn tháng ở header: xóa dòng cũ và tạo lại dòng chi tiết theo các tháng đã chọn
        if self.x_registration_type == 'month':
            self._load_employee_lines()

    @api.onchange('x_apply_all_date_from')
    def _onchange_apply_all_date_from(self):
        # Áp dụng từ ngày cho tất cả các dòng chi tiết
        if self.x_apply_all_date_from and self.x_registration_type == 'day':
            for line in self.x_line_ids:
                line.x_date_from = self.x_apply_all_date_from

    @api.onchange('x_apply_all_date_to')
    def _onchange_apply_all_date_to(self):
        # Áp dụng đến ngày cho tất cả các dòng chi tiết
        if self.x_apply_all_date_to and self.x_registration_type == 'day':
            for line in self.x_line_ids:
                line.x_date_to = self.x_apply_all_date_to

    @api.onchange('x_registration_type')
    def _onchange_registration_type(self):
        # Khi đổi loại đăng ký: xóa giá trị cũ ở các dòng chi tiết và điều kiện header
        # Ngày bắt buộc dùng ca cố định; tuần/tháng giữ nguyên chế độ phân ca đã chọn
        if self.x_registration_type == 'day':
            self.x_assignment_mode = 'static'
        self.x_fixed_shift_id = False
        self.x_rotation_id = False
        self.x_apply_all_week_ids = [(5, 0, 0)]
        self.x_apply_all_month_ids = [(5, 0, 0)]
        self.x_apply_all_date_from = False
        self.x_apply_all_date_to = False
        for line in self.x_line_ids:
            line.x_week_id = False
            line.x_month = False
            line.x_date_from = False
            line.x_date_to = False

    @api.constrains('x_registration_type', 'x_assignment_mode', 'x_fixed_shift_id', 'x_rotation_id')
    def _check_assignment(self):
        # Kiểm tra cấu hình phân ca hợp lệ theo chế độ và loại đăng ký
        for rec in self:
            if rec.x_registration_type == 'day' and rec.x_assignment_mode != 'static':
                raise ValidationError(_('Day registration must use Fixed Shift mode.'))
            if rec.x_assignment_mode == 'static' and not rec.x_fixed_shift_id:
                raise ValidationError(_('Fixed Shift is required in Fixed Shift mode.'))
            if rec.x_assignment_mode == 'rotation' and not rec.x_rotation_id:
                raise ValidationError(_('Rotation is required in Rotation mode.'))

    def action_confirm(self):
        # Xác nhận đăng ký; tạo lịch ca thủ công tương ứng theo loại đăng ký
        self.write({'x_state': 'confirmed'})
        for rec in self:
            if rec.x_registration_type == 'day':
                rec._create_manual_slots(rec)
            elif rec.x_registration_type == 'week':
                rec._create_week_slots(rec)
            elif rec.x_registration_type == 'month':
                rec._create_month_slots(rec)

    def _upsert_slot(self, employee_id, day, shift_id):
        # Tạo hoặc cập nhật slot ca cho nhân viên vào ngày chỉ định
        Slot = self.env['ps.work.shift.slot']
        existing = Slot.search([
            ('x_employee_id', '=', employee_id),
            ('x_date', '=', day),
        ], limit=1)
        if existing:
            existing.write({'x_shift_id': shift_id, 'x_source': 'manual'})
        else:
            Slot.create({
                'x_employee_id': employee_id,
                'x_date': day,
                'x_shift_id': shift_id,
                'x_source': 'manual',
            })

    def _create_manual_slots(self, rec, cutoff_date=None):
        # Tạo slot ca cố định cho từng ngày trong khoảng ngày của loại đăng ký Ngày
        fixed_shift = rec.x_fixed_shift_id
        for line in rec.x_line_ids:
            if not line.x_employee_id or not fixed_shift or not line.x_date_from or not line.x_date_to:
                continue
            day = line.x_date_from
            end = min(line.x_date_to, cutoff_date) if cutoff_date else line.x_date_to
            while day <= end:
                self._upsert_slot(line.x_employee_id.id, day, fixed_shift.id)
                day += timedelta(days=1)

    def _create_week_slots(self, rec, cutoff_date=None):
        # Tao slot ca cho tung ngay trong tuan da chon (ca co dinh hoac xoay ca)
        fixed_shift = rec.x_fixed_shift_id if rec.x_assignment_mode == 'static' else False
        rotation = rec.x_rotation_id if rec.x_assignment_mode == 'rotation' else False
        if not fixed_shift and not rotation:
            return
        for line in rec.x_line_ids:
            if not line.x_employee_id or not line.x_week_id:
                continue
            day = line.x_week_id.x_date_from
            end_day = line.x_week_id.x_date_to
            if cutoff_date:
                end_day = min(end_day, cutoff_date)
            while day <= end_day:
                shift = False
                if fixed_shift:
                    shift = fixed_shift
                elif rotation and day >= rotation.x_reference_date:
                    shift = rotation._get_shift_for_date(day)
                if not shift:
                    day += timedelta(days=1)
                    continue
                self._upsert_slot(line.x_employee_id.id, day, shift.id)
                day += timedelta(days=1)

    def _create_month_slots(self, rec, cutoff_date=None):
        # Tao slot ca cho tung ngay trong thang da chon (ca co dinh hoac xoay ca)
        fixed_shift = rec.x_fixed_shift_id if rec.x_assignment_mode == 'static' else False
        rotation = rec.x_rotation_id if rec.x_assignment_mode == 'rotation' else False
        if not fixed_shift and not rotation:
            return
        for line in rec.x_line_ids:
            if not line.x_employee_id or not line.x_month:
                continue
            month = int(line.x_month.x_value)
            if month < 1 or month > 12:
                continue
            start_date = fields.Date.from_string(f'{rec.x_year}-{month:02d}-01')
            next_month = start_date + relativedelta(months=1)
            end_date = next_month - timedelta(days=1)
            if cutoff_date:
                end_date = min(end_date, cutoff_date)
            day = start_date
            while day <= end_date:
                shift = False
                if fixed_shift:
                    shift = fixed_shift
                elif rotation and day >= rotation.x_reference_date:
                    shift = rotation._get_shift_for_date(day)
                if not shift:
                    day += timedelta(days=1)
                    continue
                self._upsert_slot(line.x_employee_id.id, day, shift.id)
                day += timedelta(days=1)

    def action_draft(self):
        # Chuyen ban ghi ve trang thai ban nhap
        self.write({'x_state': 'draft'})

    @api.model
    def _cron_generate_slots_from_registration(self, days_ahead=0):
        # Cron sinh slot cho cac dang ky da xac nhan (tuan/thang/ngay)
        registrations = self.search([('x_state', '=', 'confirmed')])
        cutoff_date = fields.Date.today() + timedelta(days=days_ahead) if days_ahead > 0 else None
        for rec in registrations:
            if rec.x_registration_type == 'day':
                rec._create_manual_slots(rec, cutoff_date=cutoff_date)
            elif rec.x_registration_type == 'week':
                rec._create_week_slots(rec, cutoff_date=cutoff_date)
            elif rec.x_registration_type == 'month':
                rec._create_month_slots(rec, cutoff_date=cutoff_date)
        return True

    @api.constrains('x_line_ids')
    def _check_line_required_fields(self):
        # Kiểm tra cac truong bat buoc theo loai dang ky (tuan/thang/ngay) tren tung dong chi tiet
        # Ca/xoay ca lay tu header Phan ca, khong con gan ca tren dong
        for rec in self:
            for line in rec.x_line_ids:
                if rec.x_registration_type == 'week' and not line.x_week_id:
                    raise ValidationError(_('Applied week is required for week registration on line of employee %s.') % line.x_employee_id.name)
                if rec.x_registration_type == 'month' and not line.x_month:
                    raise ValidationError(_('Applied month is required for month registration on line of employee %s.') % line.x_employee_id.name)
                if rec.x_registration_type == 'day':
                    if not line.x_date_from or not line.x_date_to:
                        raise ValidationError(_('Date range is required for day registration on line of employee %s.') % line.x_employee_id.name)

    @api.constrains('x_line_ids')
    def _check_overlap(self):
        # Kiem tra trung lap giua cac dong trong cung ban ghi va voi cac ban ghi da xac nhan
        # Ca/xoay ca lay tu header Phan ca nen kiem tra overlap dung rec.x_fixed_shift_id / rec.x_rotation_id
        for rec in self:
            lines = rec.x_line_ids
            if rec.x_registration_type == 'week':
                # Lay ten ca/xoay ca header de hien thi loi
                shift_name = (
                    rec.x_fixed_shift_id.x_shift_name
                    if rec.x_assignment_mode == 'static' and rec.x_fixed_shift_id
                    else rec.x_rotation_id.x_name if rec.x_rotation_id else ''
                )
                seen = set()
                for line in lines:
                    if not line.x_employee_id or not line.x_week_id:
                        continue
                    # Trung lap: cung nhan vien, cung tuan, cung nam
                    key = (line.x_employee_id.id, line.x_week_id.id)
                    if key in seen:
                        raise ValidationError(
                            _('Employee %(employee)s has duplicate week %(week)s registrations for shift %(shift)s.')
                            % {
                                'employee': line.x_employee_id.name,
                                'week': line.x_week_id.x_name,
                                'shift': shift_name,
                            }
                        )
                    seen.add(key)
                    domain = [
                        ('id', 'not in', lines.ids),
                        ('x_employee_id', '=', line.x_employee_id.id),
                        ('x_registration_id.x_registration_type', '=', 'week'),
                        ('x_registration_id.x_state', '=', 'confirmed'),
                        ('x_week_id', '=', line.x_week_id.id),
                        ('x_registration_id.x_year', '=', rec.x_year),
                    ]
                    if self.env['ps.work.schedule.registration.line'].search_count(domain, limit=1):
                        raise ValidationError(
                            _('Employee %(employee)s already has a confirmed registration for shift %(shift)s in %(week)s of year %(year)s.')
                            % {
                                'employee': line.x_employee_id.name,
                                'shift': shift_name,
                                'week': line.x_week_id.x_name,
                                'year': rec.x_year,
                            }
                        )
            elif rec.x_registration_type == 'month':
                shift_name = (
                    rec.x_fixed_shift_id.x_shift_name
                    if rec.x_assignment_mode == 'static' and rec.x_fixed_shift_id
                    else rec.x_rotation_id.x_name if rec.x_rotation_id else ''
                )
                seen = set()
                for line in lines:
                    if not line.x_employee_id or not line.x_month:
                        continue
                    # Trung lap: cung nhan vien, cung thang, cung nam
                    key = (line.x_employee_id.id, line.x_month.id)
                    if key in seen:
                        raise ValidationError(
                            _('Employee %(employee)s has duplicate month %(month)s registrations for shift %(shift)s.')
                            % {
                                'employee': line.x_employee_id.name,
                                'month': line.x_month.x_name,
                                'shift': shift_name,
                            }
                        )
                    seen.add(key)
                    domain = [
                        ('id', 'not in', lines.ids),
                        ('x_employee_id', '=', line.x_employee_id.id),
                        ('x_registration_id.x_registration_type', '=', 'month'),
                        ('x_registration_id.x_state', '=', 'confirmed'),
                        ('x_month', '=', line.x_month.id),
                        ('x_registration_id.x_year', '=', rec.x_year),
                    ]
                    if self.env['ps.work.schedule.registration.line'].search_count(domain, limit=1):
                        raise ValidationError(
                            _('Employee %(employee)s already has a confirmed registration for shift %(shift)s in %(month)s of year %(year)s.')
                            % {
                                'employee': line.x_employee_id.name,
                                'shift': shift_name,
                                'month': line.x_month.x_name,
                                'year': rec.x_year,
                            }
                        )
            else:
                fixed_shift = rec.x_fixed_shift_id
                if not fixed_shift:
                    continue
                intervals = []
                for line in lines:
                    if not line.x_employee_id or not line.x_date_from or not line.x_date_to:
                        continue
                    for other_employee_id, other_shift_id, other_from, other_to in intervals:
                        if (other_employee_id == line.x_employee_id.id and
                                other_shift_id == fixed_shift.id and
                                other_from <= line.x_date_to and
                                other_to >= line.x_date_from):
                            raise ValidationError(
                                _('Employee %(employee)s has duplicate day registrations for shift %(shift)s in the same period.')
                                % {
                                    'employee': line.x_employee_id.name,
                                    'shift': fixed_shift.x_shift_name,
                                }
                            )
                    intervals.append((line.x_employee_id.id, fixed_shift.id, line.x_date_from, line.x_date_to))
                    domain = [
                        ('id', 'not in', lines.ids),
                        ('x_employee_id', '=', line.x_employee_id.id),
                        ('x_registration_id.x_registration_type', '=', 'day'),
                        ('x_registration_id.x_state', '=', 'confirmed'),
                        ('x_registration_id.x_fixed_shift_id', '=', fixed_shift.id),
                        ('x_date_from', '<=', line.x_date_to),
                        ('x_date_to', '>=', line.x_date_from),
                    ]
                    if self.env['ps.work.schedule.registration.line'].search_count(domain, limit=1):
                        raise ValidationError(
                            _('Employee %(employee)s already has an overlapping confirmed day registration for shift %(shift)s.')
                            % {
                                'employee': line.x_employee_id.name,
                                'shift': fixed_shift.x_shift_name,
                            }
                        )


class PsWorkScheduleRegistrationLine(models.Model):
    _name = 'ps.work.schedule.registration.line'
    _description = 'Work Schedule Registration Line'
    _order = 'x_sequence, id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    x_registration_id = fields.Many2one(
        'ps.work.schedule.registration',
        string='Registration',
        required=True,
        ondelete='cascade',
    )
    x_registration_type = fields.Selection(
        related='x_registration_id.x_registration_type',
        string='Registration Type',
        store=True,
        readonly=True,
    )
    x_employee_ids = fields.Many2many(
        'hr.employee',
        string='Allowed Employees',
        related='x_registration_id.x_employee_ids',
        help='Danh sach nhan vien duoc loc theo cong ty va bo phan.',
    )
    x_sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    x_employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
    )
    x_department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='x_employee_id.department_id',
        store=True,
        readonly=True,
    )
    x_week_id = fields.Many2one(
        'ps.work.week',
        string='Applied Week',
        ondelete='restrict',
    )
    x_month = fields.Many2one(
        'ps.work.month',
        string='Applied Month',
        ondelete='restrict',
    )
    x_date_from = fields.Date(
        string='Date From',
    )
    x_date_to = fields.Date(
        string='Date To',
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

    @api.constrains('x_date_from', 'x_date_to')
    def _check_date_range(self):
        # Kiem tra den ngay phai sau hoac bang tu ngay
        for line in self:
            if line.x_date_from and line.x_date_to and line.x_date_to < line.x_date_from:
                raise ValidationError(_('Date To must be after Date From.'))
