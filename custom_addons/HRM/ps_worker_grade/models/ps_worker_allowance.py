# Danh mục phụ cấp công việc
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PsWorkerAllowance(models.Model):
    _name = 'ps.worker.allowance'
    _description = 'Worker Allowance'
    _rec_name = 'x_name'
    _order = 'x_sequence, x_code'

    x_code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        help='Unique allowance code, e.g. PC_NHA_O',
    )
    x_name = fields.Char(
        string='Allowance Name',
        required=True,
        help='Allowance name, e.g. Phụ cấp nhà ở',
    )
    x_amount = fields.Float(
        string='Amount',
        required=True,
        default=0.0,
        help='Allowance amount',
    )
    x_employee_type = fields.Selection(
        [
            ('official', 'Official'),
            ('probation', 'Probation'),
        ],
        string='Employee Type',
        required=True,
        default='official',
        help='Determine whether this allowance applies to an official or probationary employee.',
    )
    x_working_days = fields.Integer(
        string='Working Days',
        required=True,
        default=0,
        help='Number of working days in the period.',
    )
    x_probation_days = fields.Integer(
        string='Probation Days',
        help='Number of probation days (only required for probationary employees).',
    )
    x_sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    x_active = fields.Boolean(
        string='Active',
        default=True,
    )
    x_note = fields.Text(
        string='Notes',
    )

    @api.constrains('x_employee_type', 'x_probation_days', 'x_working_days')
    def _check_probation_days(self):
        for rec in self:
            if rec.x_employee_type == 'probation':
                if not rec.x_probation_days or rec.x_probation_days <= 0:
                    raise ValidationError(
                        _('Probation days must be greater than 0 for probationary employees.')
                    )
                if rec.x_probation_days > rec.x_working_days:
                    raise ValidationError(
                        _('Probation days cannot be greater than working days.')
                    )

    _allowance_code_unique = models.Constraint(
        "UNIQUE(x_code)",
        "Allowance code already exists!",
    )
