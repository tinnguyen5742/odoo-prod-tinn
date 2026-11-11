from odoo import models


class SlideChannelPartner(models.Model):
    _inherit = 'slide.channel.partner'

    def _is_evaluation_pending(self):
        """True nếu khóa yêu cầu đánh giá bắt buộc mà học viên chưa nộp."""
        self.ensure_one()
        channel = self.channel_id
        if not (channel.is_mandatory_evaluation and channel.course_evaluation_survey_id):
            return False
        survey_done = self.env['survey.user_input'].sudo().search_count([
            ('survey_id', '=', channel.course_evaluation_survey_id.id),
            ('partner_id', '=', self.partner_id.id),
            ('x_channel_id', '=', channel.id), 
            ('state', '=', 'done'),
        ])
        return not survey_done

    def write(self, vals):
        if vals.get('member_status') == 'completed':
            blocked = self.filtered(
                lambda r: r.member_status != 'completed' and r._is_evaluation_pending()
            )
            allowed = self - blocked
            if blocked:
                # Học đủ 100% nhưng chưa đánh giá: giữ ở trạng thái "ongoing"
                super(SlideChannelPartner, blocked).write(dict(vals, member_status='ongoing'))
            if allowed:
                return super(SlideChannelPartner, allowed).write(vals)
            return True
        return super().write(vals)

    def _post_completion_update_hook(self, completed=True):
        # Không cộng karma khi chưa thật sự hoàn thành
        if completed:
            self = self.filtered(lambda r: r.member_status == 'completed')
        return super(SlideChannelPartner, self)._post_completion_update_hook(completed=completed)

    def _send_completed_mail(self):
        # Không gửi mail "đã hoàn thành" khi chưa đánh giá
        self = self.filtered(lambda r: r.member_status == 'completed')
        return super(SlideChannelPartner, self)._send_completed_mail()

    def _complete_after_evaluation(self):
        """Gọi khi học viên nộp khảo sát: hoàn tất khóa nếu đã học đủ 100%."""
        to_complete = self.filtered(
            lambda r: r.member_status != 'completed'
            and r.completion == 100
            and not r._is_evaluation_pending()
        )
        if to_complete:
            to_complete.write({'member_status': 'completed'})
            to_complete._post_completion_update_hook(completed=True)
            to_complete._send_completed_mail()