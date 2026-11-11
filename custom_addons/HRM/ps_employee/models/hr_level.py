# model trình độ
from odoo import models, fields

class PsHrLevel(models.Model):
    _name = 'ps.hr.level'
    _description = 'HR Qualification'
    _order = 'type, sequence, name'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True, index=True)

    type = fields.Selection([
        ('education', 'Education'),
        ('professional', 'Professional'),
        ('other', 'Other'),
        ('language', 'Language'),
        ('it', 'Information Technology'),
    ], string='Type', required=True)

    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)