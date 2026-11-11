from odoo import api, fields, models


class PsWorkMonth(models.Model):
    _name = 'ps.work.month'
    _description = 'Work Month'
    _order = 'x_value'
    _rec_name = 'x_name'

    x_value = fields.Char(
        string='Value',
        required=True,
        help='Month number from 1 to 12.',
    )
    x_name = fields.Char(
        string='Name',
        compute='_compute_x_name',
        store=True,
    )
    x_active = fields.Boolean(
        string='Active',
        default=True,
    )

    _month_value_unique = models.Constraint(
        "UNIQUE(x_value)",
        "Month value must be unique.",
    )

    @api.depends('x_value')
    def _compute_x_name(self):
        month_labels = {
            '1': 'Tháng 1',
            '2': 'Tháng 2',
            '3': 'Tháng 3',
            '4': 'Tháng 4',
            '5': 'Tháng 5',
            '6': 'Tháng 6',
            '7': 'Tháng 7',
            '8': 'Tháng 8',
            '9': 'Tháng 9',
            '10': 'Tháng 10',
            '11': 'Tháng 11',
            '12': 'Tháng 12',
        }
        for rec in self:
            rec.x_name = month_labels.get(rec.x_value, 'Tháng ' + (rec.x_value or ''))
