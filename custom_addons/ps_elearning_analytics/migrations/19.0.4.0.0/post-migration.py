from pathlib import Path

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    template = (
        Path(__file__).resolve().parents[2]
        / "templates"
        / "report_course_progress.xml"
    )
    view = env["ir.ui.view"].sudo().search(
        [("key", "=", "custom_elearning.report_course_progress")], limit=1
    )
    if not view:
        raise RuntimeError(
            "The custom_elearning.report_course_progress QWeb view was not found."
        )
    view.write({"arch_db": template.read_text(encoding="utf-8")})
