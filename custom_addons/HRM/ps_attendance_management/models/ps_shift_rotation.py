from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PsShiftRotation(models.Model):
    _name = 'ps.shift.rotation'
    _description = 'Shift Rotation'
    _rec_name = 'x_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    x_name = fields.Char(
        string='Rotation Name',
        required=True,
        tracking=True,
    )
    x_active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
    )
    x_company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        tracking=True,
    )
    x_method = fields.Selection(
        [
            ('weekly', 'Weekly'),
            ('cycle', 'Cycle'),
        ],
        string='Method',
        default='weekly',
        help='Weekly: fixed per-weekday pattern. Cycle: continuous 28-day rotation (14+14).',
        tracking=True,
    )
    # --- Cycle mode fields (continuous 28-day rotation) ---
    x_reference_date = fields.Date(
        string='Reference Date',
        default=fields.Date.today,
        required=True,
        help='Date when shift 1 starts. Used as the anchor of the rotation cycle.',
        tracking=True,
    )
    x_shift_length = fields.Integer(
        string='Shift Length',
        default=14,
        help='Boundary day for the rotation block. E.g. 14 means shift 1 from day 1-14, shift 2 from day 15-28, and shift 1 again for days 29+.',
        tracking=True,
    )
    x_shift1_id = fields.Many2one(
        'ps.work.shift',
        string='Shift 1',
        domain="[('x_is_rotatable', '=', True)]",
        tracking=True,
    )
    x_shift2_id = fields.Many2one(
        'ps.work.shift',
        string='Shift 2',
        domain="[('x_is_rotatable', '=', True)]",
        tracking=True,
    )
    # --- Weekly mode fields ---
    x_line_ids = fields.One2many(
        'ps.shift.rotation.line',
        'x_rotation_id',
        string='Rotation Lines',
    )

    _rotation_name_unique = models.Constraint(
        "UNIQUE(x_name, x_company_id)",
        "Rotation name already exists",
    )

    def _get_shift_for_date(self, target_date):
        # Trả về ca áp dụng cho ngày chỉ định theo phương thức chu kỳ hoặc tuần
        self.ensure_one()
        if not self.x_reference_date:
            raise ValidationError('Reference date is required for rotation %s.' % self.x_name)
        if target_date < self.x_reference_date:
            raise ValidationError('Target date %s is before the rotation reference date %s.' % (target_date, self.x_reference_date))
        if self.x_method == 'cycle':
            return self._get_cycle_shift_for_date(target_date)
        return self._get_weekly_shift_for_date(target_date)

    def _get_cycle_shift_for_date(self, target_date):
        # Trả về ca theo mốc ngày trong tháng (VD: 1-14 ca1, 15-28 ca2, 29+ ca1)
        if not self.x_shift1_id or not self.x_shift2_id:
            raise ValidationError('Shift 1 and Shift 2 are required for cycle rotation.')
        boundary = self.x_shift_length or 14
        day = target_date.day
        if day <= boundary:
            return self.x_shift1_id
        if day <= boundary * 2:
            return self.x_shift2_id
        return self.x_shift1_id

    def _get_weekly_shift_for_date(self, target_date):
        # Trả về ca theo thứ trong tuần từ dòng vòng lặp tuần (T2-CN)
        lines = self.x_line_ids.sorted('x_week')
        if not lines:
            return False
        week_number = target_date.isocalendar().week
        max_week = lines[-1].x_week or 1
        rotation_week = ((week_number - 1) % max_week) + 1
        line = lines.filtered(lambda l: l.x_week == rotation_week)[:1] or lines[0]
        weekday_fields = ['x_t2_id', 'x_t3_id', 'x_t4_id', 'x_t5_id', 'x_t6_id', 'x_t7_id', 'x_cn_id']
        return line[weekday_fields[target_date.weekday()]]

    def action_regenerate_slots(self):
        # Tim cac dang ky da xac nhan dung xoay ca nay va tao lai slot
        Registration = self.env['ps.work.schedule.registration']
        registrations = Registration.search([
            ('x_state', '=', 'confirmed'),
            ('x_rotation_id', 'in', self.ids),
        ])
        registrations._cron_generate_slots_from_registration()

    @api.constrains('x_method', 'x_shift_length')
    def _check_cycle_config(self):
        # Kiểm tra cấu hình vòng lặp chu kỳ hợp lệ (ca 1, ca 2, ngày mốc, độ dài)
        for rec in self:
            if rec.x_method == 'cycle':
                if not rec.x_shift_length or rec.x_shift_length < 1:
                    raise ValidationError('Shift length must be at least 1.')
                if rec.x_shift1_id and rec.x_shift1_id == rec.x_shift2_id:
                    raise ValidationError('Shift 1 and Shift 2 must be different.')
                if rec.x_reference_date and (not rec.x_shift1_id or not rec.x_shift2_id):
                    raise ValidationError('Shift 1 and Shift 2 are required for a cycle rotation.')
                if not rec.x_reference_date:
                    raise ValidationError('Reference date is required for a cycle rotation.')


class PsShiftRotationLine(models.Model):
    _name = 'ps.shift.rotation.line'
    _description = 'Shift Rotation Line'
    _order = 'x_week, id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    x_rotation_id = fields.Many2one(
        'ps.shift.rotation',
        string='Rotation',
        required=True,
        ondelete='cascade',
    )
    x_week = fields.Integer(
        string='Week',
        default=1,
    )
    # Ca cho từng ngày trong tuần (T2 - CN)
    x_t2_id = fields.Many2one('ps.work.shift', string='T2')
    x_t3_id = fields.Many2one('ps.work.shift', string='T3')
    x_t4_id = fields.Many2one('ps.work.shift', string='T4')
    x_t5_id = fields.Many2one('ps.work.shift', string='T5')
    x_t6_id = fields.Many2one('ps.work.shift', string='T6')
    x_t7_id = fields.Many2one('ps.work.shift', string='T7')
    x_cn_id = fields.Many2one('ps.work.shift', string='CN')