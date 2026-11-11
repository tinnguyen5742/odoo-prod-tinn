from odoo import models, api

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model_create_multi
    def create(self, vals_list):
        employees = super(HrEmployee, self).create(vals_list)
        
        for employee in employees:
            employee._enroll_mandatory_courses()
        #  Quét và ghi danh khóa học theo Phòng ban
        department_ids = employees.mapped('department_id').ids
        if department_ids:
            channels = self.env['slide.channel'].sudo().search([('department_ids', 'in', department_ids)])
            if channels:
                channels._enroll_department_employees()
            
        return employees
    
    def write(self, vals):
        res = super(HrEmployee, self).write(vals)
        
        # Nếu có sự thay đổi về Phòng ban hoặc Người dùng liên quan
        if 'department_id' in vals or 'user_id' in vals:
            department_ids = self.mapped('department_id').ids
            if department_ids:
                channels = self.env['slide.channel'].sudo().search([('department_ids', 'in', department_ids)])
                if channels:
                    channels._enroll_department_employees()
                    
        return res

    def _enroll_mandatory_courses(self):
        SlideChannel = self.env['slide.channel']
        SlideChannelPartner = self.env['slide.channel.partner']

        for employee in self:
            partner = employee.user_id.partner_id or employee.work_contact_id or employee.address_home_id
            if not partner:
                continue

            # Lấy khóa học chung
            mandatory_courses = SlideChannel.search([('is_mandatory_for_new_employee', '=', True)])

            # Lấy khóa học theo phòng ban/vị trí
            if employee.job_id and employee.job_id.mandatory_course_ids:
                mandatory_courses |= employee.job_id.mandatory_course_ids

            # Ghi danh
            for course in mandatory_courses:
                existing_enrollment = SlideChannelPartner.search([
                    ('channel_id', '=', course.id),
                    ('partner_id', '=', partner.id)
                ], limit=1)

                if not existing_enrollment:
                    SlideChannelPartner.create({
                        'channel_id': course.id,
                        'partner_id': partner.id,
                    })