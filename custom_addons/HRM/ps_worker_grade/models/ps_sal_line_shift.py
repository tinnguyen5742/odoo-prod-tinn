# Dynamic shift counts on salary line
from odoo import api, fields, models


class PsWorkerSalaryLineShift(models.Model):
    # Số ca làm việc động trên dòng lương
    _name = 'ps.worker.salary.line.shift'
    _description = 'Salary Line Shift'
    _order = 'x_shift_type_id, id'

    x_salary_line_id = fields.Many2one(
        'ps.worker.salary.line',
        string='Salary Line',
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
        help='Number of shifts of this type',
    )
    x_basic_amount = fields.Float(
        string='Basic Amount',
        compute='_compute_amounts',
        store=True,
    )
    x_kpi_amount = fields.Float(
        string='KPI Amount',
        compute='_compute_amounts',
        store=True,
    )
    x_total = fields.Float(
        string='Total',
        compute='_compute_amounts',
        store=True,
    )

    @api.depends(
        'x_count', 'x_shift_type_id',
        'x_salary_line_id.x_basic_salary', 'x_salary_line_id.x_kpi_amount',
        'x_salary_line_id.x_formula_id.x_kpi_divisor',
    )
    def _compute_amounts(self):
        # Tính tiền LCB/KPI/tổng cho từng ca làm việc
        for line in self:
            salary_line = line.x_salary_line_id
            shift_type = line.x_shift_type_id
            if not salary_line or not shift_type:
                line.x_basic_amount = 0.0
                line.x_kpi_amount = 0.0
                line.x_total = 0.0
                continue

            basic = salary_line.x_basic_salary or 0.0
            kpi = salary_line.x_kpi_amount or 0.0
            formula = salary_line.x_formula_id
            divisor = formula.x_kpi_divisor if formula else 11.0

            hourly_basic = basic / 26.0 / 8.0
            hourly_kpi = kpi / 26.0 / divisor if divisor else 0.0

            basic_amount = hourly_basic * shift_type.x_factor
            if shift_type.x_round:
                basic_amount = round(basic_amount, -2)
            kpi_amount = hourly_kpi * shift_type.x_kpi_hours

            line.x_basic_amount = basic_amount * line.x_count
            line.x_kpi_amount = kpi_amount * line.x_count
            line.x_total = line.x_basic_amount + line.x_kpi_amount
