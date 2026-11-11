# Worker grade catalog
from odoo import fields, models


class PsWorkerGrade(models.Model):
    # Danh mục bậc thợ
    _name = 'ps.worker.grade'
    _description = 'Worker Grade'
    _rec_name = 'x_name'
    _order = 'x_profession_id, x_job_id, x_level, x_sequence, x_name'

    def name_get(self):
        # Hiển thị tên bậc thợ kèm ngành nghề/vị trí
        result = []
        for grade in self:
            profession = grade.x_profession_id.x_name or ''
            job = grade.x_job_id.name or ''
            name = f'{grade.x_code} - {grade.x_name}'
            parts = [p for p in [profession, job] if p]
            if parts:
                name = f'{name} ({", ".join(parts)})'
            result.append((grade.id, name))
        return result

    x_code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        help='Grade code, e.g. B1',
    )
    x_name = fields.Char(
        string='Grade Name',
        required=True,
        help='Grade name, e.g. Grade 1',
    )
    x_profession_id = fields.Many2one(
        'ps.worker.profession',
        string='Profession',
        required=True,
        ondelete='cascade',
        help='Profession this grade belongs to',
    )
    x_job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
        help='Job position from HR module',
    )
    x_employment_type = fields.Selection(
        [
            ('probation', 'Probation'),
            ('official', 'Official'),
        ],
        string='Employment Type',
        default='official',
        required=True,
        help='Probation or official employment type',
    )
    x_level = fields.Float(
        string='Level',
        default=0.0,
        help='Grade level, e.g. 0, 1, 1.5, 2',
    )
    x_probation_days = fields.Integer(
        string='Probation Days',
        default=0,
        help='Probation working days, e.g. 6 or 14',
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
    x_shift_ids = fields.One2many(
        'ps.worker.grade.shift',
        'x_grade_id',
        string='Default Shifts',
        help='Default shift configuration for this grade',
    )

    _grade_profession_job_code_unique = models.Constraint(
        "UNIQUE(x_profession_id, x_job_id, x_code)",
        "Grade code already exists for this profession and job!",
    )
    _grade_profession_job_name_unique = models.Constraint(
        "UNIQUE(x_profession_id, x_job_id, x_name)",
        "Grade name already exists for this profession and job!",
    )
