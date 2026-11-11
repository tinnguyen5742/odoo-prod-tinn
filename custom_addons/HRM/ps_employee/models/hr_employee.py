import logging

from odoo import models, fields, api, _

from odoo.addons.ps_vn_address.models import vn_address_service as vn_addr

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    family_ids = fields.One2many('ps.hr.employee.family', 'employee_id', string='Family Members')
    representative_employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Representative',
    )
    representative_job_title = fields.Char(
        related='representative_employee_id.job_title',
        string='Job Title',
    )
    representative_company = fields.Many2one(
        related='representative_employee_id.company_id',
        string='Company',
    )
    representative_address = fields.Many2one(
        related='representative_employee_id.address_id',
        string='Address',
    )
    representative_mobile = fields.Char(
        related='representative_employee_id.mobile_phone',
        string='Mobile',
    )
    representative_fax = fields.Char(
        related='representative_employee_id.work_phone',
        string='Fax Number',
    )
    representative_email = fields.Char(
        related='representative_employee_id.work_email',
        string='Email',
    )

    salary_history_ids = fields.One2many('ps.hr.employee.salary.history', 'employee_id', string='Salary History')
    bhxh_ids = fields.One2many('ps.hr.employee.bhxh', 'employee_id', string='Social Insurance (BHXH)')
    bhyt_ids = fields.One2many('ps.hr.employee.bhyt', 'employee_id', string='Health Insurance (BHYT)')
    bhtn_ids = fields.One2many('ps.hr.employee.bhtn', 'employee_id', string='Unemployment Insurance (BHTN)')
    accident_insurance_ids = fields.One2many('ps.hr.employee.insurance.accident', 'employee_id',
                                             string='Accident Insurance')
    external_insurance_ids = fields.One2many('ps.hr.employee.insurance.external', 'employee_id',
                                             string='External Insurance')
    identification_date = fields.Date(string='ID Card Issue Date')
    identification_address = fields.Char(string='ID Card Issue Place')
    nationality = fields.Char(string='Nationality', default='Vietnam')
    x_religion = fields.Char(string='Religion', default='None')
    education_level_id = fields.Many2one(
        'ps.hr.level',
        string='Education Level',
        domain=[('type', '=', 'education')]
    )

    professional_level_id = fields.Many2one(
        'ps.hr.level',
        string='Professional Level',
        domain=[('type', '=', 'professional')]
    )

    other_level_id = fields.Many2one(
        'ps.hr.level',
        string='Other Level',
        domain=[('type', '=', 'other')]
    )

    language_level_id = fields.Many2one(
        'ps.hr.level',
        string='Language Level',
        domain=[('type', '=', 'language')]
    )

    it_level_id = fields.Many2one(
        'ps.hr.level',
        string='IT Level',
        domain=[('type', '=', 'it')]
    )

    tax_code = fields.Char(string='Tax Code')
    party_member = fields.Boolean(string='Party Member', default=False)
    union_member = fields.Boolean(string='Youth Union Member', default=False)
    trade_union = fields.Boolean(string='Trade Union Member', default=False)
    party_join_date = fields.Date(string='Party Join Date')
    union_join_date = fields.Date(string='Union Join Date')
    trade_union_join_date = fields.Date(string='Trade Union Join Date')
    x_ethnicity = fields.Char(string='Ethnicity')
    x_employee_code = fields.Char(string='Employee Code', copy=False)
    x_applicant_id = fields.Many2one('hr.applicant', string='Applicant', readonly=True, ondelete='set null')
    x_employee_code_readonly = fields.Boolean(compute='_compute_employee_code_readonly', store=False)
    x_sale_province = fields.Many2one('res.country.state', string='Assigned Province/City')

    x_address_old = fields.Char(string='Pre-Merger Address')
    x_permanent_address = fields.Char(string='Permanent Address')
    x_current_address_edit_mode = fields.Boolean(
        string='Current Address Edit Mode',
        default=True,
    )

    x_other_document_ids = fields.One2many(
        'ps.hr.employee.other', 'employee_id',
        string='Visa & Work Permit Documents'
    )

    x_contract_ids = fields.One2many(
        'ps.hr.contract', 'employee_id',
        string='Hợp đồng lao động'
    )

    @api.depends('x_applicant_id')
    def _compute_employee_code_readonly(self):
        for rec in self:
            rec.x_employee_code_readonly = bool(rec.x_applicant_id)

    @api.onchange('x_address_old')
    def _onchange_x_address_old(self):
        if not self.x_address_old:
            self.x_current_address_edit_mode = True
            return
        if not self._apply_current_address(self.x_address_old):
            return {
                'warning': {
                    'title': _('Address Conversion Failed'),
                    'message': _('No matching new address found for: %s', self.x_address_old),
                }
            }

    @api.onchange('x_permanent_address')
    def _onchange_permanent_address(self):
        if self.env.context.get('vn_address_no_recompute'):
            return
        if not self.x_permanent_address:
            return
        result = self._convert_address(self.x_permanent_address)
        if not result:
            return {
                'warning': {
                    'title': _('Address Conversion Failed'),
                    'message': _('No matching new address found for: %s', self.x_permanent_address),
                }
            }
        self.with_context(vn_address_no_recompute=True).x_permanent_address = result['new_full_address']

    def action_edit_current_address(self):
        for rec in self:
            rec.x_current_address_edit_mode = True

    def _convert_address(self, address):
        """Parse and convert the address to the new structure.

        Returns a result dict if successful, None otherwise.
        """
        parsed = vn_addr.parse_vn_address(address)
        if not parsed:
            return None

        api_key = vn_addr._get_api_key(self.env)
        if not api_key:
            _logger.warning("Missing tinhthanhpho.com API key for address conversion")
            return None

        converted = vn_addr.convert_old_to_new_address(
            parsed['province_code'],
            parsed['district_code'],
            parsed['ward_code'],
            parsed['street'],
            api_key,
        )
        if not converted or not converted.get('new'):
            return None

        new = converted['new']
        province_name = new.get('province', {}).get('name')
        ward_name = new.get('ward', {}).get('name')
        street = parsed['street']
        new_full = new.get('fullAddress') or ", ".join(filter(None, [street, ward_name, province_name]))
        return {
            'parsed': parsed,
            'converted': converted,
            'new_full_address': new_full,
        }

    def _apply_current_address(self, address):
        """Parse and convert the current address, then fill in the private address fields.

        Returns a result dict if successful, None otherwise.
        """
        result = self._convert_address(address)
        if not result:
            return None

        parsed = result['parsed']
        new = result['converted']['new']
        province_name = new.get('province', {}).get('name')
        ward_name = new.get('ward', {}).get('name')
        state = vn_addr._find_state(self.env, province_name)
        country = vn_addr._find_vn_country(self.env)

        self.update({
            'private_street': parsed['street'] or '',
            'private_street2': '',
            'private_city': ward_name or '',
            'private_state_id': state.id if state else False,
            'private_country_id': country.id if country else False,
            'private_zip': '',
        })
        self.x_current_address_edit_mode = False
        return result


# Class tab khac trong nhân viên
class HrEmployeeOther(models.Model):
    _name = 'ps.hr.employee.other'
    _description = 'Visa & Work Permit Document'
    _rec_name = 'x_document_no'
    _order = 'x_issue_date desc'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, ondelete='cascade')
    x_document_type = fields.Selection([
        ('visa', 'Visa'),
        ('passport', 'Passport'),
        ('work_permit', 'Work Permit'),
        ('temporary_residence', 'Temporary Residence'),
        ('other', 'Other'),
    ], string='Document Type', required=True)
    x_document_no = fields.Char(string='Document No', required=True)
    x_issue_date = fields.Date(string='Issue Date')
    x_issue_place = fields.Char(string='Issue Place')
    x_expiry_date = fields.Date(string='Expiry Date')
    x_document_file = fields.Binary(string='Attachment', attachment=True)
    x_document_filename = fields.Char(string='File Name')
    x_notes = fields.Text(string='Notes')

    # Mở chi tiết record
    def action_open_record(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': self._name,
            'res_id': self.id,
            'target': 'new',
        }

    # button xem chứng chỉ
    def action_preview_document(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/%s' % (self._name, self.id, 'x_document_file'),
            'target': 'new',
        }
