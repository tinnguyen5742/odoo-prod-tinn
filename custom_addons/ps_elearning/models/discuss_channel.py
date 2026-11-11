from odoo import models, fields


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    x_is_slide_channel = fields.Boolean(
        string='Course Channel',
        compute='_compute_is_slide_channel',
    )

    # check xem channel này có được tạo từ khóa học không
    def _compute_is_slide_channel(self):
        courses = self.env['slide.channel'].sudo().search([
            ('x_discuss_channel_id', 'in', self.ids)
        ])
        course_channel_ids = set(courses.mapped('x_discuss_channel_id').ids)
        for channel in self:
            channel.x_is_slide_channel = channel.id in course_channel_ids

    # Khi gửi dữ liệu của channel sang frontend(OWL / JavaScript Store), gửi thêm field x_is_slide_channel
    def _to_store_defaults(self, target):
        res = super()._to_store_defaults(target)
        res.append('x_is_slide_channel')
        return res

    # Đăng ký field này để đồng bộ(sync) giữa Backend và Frontend.
    def _sync_field_names(self):
        res = super()._sync_field_names()
        res[None].append('x_is_slide_channel')
        return res

    # action quay về khóa học từ chat
    def action_open_linked_course(self):
        self.ensure_one()
        course = self.env['slide.channel'].sudo().search(
            [('x_discuss_channel_id', '=', self.id)], limit=1)
        if course:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'slide.channel',
                'res_id': course.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
            }
        return {'type': 'ir.actions.act_window_close'}
