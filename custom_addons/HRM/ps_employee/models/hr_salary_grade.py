# model học vấn
from odoo import models, fields

class HrSalaryGrade(models.Model):
    _name = 'ps.hr.salary.grade'
    _description = 'Salary Grade'

    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Name', required=True)
