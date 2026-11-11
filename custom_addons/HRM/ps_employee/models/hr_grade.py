# model cấp bậc
from odoo import models, fields

class HrGrade(models.Model):
    _name = 'ps.hr.grade'
    _description = 'Grade'
    _order = 'sequence, name'


    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
