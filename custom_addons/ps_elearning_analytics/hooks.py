from pathlib import Path
import xml.etree.ElementTree as ET

from odoo import _


def _register_xmlid(env, module, name, model, record):
    data = env["ir.model.data"].sudo().search(
        [("module", "=", module), ("name", "=", name)], limit=1
    )
    if data:
        if data.model != model or data.res_id != record.id:
            raise RuntimeError(f"External ID {module}.{name} is already in use.")
        return
    env["ir.model.data"].sudo().create(
        {
            "module": module,
            "name": name,
            "model": model,
            "res_id": record.id,
            "noupdate": False,
        }
    )


def post_init_hook(env):
    template_dir = Path(__file__).parent / "templates"
    for filename in (
        "report_course_summary.xml",
        "report_courses_overview.xml",
        "report_course_progress.xml",
    ):
        root = ET.fromstring((template_dir / filename).read_text(encoding="utf-8"))
        key = root.attrib.get("t-name")
        if not key:
            raise RuntimeError(f"Report template {filename} has no t-name.")

        xmlid_module, xmlid_name = key.split(".", 1)
        if xmlid_module not in ("custom_elearning", "ps_elearning_analytics"):
            raise RuntimeError(f"Unsupported report template key {key}.")
        data = env["ir.model.data"].sudo().search(
            [("module", "=", xmlid_module), ("name", "=", xmlid_name)], limit=1
        )
        view = env["ir.ui.view"].sudo().browse()
        if data:
            if data.model != "ir.ui.view":
                raise RuntimeError(f"External ID {key} is not a QWeb view.")
            view = env["ir.ui.view"].sudo().browse(data.res_id).exists()
            if not view:
                raise RuntimeError(f"External ID {key} points to a missing view.")
        if not view:
            view = env["ir.ui.view"].sudo().search([("key", "=", key)], limit=1)

        values = {
            "name": key,
            "type": "qweb",
            "key": key,
            "model": False,
            "inherit_id": False,
            "mode": "primary",
            "active": True,
            "arch_db": ET.tostring(root, encoding="unicode"),
        }
        if view:
            view.write(values)
        else:
            view = env["ir.ui.view"].sudo().create(values)
        _register_xmlid(env, xmlid_module, xmlid_name, "ir.ui.view", view)
