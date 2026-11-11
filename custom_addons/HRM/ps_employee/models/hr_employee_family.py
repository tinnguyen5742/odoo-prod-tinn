from odoo import models, fields


class HrEmployeeFamily(models.Model):
    _name = 'ps.hr.employee.family'
    _description = 'Family Member'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade')
    name = fields.Char(string='Full Name')
    relationship = fields.Selection([
        ('father', 'Father'),
        ('mother', 'Mother'),
        ('spouse', 'Spouse'),
        ('child', 'Child'),
        ('sibling', 'Sibling'),
        ('other', 'Other'),
    ], string='Relationship')
    date_of_birth = fields.Date(string='Date of Birth')
    id_number = fields.Char(string='ID Card/Visa/Passport')
    book_number = fields.Char(string='Book Number')
    birth_certificate = fields.Char(string='Birth Certificate Number')
    tax_code = fields.Char(string='Tax Code')
    is_dependent = fields.Boolean(string='Dependent')
    education_level = fields.Char(string='Education Level')
    job = fields.Char(string='Occupation')
    address = fields.Char(string='Address')
    mobile = fields.Char(string='Mobile')
    date_from = fields.Date(string='From Date')
    date_to = fields.Date(string='To Date')
    biography = fields.Text(string='Biography Summary')
    note = fields.Char(string='Note')
