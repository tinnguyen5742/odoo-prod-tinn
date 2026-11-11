from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class HrContractMass(models.TransientModel):
    _name = 'ps.hr.contract.mass'
    _description = 'Mass Create Contracts'
    _rec_name = 'name'

    employee_ids = fields.Many2many('hr.employee', string='Employee', required=True)
    x_rep_id = fields.Many2one('hr.employee', string='Representative')
    name = fields.Char(default='Mass Create Contracts')

    contract_template_id = fields.Many2one(
        'hr.version',
        string='Contract Template',
        domain=[('employee_id', '=', False)],
    )
    contract_template_name = fields.Char(
        string='Contract Name',
        related='contract_template_id.name',
        readonly=True,
    )

    x_contract_type = fields.Many2one('hr.contract.type', string='Contract Type', required=True)
    date_sign = fields.Date(string='Sign Date')
    x_date_create = fields.Date(string='Create Date', default=fields.Date.today)
    x_date_start = fields.Date(string='Start Date', required=True)
    x_date_end = fields.Date(string='End Date', required=True)

    percent_salary = fields.Float(string='Salary Percent', default=100)
    wage = fields.Float(string='Wage', required=True)
    allowance = fields.Float(string='Allowance')

    x_grade = fields.Many2one('ps.hr.grade', string='Grade')
    x_job_title = fields.Char(string='Job Title')
    x_position = fields.Char(string='Position')
    x_salary_grade = fields.Many2one('ps.hr.salary.grade', string='Salary Grade')
    x_ins_salary = fields.Float(string='Insured Salary')

    work_address = fields.Char(string='Work Address')
    note = fields.Text(string='Note')

    @api.onchange('contract_template_id')
    def _onchange_contract_template_id(self):
        if not self.contract_template_id:
            return
        template = self.contract_template_id
        if template.contract_type_id:
            self.x_contract_type = template.contract_type_id
        if template.wage:
            self.wage = template.wage
        if template.date_start:
            self.x_date_start = template.date_start
        if template.date_end:
            self.x_date_end = template.date_end

    def action_create(self):
        if self.x_date_end and self.x_date_start and self.x_date_end <= self.x_date_start:
            raise ValidationError(_("End Date must be later than Start Date."))
        if self.wage and self.wage <= 0:
            raise ValidationError(_("Wage must be greater than 0."))

        vals_list = []
        Contract = self.env['ps.hr.contract']
        for employee in self.employee_ids:
            vals_list.append({
                'name': Contract._default_contract_code(),
                'employee_id': employee.id,
                'x_rep_id': self.x_rep_id.id,
                'x_contract_type': self.x_contract_type.id,
                'date_sign': self.date_sign,
                'x_date_create': self.x_date_create,
                'x_date_start': self.x_date_start,
                'x_date_end': self.x_date_end,
                'percent_salary': self.percent_salary,
                'wage': self.wage,
                'allowance': self.allowance,
                'x_grade': self.x_grade.id,
                'x_job_title': self.x_job_title,
                'x_position': self.x_position,
                'x_salary_grade': self.x_salary_grade.id,
                'x_ins_salary': self.x_ins_salary,
                'work_address': self.work_address,
                'note': self.note,
            })
        contracts = Contract.create(vals_list)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Contracts',
            'res_model': 'ps.hr.contract',
            'view_mode': 'list,form',
            'domain': [('id', 'in', contracts.ids)],
        }
