from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class AppointmentDashboard(models.TransientModel):
    _name = "ps.appointment.dashboard"
    _description = "Appointment Management Dashboard"

    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    date_from = fields.Date(default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(default=fields.Date.context_today)
    appointment_count = fields.Integer(compute="_compute_metrics")
    requested_count = fields.Integer(compute="_compute_metrics")
    confirmed_count = fields.Integer(compute="_compute_metrics")
    completed_count = fields.Integer(compute="_compute_metrics")
    cancelled_count = fields.Integer(compute="_compute_metrics")
    no_show_count = fields.Integer(compute="_compute_metrics")
    no_show_rate = fields.Float(compute="_compute_metrics", digits=(6, 2))
    resource_utilization = fields.Float(compute="_compute_metrics", digits=(6, 2))

    @api.depends("company_id", "date_from", "date_to")
    def _compute_metrics(self):
        for dashboard in self:
            if not dashboard.company_id or not dashboard.date_from or not dashboard.date_to:
                for field_name in (
                    "appointment_count", "requested_count", "confirmed_count", "completed_count",
                    "cancelled_count", "no_show_count", "no_show_rate", "resource_utilization",
                ):
                    dashboard[field_name] = 0
                continue
            domain = [
                ("company_id", "=", dashboard.company_id.id),
                ("start_datetime", ">=", fields.Datetime.to_datetime(dashboard.date_from)),
                ("start_datetime", "<", fields.Datetime.to_datetime(dashboard.date_to) + timedelta(days=1)),
            ]
            appointments = self.env["ps.appointment"].search(domain)
            no_show = appointments.filtered(lambda item: item.state == "no_show")
            completed_or_past = appointments.filtered(lambda item: item.state in ("done", "no_show"))
            slots = self.env["ps.appointment.slot"].search(
                [
                    ("company_id", "=", dashboard.company_id.id),
                    ("start_datetime", ">=", fields.Datetime.to_datetime(dashboard.date_from)),
                    ("start_datetime", "<", fields.Datetime.to_datetime(dashboard.date_to) + timedelta(days=1)),
                ]
            )
            booked_slots = slots.filtered(lambda item: item.state == "booked")
            dashboard.appointment_count = len(appointments)
            dashboard.requested_count = len(appointments.filtered(lambda item: item.state == "requested"))
            dashboard.confirmed_count = len(appointments.filtered(lambda item: item.state == "confirmed"))
            dashboard.completed_count = len(appointments.filtered(lambda item: item.state == "done"))
            dashboard.cancelled_count = len(appointments.filtered(lambda item: item.state == "cancelled"))
            dashboard.no_show_count = len(no_show)
            dashboard.no_show_rate = len(no_show) * 100.0 / len(completed_or_past) if completed_or_past else 0.0
            dashboard.resource_utilization = len(booked_slots) * 100.0 / len(slots) if slots else 0.0

    def _open(self, label, states=None):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("start_datetime", ">=", fields.Datetime.to_datetime(self.date_from)),
            ("start_datetime", "<", fields.Datetime.to_datetime(self.date_to) + timedelta(days=1)),
        ]
        if states:
            domain.append(("state", "in", states))
        return {
            "type": "ir.actions.act_window",
            "name": label,
            "res_model": "ps.appointment",
            "view_mode": "list,calendar,kanban,form",
            "domain": domain,
        }

    def action_open_all(self):
        return self._open(_("Appointments"))

    def action_open_requested(self):
        return self._open(_("Requested appointments"), ["requested"])

    def action_open_confirmed(self):
        return self._open(_("Confirmed appointments"), ["confirmed"])

    def action_open_completed(self):
        return self._open(_("Completed appointments"), ["done"])

    def action_open_cancelled(self):
        return self._open(_("Cancelled appointments"), ["cancelled"])

    def action_open_no_show(self):
        return self._open(_("No-show appointments"), ["no_show"])

    def action_new_appointment(self):
        if not self.env.user.has_group("ps_appointment.group_appointment_user"):
            raise AccessError(_("You are not allowed to create appointments."))
        return {
            "type": "ir.actions.act_window",
            "name": _("New Appointment"),
            "res_model": "ps.appointment",
            "view_mode": "form",
            "target": "current",
            "context": {"default_company_id": self.env.company.id},
        }

    def action_new_type(self):
        if not self.env.user.has_group("ps_appointment.group_appointment_administrator"):
            raise AccessError(_("Only an Appointment Administrator can create service types."))
        return {
            "type": "ir.actions.act_window",
            "name": _("New Appointment Service Type"),
            "res_model": "ps.appointment.type",
            "view_mode": "form",
            "target": "current",
        }
