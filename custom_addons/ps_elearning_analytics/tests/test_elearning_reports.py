from odoo import Command
from odoo.tests import TransactionCase


class TestElearningReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env["slide.channel"].create(
            {
                "name": "Reporting test course",
                "channel_type": "training",
                "is_published": True,
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {"name": "Reporting Learner Test"}
        )

    def test_all_pdf_actions_are_bound_to_courses(self):
        for xmlid in (
            "ps_elearning_analytics.action_course_summary",
            "ps_elearning_analytics.action_courses_overview",
            "ps_elearning_analytics.action_course_progress",
            "ps_elearning_analytics.action_training_progress",
        ):
            report = self.env.ref(xmlid)
            self.assertEqual(report.model, "slide.channel")
            self.assertEqual(report.report_type, "qweb-pdf")

    def test_all_report_templates_are_registered(self):
        for xmlid in (
            "custom_elearning.report_course_summary",
            "custom_elearning.report_courses_overview",
            "custom_elearning.report_course_progress",
            "ps_elearning_analytics.report_training_progress",
        ):
            self.assertTrue(self.env.ref(xmlid).exists())

    def test_course_progress_report_renders_enrollment(self):
        self.env["slide.channel.partner"].create(
            {
                "channel_id": self.channel.id,
                "partner_id": self.partner.id,
                "member_status": "ongoing",
                "completion": 20,
            }
        )
        report = self.env.ref("ps_elearning_analytics.action_course_progress")
        html, content_type = report._render_qweb_html(
            "ps_elearning_analytics.action_course_progress", self.channel.ids
        )
        self.assertEqual(content_type, "html")
        rendered = html.decode()
        self.assertIn("Reporting Learner Test", rendered)
        self.assertIn("Ngày ghi danh", rendered)
        self.assertIn("Cập nhật gần nhất", rendered)
        self.assertIn("Bài học tiếp theo", rendered)
        self.assertEqual(report.paperformat_id.orientation, "Landscape")

    def test_training_progress_report_renders_enrollment(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(
                        self.env.ref(
                            "ps_elearning_analytics.group_elearning_hr_manager"
                        ).id
                    )
                ]
            }
        )
        self.env["slide.channel.partner"].create(
            {
                "channel_id": self.channel.id,
                "partner_id": self.partner.id,
                "member_status": "ongoing",
                "completion": 20,
            }
        )
        report = self.env.ref("ps_elearning_analytics.action_training_progress")
        html, content_type = report._render_qweb_html(
            "ps_elearning_analytics.action_training_progress", self.channel.ids
        )
        self.assertEqual(content_type, "html")
        rendered = html.decode()
        self.assertIn("BÁO CÁO TIẾN ĐỘ ĐÀO TẠO NHÂN VIÊN", rendered)
        self.assertIn("Reporting Learner Test", rendered)
        self.assertIn("Ngày ghi danh", rendered)
        self.assertIn("Bài học tiếp theo", rendered)

    def test_analytics_view_contains_enrollment(self):
        self.env["slide.channel.partner"].create(
            {
                "channel_id": self.channel.id,
                "partner_id": self.partner.id,
                "member_status": "ongoing",
                "completion": 20,
            }
        )
        row = self.env["elearning.training.report"].search(
            [("course_id", "=", self.channel.id), ("partner_id", "=", self.partner.id)]
        )
        self.assertEqual(len(row), 1)
        self.assertEqual(row.member_status, "ongoing")
        self.assertEqual(row.completion, 20)
