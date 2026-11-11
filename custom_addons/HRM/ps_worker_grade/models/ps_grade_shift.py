# Default shift configuration per grade
from odoo import fields, models


class PsWorkerGradeShift(models.Model):
    # Cấu hình ca làm việc mặc định cho từng bậc thợ
    _name = 'ps.worker.grade.shift'
    _description = 'Grade Default Shift'
    _order = 'x_sequence, id'

    x_grade_id = fields.Many2one(
        'ps.worker.grade',
        string='Grade',
        required=True,
        ondelete='cascade',
    )
    x_shift_type_id = fields.Many2one(
        'ps.worker.shift.type',
        string='Shift Type',
        required=True,
    )
    x_count = fields.Integer(
        string='Shift Count',
        default=0,
        required=True,
        help='Number of shifts of this type for the grade',
    )
    x_sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    _grade_shift_type_unique = models.Constraint(
        "UNIQUE(x_grade_id, x_shift_type_id)",
        "Shift type already configured for this grade!",
    )
