from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PsShiftChange(models.Model):
    _name = 'ps.shift.change'
    _description = 'Shift Change'
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
        string='New Work Shift',
        tracking=True,
        help='New shift to apply.',
    )
    x_date_from = fields.Date(
        string='Date From',
        required=True,
    )
    x_date_to = fields.Date(
        string='Date To',
        required=True,
    )
    x_reason = fields.Char(
        string='Reason',
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
        default=lambda self: self.env.company,
    )
    x_line_ids = fields.One2many(
        'ps.shift.change.line',
        'x_change_id',
        string='Shift Change Lines',
    )
    
    @api.depends('x_registration_date', 'x_department_id', 'x_employee_id')
    def _compute_x_name(self):
        # Sinh tên phiếu: SC - Ngày - Bộ phận - Nhân viên
        for rec in self:
            parts = ['SC', str(rec.x_registration_date)]
            if rec.x_department_id:
                parts.append(rec.x_department_id.name)
            if rec.x_employee_id:
                parts.append(rec.x_employee_id.name)
            rec.x_name = ' - '.join(parts) or _('New Shift Change')

    @api.depends('x_company_id', 'x_department_id')
    def _compute_x_employee_ids(self):
        # Lọc nhân viên theo công ty và bộ phận
        for rec in self:
            domain = [('company_id', '=', rec.x_company_id.id)]
            if rec.x_department_id:
                domain.append(('department_id', '=', rec.x_department_id.id))
            rec.x_employee_ids = self.env['hr.employee'].sudo().search(domain)

    @api.onchange('x_company_id')
    def _onchange_company_id(self):
        # Đổi công ty: xóa bộ phận, nhân viên cũ
        self.x_department_id = False
        self.x_employee_id = False

    def _load_employee_lines(self):
        # Nạp dòng chi tiết từ lịch phân ca theo bộ phận/nhân viên/ngày/ca
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
            slot_domain.append(('x_shift_id', '!=', self.x_shift_id.id))

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
                'x_reason': self.x_reason,
            }))
        self.x_line_ids = commands
        return len(slots)

    def action_load_employees(self):
        # Nút load nhân viên từ lịch phân ca
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
            },
        }

    def action_confirm(self):
        # Xác nhận đổi ca: kiểm tra dữ liệu, trùng lặp và cập nhật lịch phân ca
        for rec in self:
            if not rec.x_line_ids:
                raise ValidationError(_('No employees have been assigned shift change.'))
            if not rec.x_shift_id:
                raise ValidationError(_('Please select the new work shift.'))

            # Kiểm tra trùng lặp với phiếu đổi ca đã confirmed
            for line in rec.x_line_ids:
                if not line.x_employee_id or not line.x_date_from:
                    continue
                domain = [
                    ('x_change_id', '!=', rec.id),
                    ('x_employee_id', '=', line.x_employee_id.id),
                    ('x_date_from', '=', line.x_date_from),
                    ('x_change_id.x_state', '=', 'confirmed'),
                ]
                if self.env['ps.shift.change.line'].search_count(domain, limit=1):
                    raise ValidationError(
                        _(
                            'Employee %(employee)s already has a confirmed shift change on %(date)s.',
                            employee=line.x_employee_id.name,
                            date=line.x_date_from,
                        )
                    )

        self.write({'x_state': 'confirmed'})
        self.env.flush_all()

        # Cập nhật lịch phân ca theo ca mới
        Slot = self.env['ps.work.shift.slot']
        for rec in self:
            for line in rec.x_line_ids:
                if not line.x_employee_id or not line.x_date_from:
                    continue
                slot = Slot.sudo().search([
                    ('x_employee_id', '=', line.x_employee_id.id),
                    ('x_date', '=', line.x_date_from),
                ], limit=1)
                if slot:
                    slot.write({
                        'x_shift_id': rec.x_shift_id.id,
                        'x_source': 'manual',
                        'x_old_shift_id': slot.x_shift_id.id,
                        'x_change_reason': line.x_reason or rec.x_reason,
                        'x_change_date': fields.Date.today(),
                        'x_shift_change_id': rec.id,
                    })

    def action_draft(self):
        # Chuyển về Draft
        self.ensure_one()
        self.write({'x_state': 'draft'})

        # Xóa dữ liệu tracking đổi ca trên lịch phân ca của phiếu này
        slots = self.env['ps.work.shift.slot'].sudo().search([
            ('x_shift_change_id', '=', self.id),
        ])
        if slots:
            slots.write({
                'x_old_shift_id': False,
                'x_change_reason': False,
                'x_change_date': False,
                'x_shift_change_id': False,
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('The shift change has been moved back to draft.'),
                'type': 'warning',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'ps.shift.change',
                    'res_id': self.id,
                    'view_mode': 'form',
                    'target': 'current',
                    'views': [(False, 'form')],
                },
            }
        }

    def unlink(self):
        # Xóa dữ liệu tracking đổi ca trên lịch phân ca trước khi xóa phiếu
        for rec in self:
            slots = self.env['ps.work.shift.slot'].sudo().search([
                ('x_shift_change_id', '=', rec.id),
            ])
            if slots:
                slots.write({
                    'x_old_shift_id': False,
                    'x_change_reason': False,
                    'x_change_date': False,
                    'x_shift_change_id': False,
                })
        return super(PsShiftChange, self).unlink()

    @api.model_create_multi
    def create(self, vals_list):
        # Tạo mới: nạp dòng chi tiết sau khi lưu nếu ở Draft
        records = super(PsShiftChange, self).create(vals_list)
        for rec in records:
            if rec.x_state == 'draft':
                rec._load_employee_lines()
        return records

    def write(self, vals):
        # Lưu phiếu: nạp lại dòng chi tiết nếu ở Draft và thay đổi điều kiện lọc
        if not vals:
            return super(PsShiftChange, self).write(vals)
        for rec in self:
            if rec.x_state == 'confirmed':
                if set(vals.keys()) != {'x_state'} or vals.get('x_state') != 'draft':
                    raise ValidationError(
                        _('A confirmed shift change cannot be edited. Please set it back to draft first.')
                    )
        result = super(PsShiftChange, self).write(vals)
        for rec in self:
            if rec.x_state == 'draft' and any(k in vals for k in (
                'x_department_id', 'x_employee_id', 'x_shift_id', 'x_date_from', 'x_date_to'
            )):
                rec._load_employee_lines()
        return result

    @api.constrains('x_date_from', 'x_date_to')
    def _check_date_range(self):
        # Kiểm tra đến ngày >= từ ngày
        for rec in self:
            if rec.x_date_from and rec.x_date_to and rec.x_date_to < rec.x_date_from:
                raise ValidationError(_('Date To must be after Date From.'))


class PsShiftChangeLine(models.Model):
    _name = 'ps.shift.change.line'
    _description = 'Shift Change Line'
    _order = 'x_date_from, id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # region Line fields
    x_change_id = fields.Many2one(
        'ps.shift.change',
        string='Shift Change',
        required=True,
        ondelete='cascade',
    )
    x_employee_ids = fields.Many2many(
        'hr.employee',
        string='Allowed Employees',
        related='x_change_id.x_employee_ids',
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
        string='Current Work Shift',
        help='Current shift from shift schedule.',
    )
    x_new_shift_id = fields.Many2one(
        'ps.work.shift',
        string='New Work Shift',
        related='x_change_id.x_shift_id',
        store=True,
        readonly=True,
        help='New shift to apply from the shift change header.',
    )
    x_reason = fields.Char(
        string='Reason',
    )
    x_change_status = fields.Selection(
        [
            ('changed', 'Shift Change'),
        ],
        string='Shift Change',
        compute='_compute_x_change_status',
    )
    x_state = fields.Selection(
        related='x_change_id.x_state',
        string='Status',
        store=True,
        readonly=True,
    )
    x_company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='x_change_id.x_company_id',
        store=True,
        readonly=True,
    )
    # endregion

    @api.depends('x_employee_id')
    def _compute_x_employee_code(self):
        # Lấy mã nhân viên
        for line in self:
            emp = line.x_employee_id
            code = False
            if emp:
                code = getattr(emp, 'x_employee_code', False) or emp.barcode
            line.x_employee_code = code or ''

    @api.depends('x_shift_id', 'x_change_id.x_shift_id')
    def _compute_x_change_status(self):
        # Hiển thị badge Đổi ca khi ca chi tiết khác ca header
        for line in self:
            header_shift = line.x_change_id.x_shift_id
            if header_shift and line.x_shift_id and line.x_shift_id != header_shift:
                line.x_change_status = 'changed'
            else:
                line.x_change_status = False

    @api.constrains('x_date_from', 'x_date_to')
    def _check_date_range(self):
        # Kiểm tra đến ngày >= từ ngày
        for line in self:
            if line.x_date_from and line.x_date_to and line.x_date_to < line.x_date_from:
                raise ValidationError(_('Date To must be after Date From.'))

    @api.model_create_multi
    def create(self, vals_list):
        # Không cho thêm dòng khi phiếu đã confirmed
        for vals in vals_list:
            change = self.env['ps.shift.change'].browse(vals.get('x_change_id'))
            if change.x_state == 'confirmed':
                raise ValidationError(_('Cannot add lines to a confirmed shift change.'))
        return super(PsShiftChangeLine, self).create(vals_list)

    def write(self, vals):
        # Không cho sửa dòng khi phiếu đã confirmed
        if not vals:
            return super(PsShiftChangeLine, self).write(vals)
        for line in self:
            if line.x_change_id.x_state == 'confirmed':
                raise ValidationError(_('Cannot edit lines of a confirmed shift change.'))
        return super(PsShiftChangeLine, self).write(vals)
