from odoo import models, fields


class HrEmployeeBHXH(models.Model):
    _name = 'ps.hr.employee.bhxh'
    _description = 'Social Insurance (BHXH)'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade')
    insurance_number = fields.Char(string='Insurance Number')
    insurance_level = fields.Float(string='Contribution Rate')
    date_joined = fields.Date(string='Join Date')
    is_active = fields.Boolean(string='Active', default=True)
    insurance_category = fields.Char(string='Insurance Category')
    place_joined = fields.Char(string='Place Joined')
    join_method = fields.Char(string='Join Method')


class HrEmployeeBHYT(models.Model):
    _name = 'ps.hr.employee.bhyt'
    _description = 'Health Insurance (BHYT)'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade')
    kcb_code = fields.Char(string='Healthcare Examination Code')
    kcb_ticket = fields.Char(string='Healthcare Examination Ticket Number')
    insurance_level = fields.Float(string='Contribution Rate')
    date_start = fields.Date(string='Start Date')
    hospital_id = fields.Many2one('ps.hr.hospital', string='Registered Hospital')
    province_id = fields.Many2one('ps.hr.province', string='Registered Province')
    place_joined = fields.Char(string='Place Joined')
    join_method = fields.Char(string='Join Method')
    is_active = fields.Boolean(string='Active', default=True)


class HrHospital(models.Model):
    _name = 'ps.hr.hospital'
    _description = 'Hospital'

    code = fields.Char(string='Code')
    name = fields.Char(string='Hospital Name', required=True)
    province_id = fields.Many2one('ps.hr.province', string='Province')


class HrProvince(models.Model):
    _name = 'ps.hr.province'
    _description = 'Province/City'

    code = fields.Char(string='Code')
    name = fields.Char(string='Province Name', required=True)


class HrEmployeeBHTN(models.Model):
    _name = 'ps.hr.employee.bhtn'
    _description = 'Unemployment Insurance (BHTN)'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade')
    insurance_level = fields.Float(string='Contribution Rate')
    date_joined = fields.Date(string='Join Date')
    place_joined = fields.Char(string='Place Joined')
    is_active = fields.Boolean(string='Active', default=True)


class HrEmployeeAccidentInsurance(models.Model):
    _name = 'ps.hr.employee.insurance.accident'
    _description = 'Accident Insurance'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade')
    insurance_number = fields.Char(string='Insurance Number')
    insurance_level = fields.Float(string='Contribution Rate')
    insurance_category = fields.Char(string='Insurance Category')
    is_active = fields.Boolean(string='Active', default=True)
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')
    place_joined = fields.Char(string='Place Joined')
    join_method = fields.Char(string='Join Method')
    total_compensation = fields.Float(string='Total Compensation')
    compensation_per_case = fields.Float(string='Compensation per Case')


class HrEmployeeExternalInsurance(models.Model):
    _name = 'ps.hr.employee.insurance.external'
    _description = 'External Insurance'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade')
    insurance_number = fields.Char(string='Insurance Number')
    insurance_level = fields.Float(string='Contribution Rate')
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')
    provider_name = fields.Char(string='Provider Name')
