# Danh mục bậc thợ
from odoo import fields, models

class PsWorkerGrade(models.Model):
    _name = 'ps.worker.grade'
    _description = 'Worker Grade'
    _rec_name = 'x_name'
    _order = 'x_profession_id, x_sequence, x_name'

    x_code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        help='Grade code, e.g. B1',
    )
    x_name = fields.Char(
        string='Grade Name',
        required=True,
        help='Grade name, e.g. Bậc 1',
    )
    x_profession_id = fields.Many2one(
        'ps.worker.profession',
        string='Profession',
        required=True,
        ondelete='cascade',
        help='Profession this grade belongs to',
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

    _grade_profession_code_unique = models.Constraint(
        "UNIQUE(x_profession_id, x_code)",
        "Grade code already exists for this profession!",
    )
    _grade_profession_name_unique = models.Constraint(
        "UNIQUE(x_profession_id, x_name)",
        "Grade name already exists for this profession!",
    )
