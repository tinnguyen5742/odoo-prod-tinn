# model hợp đồng

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class HrContract(models.Model):
    _name = 'ps.hr.contract'
    _description = 'HR Contract'
    _rec_name = 'name'
    _order = 'x_date_start desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Contract Code', readonly=True, default=lambda self: self._default_contract_code())
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)

    x_contract_type = fields.Many2one('hr.contract.type', string='Contract Type', required=True)

    date_sign = fields.Date(string='Sign Date')
    x_date_start = fields.Date(string='Start Date', required=True,tracking=True)
    x_date_end = fields.Date(string='End Date', required=True,tracking=True)
    x_date_create = fields.Date(string='Create Date', default=fields.Date.today)

    percent_salary = fields.Float(string='Salary Percent', default=100)
    wage = fields.Float(string='Wage', required=True,tracking=True)
    allowance = fields.Float(string='Allowance',tracking=True)
    total_income = fields.Float(string='Total Income', compute='_compute_total', store=True)

    x_grade = fields.Many2one('ps.hr.grade', string='Grade')
    x_job_title = fields.Char(string='Job Title')
    x_position = fields.Char(string='Position')
    x_salary_grade = fields.Many2one('ps.hr.salary.grade', string='Salary Grade')
    x_ins_salary = fields.Float(string='Insured Salary')

    work_address = fields.Char(string='Work Address')
    note = fields.Text(string='Note')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('expiring', 'Expiring Soon'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string='Status', compute='_compute_state', store=True, default='draft')
    is_cancelled = fields.Boolean(string='Cancelled')

    x_rep_id = fields.Many2one('hr.employee', string='Representative', required=True)
    x_rep_job = fields.Char(related='x_rep_id.job_title', string='Representative Job Title', readonly=True)
    x_rep_company = fields.Char(related='x_rep_id.company_id.name', string='Company', readonly=True)
    x_rep_address = fields.Char(related='x_rep_id.address_id.display_name', string='Address', readonly=True)
    x_rep_mobile = fields.Char(related='x_rep_id.mobile_phone', string='Mobile', readonly=True)
    x_rep_fax = fields.Char(related='x_rep_id.work_phone', string='Fax', readonly=True)
    x_rep_email = fields.Char(related='x_rep_id.work_email', string='Email', readonly=True)

    x_emp_name = fields.Char(related='employee_id.name', string='Employee Name', readonly=True)
    x_emp_birthday = fields.Date(related='employee_id.birthday', string='Birthday', readonly=True)
    x_emp_id_num = fields.Char(related='employee_id.identification_id', string='ID Number', readonly=True)
    x_emp_id_date = fields.Date(related='employee_id.identification_date', string='ID Issue Date', readonly=True)
    x_emp_id_place = fields.Char(related='employee_id.identification_address', string='ID Issue Place', readonly=True)

    @api.depends('x_date_start', 'x_date_end', 'is_cancelled')
    def _compute_state(self):
        today = fields.Date.today()
        for rec in self:
            if rec.is_cancelled:
                rec.state = 'cancelled'
            elif rec.x_date_end and rec.x_date_end < today:
                rec.state = 'expired'
            elif rec.x_date_end and (rec.x_date_end - today).days <= 30:
                rec.state = 'expiring'
            elif not rec.x_date_start or rec.x_date_start <= today:
                rec.state = 'running'
            else:
                rec.state = 'draft'

    @api.constrains('x_date_start', 'x_date_end', 'wage')
    def _check_validity(self):
        for rec in self:
            if rec.x_date_end and rec.x_date_start and rec.x_date_end <= rec.x_date_start:
                raise ValidationError(_("End Date must be later than Start Date."))
            if rec.wage and rec.wage <= 0:
                raise ValidationError(_("Wage must be greater than 0."))

    def action_cancel(self):
        today = fields.Date.today()
        for rec in self:
            rec.write({
                'is_cancelled': True,
                'x_date_end': rec.x_date_end or today,
            })

    def action_draft(self):
        self.is_cancelled = False

    @api.depends('wage', 'percent_salary', 'allowance')
    def _compute_total(self):
        for rec in self:
            rec.total_income = (rec.wage * rec.percent_salary / 100) + rec.allowance

    def _default_contract_code(self):
        IrSequence = self.env['ir.sequence'].sudo()
        seq = IrSequence.next_by_code('ps.hr.contract')
        if seq:
            return seq
        IrSequence.create({
            'name': 'Hợp đồng lao động',
            'code': 'ps.hr.contract',
            'prefix': 'HĐTD-%(year)s-',
            'padding': 4,
        })
        return IrSequence.next_by_code('ps.hr.contract') or '/'

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            self.x_job_title = self.employee_id.job_title
            self.x_position = self.employee_id.job_id.name if self.employee_id.job_id else False
