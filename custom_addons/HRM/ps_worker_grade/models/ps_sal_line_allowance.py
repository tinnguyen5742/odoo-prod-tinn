# Dynamic allowances on salary line
from odoo import api, fields, models


class PsWorkerSalaryLineAllowance(models.Model):
    # Phụ cấp động trên dòng lương
    _name = 'ps.worker.salary.line.allowance'
    _description = 'Salary Line Allowance'
    _order = 'x_sequence, id'

    x_salary_line_id = fields.Many2one(
        'ps.worker.salary.line',
        string='Salary Line',
        required=True,
        ondelete='cascade',
    )
    x_allowance_id = fields.Many2one(
        'ps.worker.allowance',
        string='Allowance',
        required=True,
    )
    x_amount = fields.Float(
        string='Amount',
        compute='_compute_amount',
        store=True,
    )
    x_sequence = fields.Integer(
        string='Sequence',
        related='x_allowance_id.x_sequence',
        store=True,
    )
    x_note = fields.Char(
        string='Notes',
    )

    @api.depends(
        'x_allowance_id', 'x_allowance_id.x_amount', 'x_allowance_id.x_working_days',
        'x_allowance_id.x_min_working_days', 'x_salary_line_id.x_working_days',
    )
    def _compute_amount(self):
        # Tính phụ cấp theo số ngày công và điều kiện tối thiểu
        for line in self:
            allowance = line.x_allowance_id
            salary_line = line.x_salary_line_id
            if not allowance or not salary_line:
                line.x_amount = 0.0
                continue

            working_days = salary_line.x_working_days or 0
            min_days = allowance.x_min_working_days or 0
            if working_days < min_days:
                line.x_amount = 0.0
                continue

            base_days = allowance.x_working_days or 26
            if base_days <= 0:
                line.x_amount = 0.0
                continue

            line.x_amount = allowance.x_amount / base_days * working_days

    @api.onchange('x_allowance_id')
    def _onchange_allowance(self):
        # Tự động điền ghi chú từ danh mục phụ cấp
        for line in self:
            if line.x_allowance_id and not line.x_note:
                line.x_note = line.x_allowance_id.x_note or ''
