# Worker shift type catalog
from odoo import fields, models


class PsWorkerShiftType(models.Model):
    # Danh mục loại ca làm việc
    _name = 'ps.worker.shift.type'
    _description = 'Worker Shift Type'
    _rec_name = 'x_name'
    _order = 'x_sequence, id'

    x_code = fields.Char(
        string='Code',
        required=True,
        copy=False,
    )
    x_name = fields.Char(
        string='Shift Type Name',
        required=True,
    )
    x_factor = fields.Float(
        string='Salary Factor',
        default=8.0,
        required=True,
        help='Total factor used to compute basic amount per shift, e.g. 8 * 100% = 8.0',
    )
    x_kpi_hours = fields.Float(
        string='KPI Hours',
        default=8.0,
        required=True,
        help='Number of KPI hours for this shift type',
    )
    x_is_sunday = fields.Boolean(
        string='Sunday Shift',
        default=False,
        help='Check if this shift type is for Sunday',
    )
    x_round = fields.Boolean(
        string='Round Amount',
        default=False,
        help='Round basic amount to nearest 100',
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

    _shift_type_code_unique = models.Constraint(
        "UNIQUE(x_code)",
        "Shift type code already exists!",
    )
