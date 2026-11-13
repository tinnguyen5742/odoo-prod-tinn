from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class QualityDashboard(models.TransientModel):
    _name = "ps.quality.dashboard"
    _description = "Quality Management Dashboard"

    inspection_count = fields.Integer(compute="_compute_metrics")
    passed_count = fields.Integer(compute="_compute_metrics")
    failed_count = fields.Integer(compute="_compute_metrics")
    pass_rate = fields.Float(compute="_compute_metrics", digits=(6, 2))
    open_ncr_count = fields.Integer(compute="_compute_metrics")
    open_capa_count = fields.Integer(compute="_compute_metrics")
    overdue_equipment_count = fields.Integer(compute="_compute_metrics")
    avg_ncr_resolution_days = fields.Float(compute="_compute_metrics", digits=(6, 2))
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    def _new_action(self, model, label):
        return {
            "type": "ir.actions.act_window",
            "name": label,
            "res_model": model,
            "view_mode": "form",
            "target": "current",
            "context": dict(self.env.context, default_company_id=self.env.company.id),
        }

    def action_new_inspection(self):
        if not self.env.user.has_group("ps_quality.group_quality_user"):
            raise AccessError(_("You are not allowed to create quality inspections."))
        return self._new_action("ps.quality.inspection", _("New quality inspection"))

    def action_new_standard(self):
        if not self.env.user.has_group("ps_quality.group_quality_administrator"):
            raise AccessError(_("Only a Quality Administrator can create standards."))
        return self._new_action("ps.quality.standard", _("New quality standard"))

    def action_new_plan(self):
        if not self.env.user.has_group("ps_quality.group_quality_manager"):
            raise AccessError(_("Only a Quality Manager can create inspection plans."))
        return self._new_action("ps.quality.plan", _("New inspection plan"))

    def action_new_ncr(self):
        if not self.env.user.has_group("ps_quality.group_quality_inspector"):
            raise AccessError(_("Only a Quality Inspector can create an NCR."))
        return self._new_action("ps.quality.ncr", _("New non-conformance report"))

    def action_new_capa(self):
        if not self.env.user.has_group("ps_quality.group_quality_manager"):
            raise AccessError(_("Only a Quality Manager can create CAPA actions."))
        return self._new_action("ps.quality.capa", _("New CAPA action"))

    def action_new_equipment(self):
        if not self.env.user.has_group("ps_quality.group_quality_manager"):
            raise AccessError(_("Only a Quality Manager can create measurement equipment."))
        return self._new_action("ps.quality.equipment", _("New measurement equipment"))

    @api.depends_context("uid", "company")
    def _compute_metrics(self):
        company = self.env.company
        domain = [("company_id", "=", company.id)]
        inspections = self.env["ps.quality.inspection"].search(domain)
        ncrs = self.env["ps.quality.ncr"].search(domain)
        capas = self.env["ps.quality.capa"].search(domain)
        equipment = self.env["ps.quality.equipment"].search(domain)
        completed = inspections.filtered(lambda record: record.result in ("pass", "fail"))
        passed = completed.filtered(lambda record: record.result == "pass")
        failed = completed.filtered(lambda record: record.result == "fail")
        open_ncrs = ncrs.filtered(lambda record: record.state not in ("closed", "cancelled"))
        open_capas = capas.filtered(lambda record: record.state not in ("closed", "cancelled"))
        due_equipment = equipment.filtered(
            lambda record: record.calibration_state in ("due", "overdue", "not_calibrated")
        )
        closed_ncrs = ncrs.filtered(lambda record: record.state == "closed" and record.closed_date)
        elapsed = [
            (fields.Datetime.to_datetime(record.closed_date) - record.create_date).total_seconds() / 86400
            for record in closed_ncrs
            if record.create_date
        ]
        for dashboard in self:
            dashboard.company_id = company
            dashboard.inspection_count = len(inspections)
            dashboard.passed_count = len(passed)
            dashboard.failed_count = len(failed)
            dashboard.pass_rate = len(passed) * 100.0 / len(completed) if completed else 0.0
            dashboard.open_ncr_count = len(open_ncrs)
            dashboard.open_capa_count = len(open_capas)
            dashboard.overdue_equipment_count = len(due_equipment)
            dashboard.avg_ncr_resolution_days = sum(elapsed) / len(elapsed) if elapsed else 0.0

    def _open_action(self, model, label, domain=None):
        return {
            "type": "ir.actions.act_window",
            "name": label,
            "res_model": model,
            "view_mode": "list,form",
            "domain": domain or [("company_id", "=", self.env.company.id)],
        }

    def action_open_inspections(self):
        return self._open_action("ps.quality.inspection", _("Quality inspections"))

    def action_open_passed(self):
        return self._open_action(
            "ps.quality.inspection", _("Passed inspections"),
            [("company_id", "=", self.env.company.id), ("result", "=", "pass")],
        )

    def action_open_failed(self):
        return self._open_action(
            "ps.quality.inspection", _("Failed inspections"),
            [("company_id", "=", self.env.company.id), ("result", "=", "fail")],
        )

    def action_open_ncr(self):
        return self._open_action("ps.quality.ncr", _("Non-conformance reports"))

    def action_open_capa(self):
        return self._open_action("ps.quality.capa", _("Corrective and preventive actions"))

    def action_open_due_equipment(self):
        return self._open_action(
            "ps.quality.equipment", _("Equipment requiring calibration"),
            [
                ("company_id", "=", self.env.company.id),
                ("calibration_state", "in", ["due", "overdue", "not_calibrated"]),
            ],
        )
