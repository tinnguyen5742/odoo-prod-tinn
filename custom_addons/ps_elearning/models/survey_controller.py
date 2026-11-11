from odoo import http
from odoo.http import request, content_disposition
from odoo.addons.survey.controllers.main import Survey


class PsElearningSurvey(Survey):

    @http.route(
        ['/survey/<string:survey_token>/<string:answer_token>/certificate_inline'],
        type='http',
        auth='public',
        methods=['GET'],
        website=True,
    )
    def certificate_inline(self, survey_token, answer_token, **kwargs):
        """Xem giấy chứng nhận PDF inline ngay trên trình duyệt."""
        # Tìm survey + user_input theo access token (giống core)
        survey_sudo, answer_sudo = self._fetch_from_access_token(
            survey_token, answer_token,
        )
        if not (survey_sudo and answer_sudo and answer_sudo.scoring_success):
            return request.redirect("/")

        # Render PDF chứng nhận từ report gốc của survey
        # Ép ngôn ngữ theo preference của user (My Preferences): tiếng Việt -> cert tiếng Việt, còn lại -> tiếng Anh
        user_lang = request.env.user.lang or 'vi_VN'
        report = request.env["ir.actions.report"].sudo().with_context(lang=user_lang)._render_qweb_pdf(
            'survey.certification_report',
            [answer_sudo.id],
            data={'report_type': 'pdf'},
        )[0]

        # Đổi header sang inline để xem trực tiếp thay vì tải về
        content_dis = content_disposition('Certification.pdf')
        content_split = content_dis.split(';')
        content_split[0] = 'inline'
        content_dis = ';'.join(content_split)

        return request.make_response(report, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(report)),
            ('Content-Disposition', content_dis),
        ])

    @http.route(
        '/ps_elearning/evaluation/<int:channel_id>',
        type='http',
        auth='user',
        methods=['GET'],
        website=True,
    )
    def course_evaluation_start(self, channel_id, **kwargs):
        """Bắt đầu (hoặc tiếp tục) khảo sát đánh giá cho đúng khóa học này."""
        channel = request.env['slide.channel'].sudo().browse(channel_id).exists()
        if not channel or not channel.course_evaluation_survey_id:
            return request.redirect('/slides')

        partner = request.env.user.partner_id
        is_member = request.env['slide.channel.partner'].sudo().search_count([
            ('channel_id', '=', channel.id),
            ('partner_id', '=', partner.id),
        ])
        if not is_member:
            return request.redirect(channel.website_url)

        survey = channel.course_evaluation_survey_id
        answer = request.env['survey.user_input'].sudo().search([
            ('survey_id', '=', survey.id),
            ('partner_id', '=', partner.id),
            ('x_channel_id', '=', channel.id),
        ], order='id desc', limit=1)
        if not answer:
            answer = survey._create_answer(user=request.env.user, x_channel_id=channel.id)

        return request.redirect(
            '/survey/start/%s?answer_token=%s' % (survey.access_token, answer.access_token)
        )