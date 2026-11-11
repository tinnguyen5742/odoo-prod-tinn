from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PsPublicHoliday(models.Model):
    _name = 'ps.public.holiday'
    _description = 'Public Holiday'
    _rec_name = 'x_name'
    _order = 'x_year desc, x_holiday_date asc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    @api.model
    def _get_year_selection(self):
        cur = fields.Date.today().year
        return [(str(y), str(y)) for y in range(cur, cur - 3, -1)]

    x_year = fields.Selection(
        _get_year_selection,
        string='Year',
        required=True,
        default=lambda self: str(fields.Date.today().year),
        tracking=True,
    )
    x_holiday_date = fields.Date(
        string='Date',
        required=True,
        tracking=True,
    )
    x_name = fields.Char(
        string='Holiday Name',
        required=True,
        tracking=True,
    )
    x_lunar_formula = fields.Char(
        string='Lunar Formula',
        help='Lunar New Year formula, e.g. "Mùng 1 tháng Giêng"',
        tracking=True,
    )
    x_compensatory = fields.Boolean(
        string='Compensatory Leave',
        help='Tick if this holiday has a compensatory day off'
    )
    x_compensatory_date = fields.Date(
        string='Compensatory Date',
        help='Date of the compensatory day off',
        tracking=True,
    )
    x_notes = fields.Text(
        string='Notes',
        tracking=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        tracking=True,
    )

    _holiday_unique = models.Constraint(
        "UNIQUE(x_holiday_date, company_id)",
        "A holiday already exists on this date"
    )

    # Kiểm tra ngày nghỉ bù phải khác ngày lễ
    @api.constrains('x_holiday_date', 'x_compensatory_date')
    def _check_compensatory_date(self):
        for rec in self:
            if rec.x_compensatory and rec.x_compensatory_date == rec.x_holiday_date:
                raise ValidationError('Compensatory date must be different from the holiday date')
