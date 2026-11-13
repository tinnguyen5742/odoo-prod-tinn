from odoo import SUPERUSER_ID, api


MODULE = "ps_elearning_analytics"


def _unlink_module_records(env, model_name, records):
    if not records:
        return
    env["ir.model.data"].search(
        [
            ("module", "=", MODULE),
            ("model", "=", model_name),
            ("res_id", "in", records.ids),
        ]
    ).unlink()
    records.unlink()


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    model_data = env["ir.model.data"]

    owned_views = model_data.search(
        [("module", "=", MODULE), ("model", "=", "ir.ui.view")]
    )
    views = env["ir.ui.view"].browse(owned_views.mapped("res_id")).exists()
    _unlink_module_records(
        env,
        "ir.ui.view",
        views.filtered(
            lambda view: view.model
            in ("hr.job", "slide.channel", "slide.channel.partner")
        ),
    )

    owned_rules = model_data.search(
        [("module", "=", MODULE), ("model", "=", "ir.rule")]
    )
    rules = env["ir.rule"].browse(owned_rules.mapped("res_id")).exists()
    _unlink_module_records(
        env,
        "ir.rule",
        rules.filtered(
            lambda rule: rule.model_id.model
            in ("slide.channel", "elearning.enroll.wizard")
        ),
    )

    owned_access = model_data.search(
        [("module", "=", MODULE), ("model", "=", "ir.model.access")]
    )
    accesses = env["ir.model.access"].browse(owned_access.mapped("res_id")).exists()
    _unlink_module_records(
        env,
        "ir.model.access",
        accesses.filtered(
            lambda access: access.model_id.model == "elearning.enroll.wizard"
        ),
    )

    actions = env["ir.actions.act_window"].search(
        [("res_model", "=", "elearning.enroll.wizard")]
    )
    menus = env["ir.ui.menu"].search(
        [
            (
                "action",
                "in",
                [f"ir.actions.act_window,{action_id}" for action_id in actions.ids],
            )
        ]
    )
    _unlink_module_records(env, "ir.ui.menu", menus)
    _unlink_module_records(env, "ir.actions.act_window", actions)

    owned_crons = model_data.search(
        [("module", "=", MODULE), ("model", "=", "ir.cron")]
    )
    crons = env["ir.cron"].browse(owned_crons.mapped("res_id")).exists()
    _unlink_module_records(
        env,
        "ir.cron",
        crons.filtered(
            lambda cron: "_cron_training_reminders" in (cron.code or "")
        ),
    )
