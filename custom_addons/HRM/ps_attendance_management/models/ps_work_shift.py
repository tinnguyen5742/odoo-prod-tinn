from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PsWorkShift(models.Model):
    _name = 'ps.work.shift'
    _description = 'Work Shift'
    _rec_name = 'x_shift_name'
    _order = 'x_start_time asc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    x_shift_code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        help='Unique shift code, e.g. CA1',tracking=True,
    )
    x_shift_name = fields.Char(
        string='Name Shift',
        required=True,
        help='Shift name, e.g. Morning',tracking=True,
    )
    x_start_time = fields.Float(
        string='Start',
        required=True,
        help='Shift start time',tracking=True,
    )
    x_end_time = fields.Float(
        string='End',
        required=True,
        help='Shift end time',tracking=True,
    )
    x_has_lunch_break = fields.Boolean(
        string='Has Lunch Break',
        default=True,
        tracking=True,
    )
    x_lunch_break_start = fields.Float(
        string='Start Lunch',
        help='Leave empty if no lunch break',
        tracking=True,
    )
    x_lunch_break_end = fields.Float(
        string='Lunch End',
        help='Leave empty if no lunch break',
        tracking=True,
    )
    x_working_hours = fields.Float(
        string='Hours',
        compute='_compute_x_working_hours',
        store=True,
        help='Working hours (excl. lunch break)',
        tracking=True,
    )
    x_notes = fields.Text(
        string='Notes',
        tracking=True,
    )
    x_category = fields.Selection(
        [
            ('office', 'Office'),
            ('production', 'Production'),
            ('parttime', 'Part-time'),
        ],
        string='Category',
        default='production',
        help='Classification of the shift (office, production, part-time).',
        tracking=True,
    )
    x_is_rotatable = fields.Boolean(
        string='Rotatable',
        default=True,
        help='Only rotatable shifts can be used in a cycle rotation.',
        tracking=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,tracking=True,
    )

    _shift_code_unique = models.Constraint("UNIQUE(x_shift_code, company_id)","Shift code already exists")

    # Xác định ca có qua đêm hay không
    #   - Nếu x_end_time <= x_start_time nghĩa là ca vượt qua nửa đêm
    #     (vd: 22:00 -> 06:00 sáng hôm sau) và cần cộng thêm 24h khi tính toán.
    #   - Ngược lại là ca bình thường trong ngày.
    def _is_overnight(self):
        self.ensure_one()
        return self.x_end_time <= self.x_start_time

    # Đưa 1 mốc giờ để so sánh đúng trong ca đêm
    #   - Với ca qua đêm, nếu mốc giờ < giờ bắt đầu ca thì đó là giờ của ngày hôm sau,
    #     cộng thêm 24h để đặt về sau giờ bắt đầu (vd: 00:30 -> 24:30).
    #   - Với ca thường không cần xử lý.
    def _linear_time(self, value):
        self.ensure_one()
        if self._is_overnight() and value < self.x_start_time:
            return value + 24.0
        return value

    # Kiểm tra khoảng thời gian tăng ca có giao với giờ làm việc của ca hay không
    def overtime_overlaps(self, time_from, time_to):
        self.ensure_one()
        if time_to <= time_from:
            return True
        if self.x_start_time < self.x_end_time:
            # Ca thường, ví dụ 07:30 -> 16:30
            return time_from < self.x_end_time and time_to > self.x_start_time
        # Ca qua đêm, ví dụ 22:00 -> 06:00
        if time_from > time_to:
            return True
        return time_to > self.x_start_time or time_from < self.x_end_time

    # Format giá trị float thành chuỗi HH:MM
    def _format_time(self, value):
        self.ensure_one()
        hours = int(value)
        minutes = int(round((value - hours) * 60))
        if minutes >= 60:
            hours += 1
            minutes -= 60
        return f'{hours:02d}:{minutes:02d}'

    # Tính số giờ làm việc thực tế (đã trừ thời gian nghỉ trưa)
    @api.depends('x_start_time', 'x_end_time', 'x_lunch_break_start',
                 'x_lunch_break_end', 'x_has_lunch_break')
    def _compute_x_working_hours(self):
        for rec in self:
            # Giờ kết thúc thực tế trên trục tuyến tính (cộng 24h nếu ca qua đêm)
            end = rec._linear_time(rec.x_end_time)
            total = end - rec.x_start_time

            lunch = 0.0
            # Chỉ trừ nghỉ trưa khi người dùng xác nhận có nghỉ trưa
            if rec.x_has_lunch_break:
                ls = rec._linear_time(rec.x_lunch_break_start)
                le = rec._linear_time(rec.x_lunch_break_end)
                if le > ls:
                    lunch = le - ls

            rec.x_working_hours = max(total - lunch, 0.0)

    # Kiểm tra hợp lệ giờ bắt đầu và kết thúc ca làm việc
    @api.constrains('x_start_time', 'x_end_time')
    def _check_shift_time(self):
        for rec in self:
            if rec.x_start_time < 0 or rec.x_start_time >= 24:
                raise ValidationError('Start must be 0:00 - 23:59')
            if rec.x_end_time < 0 or rec.x_end_time >= 24:
                raise ValidationError('End must be 0:00 - 23:59')

    # Kiểm tra thời gian nghỉ trưa phải nằm trong khoảng thời gian của ca
    #   - Chỉ kiểm tra khi x_has_lunch_break = True
    #   - Dùng trục tuyến tính để nghỉ trưa qua nửa đêm vẫn tính đúng.
    @api.constrains('x_lunch_break_start', 'x_lunch_break_end',
                    'x_start_time', 'x_end_time', 'x_has_lunch_break')
    def _check_lunch_break_time(self):
        for rec in self:
            # Không có nghỉ trưa -> bỏ qua, không cần kiểm tra giờ nghỉ
            if not rec.x_has_lunch_break:
                continue

            # Có tick nghỉ trưa nhưng chưa nhập giờ -> bỏ qua (tránh báo lỗi
            # "Lunch End must be after Lunch Start" khi cả 2 giờ còn rỗng = 0.0)
            if rec.x_lunch_break_start == 0.0 and rec.x_lunch_break_end == 0.0:
                continue

            # Đưa giờ nghỉ trưa về trục tuyến tính (xử lý ca qua đêm)
            ls = rec._linear_time(rec.x_lunch_break_start)
            le = rec._linear_time(rec.x_lunch_break_end)

            # Giờ kết thúc nghỉ trưa phải sau giờ bắt đầu nghỉ trưa
            if le <= ls:
                raise ValidationError('Lunch End must be after Lunch Start')

            # Khoảng nghỉ trưa phải nằm trong khoảng thời gian của ca
            if ls < rec.x_start_time or le > rec._linear_time(rec.x_end_time):
                raise ValidationError('Lunch break must be within the shift')

    # Chuẩn hóa mã ca trước khi lưu (bỏ khoảng trắng thừa, chuyển hoa "CA1" / "ca1")
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('x_shift_code'):
                vals['x_shift_code'] = vals['x_shift_code'].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('x_shift_code'):
            vals['x_shift_code'] = vals['x_shift_code'].strip().upper()
        return super().write(vals)

    # DB CHECK constraint chặn cứng giờ ngoài 0:00 - 23:59
    _check_start_time_range = models.Constraint(
        "CHECK(x_start_time >= 0 AND x_start_time < 24)",
        "Start time must be between 0:00 and 23:59",
    )
    _check_end_time_range = models.Constraint(
        "CHECK(x_end_time >= 0 AND x_end_time < 24)",
        "End time must be between 0:00 and 23:59",
    )