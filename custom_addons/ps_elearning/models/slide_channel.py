from odoo import models, fields, api

class SlideChannel(models.Model):
    _inherit = 'slide.channel'

    x_discuss_channel_id = fields.Many2one(
        'discuss.channel',
        string='Kênh thảo luận',
        readonly=True,
        copy=False,
    )

    def action_create_elearning_channel(self):
        self.ensure_one()
        channel_name = f"Khóa học - {self.name}"
        channel = self.env['discuss.channel'].create({
            'name': channel_name,
            'channel_type': 'channel',
        })
        partner_ids = set()
        # Người phụ trách khóa học
        if self.user_id:
            partner_ids.add(self.user_id.partner_id.id)
        # Các thành viên (slide.channel.partner ,học viên đã tham gia)
        for slide_partner in self.channel_partner_ids:
            if slide_partner.partner_id:
                partner_ids.add(slide_partner.partner_id.id)
        # User hiện tại
        partner_ids.add(self.env.user.partner_id.id)
        partner_ids = list(partner_ids)
        # Thêm member vào channel
        channel.add_members(partner_ids)
        self.x_discuss_channel_id = channel.id
        self.message_subscribe(partner_ids=partner_ids)
        return {
            'type': 'ir.actions.act_url',
            'url': f'/odoo/discuss?active_id=discuss.channel_{channel.id}',
            'target': 'self',
        }

    def action_open_elearning_channel(self):
        self.ensure_one()
        if self.x_discuss_channel_id:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/odoo/discuss?active_id=discuss.channel_{self.x_discuss_channel_id.id}',
                'target': 'self',
            }
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    
    is_mandatory_for_new_employee = fields.Boolean(
        string="Mandatory for New Employees",
        help="When checked, all new employees will automatically be enrolled in this course."
    )

    course_evaluation_survey_id = fields.Many2one(
        'survey.survey', 
        string='Course Evaluation Survey',
        help='Survey to evaluate the quality of the course.'
    )
    is_mandatory_evaluation = fields.Boolean(
        string='Mandatory Evaluation',
        help='If checked, participants must complete the evaluation survey to finish the course.'
    )
    has_completed_evaluation = fields.Boolean(
        compute='_compute_has_completed_evaluation',
        string="Has Completed Evaluation (Current User)"
    )
    department_ids = fields.Many2many(
        'hr.department', 
        string='Target Departments',
        help='Select departments. Employees belonging to these departments will be automatically enrolled in this course.'
    )

    @api.depends('course_evaluation_survey_id', 'is_mandatory_evaluation')
    def _compute_has_completed_evaluation(self):
        for channel in self:
            if not channel.is_mandatory_evaluation or not channel.course_evaluation_survey_id:
                channel.has_completed_evaluation = True
                continue
            
            if self.env.user._is_public():
                channel.has_completed_evaluation = False
                continue
                
            survey_done = self.env['survey.user_input'].sudo().search_count([
                ('survey_id', '=', channel.course_evaluation_survey_id.id),
                ('partner_id', '=', self.env.user.partner_id.id),
                ('x_channel_id', '=', channel.id),
                ('state', '=', 'done')
            ])
            channel.has_completed_evaluation = bool(survey_done)
            
    @api.model_create_multi
    def create(self, vals_list):
        channels = super(SlideChannel, self).create(vals_list)
        for channel in channels:
            if channel.department_ids:
                channel._enroll_department_employees()
        return channels

    def write(self, vals):
        res = super(SlideChannel, self).write(vals)
        if 'department_ids' in vals:
            for channel in self:
                channel._enroll_department_employees()
        return res

    def _enroll_department_employees(self):
        for channel in self:
            if not channel.department_ids:
                continue
            
            # Tìm tất cả nhân viên thuộc các phòng ban được chọn (và phải có tài khoản hệ thống)
            employees = self.env['hr.employee'].sudo().search([
                ('department_id', 'in', channel.department_ids.ids),
                ('user_id', '!=', False) 
            ])
            
            # Lấy danh sách partner_id của các nhân viên đó
            partner_ids = employees.mapped('user_id.partner_id.id')
            
            # Tìm xem ai đã tham gia khóa học rồi để tránh bị lỗi trùng lặp (duplicate)
            existing_partners = self.env['slide.channel.partner'].sudo().search([
                ('channel_id', '=', channel.id),
                ('partner_id', 'in', partner_ids)
            ]).mapped('partner_id.id')
            
            # Lọc ra những người mới chưa tham gia
            new_partner_ids = set(partner_ids) - set(existing_partners)
            
            # Tạo bản ghi để đưa họ vào khóa học
            if new_partner_ids:
                enrollment_vals = [{
                    'channel_id': channel.id,
                    'partner_id': partner_id,
                } for partner_id in new_partner_ids]
                self.env['slide.channel.partner'].sudo().create(enrollment_vals)