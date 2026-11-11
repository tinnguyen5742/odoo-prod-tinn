# Salary formula by profession/job position
from odoo import fields, models


class PsWorkerSalaryFormula(models.Model):
    # Công thức lương theo nghề/vị trí
    _name = 'ps.worker.salary.formula'
    _description = 'Salary Formula'
    _rec_name = 'x_name'
    _order = 'x_profession_id, x_job_id, x_name'

    x_code = fields.Char(
        string='Code',
        required=True,
        copy=False,
    )
    x_name = fields.Char(
        string='Name',
        required=True,
    )
    x_profession_id = fields.Many2one(
        'ps.worker.profession',
        string='Profession',
        required=True,
        ondelete='cascade',
    )
    x_job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
        help='Apply to specific job. Leave empty to apply for whole profession.',
    )
    x_active = fields.Boolean(
        string='Active',
        default=True,
    )
    x_kpi_divisor = fields.Float(
        string='KPI Divisor',
        default=11.0,
        required=True,
        help='KPI per hour = KPI / 26 / divisor',
    )
    x_shift_ids = fields.One2many(
        'ps.worker.salary.formula.shift',
        'x_formula_id',
        string='Default Shift Counts',
        help='Default number of shifts for each shift type in a 26-day period',
    )
    x_probation_shift_type_id = fields.Many2one(
        'ps.worker.shift.type',
        string='Probation Shift Type',
        help='Default shift type used for probation grades when grade has no shift config',
    )
    x_round_night = fields.Boolean(
        string='Round Night Shift',
        default=True,
        help='Round night shift amount to nearest 100',
    )
    x_allowance_ids = fields.Many2many(
        'ps.worker.allowance',
        'ps_worker_salary_formula_allowance_rel',
        'formula_id',
        'allowance_id',
        string='Default Allowances',
        help='Default allowances applied to salary lines using this formula',
    )
    x_note = fields.Text(
        string='Notes',
    )

    _formula_code_unique = models.Constraint(
        "UNIQUE(x_code)",
        "Formula code already exists!",
    )

    def _get_formula(self, profession, job=None):
        # Tìm công thức phù hợp theo nghề/vị trí
        domain = [
            ('x_profession_id', '=', profession.id),
            ('x_active', '=', True),
        ]
        if job:
            specific = self.search(domain + [('x_job_id', '=', job.id)], limit=1)
            if specific:
                return specific
        return self.search(domain + [('x_job_id', '=', False)], limit=1)

    def get_default_shift_counts(self):
        # Trả về dict {shift_type_id: count}
        self.ensure_one()
        return {shift.x_shift_type_id.id: shift.x_count for shift in self.x_shift_ids}


class PsWorkerSalaryFormulaShift(models.Model):
    # Số ca mặc định trong công thức lương
    _name = 'ps.worker.salary.formula.shift'
    _description = 'Salary Formula Default Shift Count'
    _order = 'x_shift_type_id, id'

    x_formula_id = fields.Many2one(
        'ps.worker.salary.formula',
        string='Formula',
        required=True,
        ondelete='cascade',
    )
    x_shift_type_id = fields.Many2one(
        'ps.worker.shift.type',
        string='Shift Type',
        required=True,
    )
    x_count = fields.Integer(
        string='Default Count',
        default=0,
        required=True,
        help='Default number of shifts of this type',
    )

    _formula_shift_type_unique = models.Constraint(
        "UNIQUE(x_formula_id, x_shift_type_id)",
        "Shift type already configured in this formula!",
    )
