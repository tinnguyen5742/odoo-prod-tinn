from odoo import models, fields, api
import logging

from odoo.orm.decorators import readonly

_logger = logging.getLogger(__name__)

_logger.warning("CREATE EMPLOYEE OVERRIDE RUNNING")


class PsHrApplicant(models.Model):
    _inherit = 'hr.applicant'

    x_applicant_id = fields.Many2one('hr.applicant', string='Applicant', readonly=True)
    x_birth_date = fields.Date(string='Ngày sinh', )
    x_address = fields.Char(string='Địa chỉ', )
    x_gender = fields.Selection(selection=[('male', 'Nam'), ('female', 'Nữ'), ('other', 'Khác'), ],
                                string='Giới tính', )
    x_ethnicity = fields.Char(string='Dân tộc')
    x_religion = fields.Char(string='Tôn giáo')
    professional_level_id = fields.Many2one('ps.hr.level', string='Trình độ chuyên môn',
                                            domain=[('type', '=', 'professional')])
    x_employee_code = fields.Char(string='Mã nhân viên', copy=False, readonly=True)
    x_employee_code_readonly = fields.Boolean(compute='_compute_employee_code_readonly')

    @api.depends('x_applicant_id')
    def _compute_employee_code_readonly(self):
        for rec in self:
            rec.x_employee_code_readonly = bool(rec.x_applicant_id)

    def write(self, vals):
        return super().write(vals)

    def create_employee_from_applicant(self):
        field_mapping = {
            'birthday': 'x_birth_date',
            'place_of_birth': 'x_address',
            'sex': 'x_gender',
            'x_ethnicity': 'x_ethnicity',
            'x_religion': 'x_religion',
            'education_level_id': 'type_id',
            'professional_level_id': 'professional_level_id',
            'x_employee_code': 'x_employee_code',
        }

        sequence = self.env['ir.sequence']
        employee_codes = {
            applicant.id: sequence.next_by_code('ps.employee.code')
            for applicant in self
            if not applicant.x_employee_code
        }

        res = super().create_employee_from_applicant()

        for applicant in self.filtered('employee_id'):
            employee = applicant.employee_id

            vals = {
                emp_field: (
                    value.id if hasattr(value, 'id') else value
                )
                for emp_field, app_field in field_mapping.items()
                if (value := applicant[app_field])
            }

            if applicant.id in employee_codes:
                code = employee_codes[applicant.id]
                vals['x_employee_code'] = code
                applicant.x_employee_code = code

            vals['x_applicant_id'] = applicant.id

            employee.write(vals)

        return res
