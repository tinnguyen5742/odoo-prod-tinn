from odoo import api, fields, models


class SlideChannelReportWizard(models.TransientModel):
    _name = "slide.channel.report.wizard"
    _description = "Báo cáo khóa học"

    channel_id = fields.Many2one(
        "slide.channel",
        string="Tên khóa học",
        required=True,
        readonly=True,
        default=lambda self: self.env.context.get("active_id")
        or self.env.context.get("active_ids", [False])[0],
    )

    def action_preview(self):
        """Mở xem trước báo cáo dạng HTML trực tiếp trên trình duyệt."""
        self.ensure_one()
        action = self.env.ref(
            "ps_elearning_report.action_course_summary"
        ).report_action(self.channel_id)
        action.update({
            "report_type": "qweb-html",
            "target": "current",
        })
        return action

    def action_export_pdf(self):
        """Xuất và tải file báo cáo dạng PDF."""
        self.ensure_one()
        return self.env.ref(
            "ps_elearning_report.action_course_summary"
        ).report_action(self.channel_id)


class SlideChannelOverviewWizard(models.TransientModel):
    _name = "slide.channel.overview.wizard"
    _description = "Báo cáo tổng hợp"

    channel_ids = fields.Many2many(
        "slide.channel",
        string="Danh sách khóa học",
        default=lambda self: self._default_channel_ids(),
    )
    course_count = fields.Integer(
        string="Số lượng khóa học",
        compute="_compute_course_count",
    )

    @api.model
    def _default_channel_ids(self):
        active_ids = self.env.context.get("active_ids")
        if active_ids:
            return [(6, 0, active_ids)]
        # Nếu không có active_ids cụ thể, mặc định lấy tất cả các khóa học đang hoạt động và đã xuất bản
        courses = self.env["slide.channel"].search([
            ("active", "=", True),
            ("is_published", "=", True),
        ])
        return [(6, 0, courses.ids)]

    @api.depends("channel_ids")
    def _compute_course_count(self):
        for record in self:
            record.course_count = len(record.channel_ids)

    def action_preview(self):
        """Mở xem trước báo cáo tổng hợp dạng HTML trực tiếp trên trình duyệt."""
        self.ensure_one()
        action = self.env.ref(
            "ps_elearning_report.action_courses_overview"
        ).report_action(self.channel_ids)
        action.update({
            "report_type": "qweb-html",
            "target": "current",
        })
        return action

    def action_export_pdf(self):
        """Xuất và tải file báo cáo tổng hợp dạng PDF."""
        self.ensure_one()
        return self.env.ref(
            "ps_elearning_report.action_courses_overview"
        ).report_action(self.channel_ids)
