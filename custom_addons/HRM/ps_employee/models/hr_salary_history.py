from odoo import models, fields


class HrEmployeeSalaryHistory(models.Model):
    _name = 'ps.hr.employee.salary.history'
    _description = 'Salary History'
    _order = 'date_from desc'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade')
    contract_number = fields.Char(string='Số HĐLĐ')
    decision_number = fields.Char(string='Số QĐ/PL')
    decision_type = fields.Many2one(
        'hr.contract.type',
        string='Loại HĐ/QĐ/PL',
    )
    date_from = fields.Date(string='From Date')
    basic_salary = fields.Float(string='Basic Salary')
    total_income = fields.Float(string='Total Income')
    allowance = fields.Float(string='Allowance')
    note = fields.Text(string='Note')
