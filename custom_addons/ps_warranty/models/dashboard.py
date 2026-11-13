from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class WarrantyDashboard(models.TransientModel):
    _name = "ps.warranty.dashboard"
    _description = "Warranty Management Dashboard"

    registration_count = fields.Integer(compute="_compute_counts")
    active_registration_count = fields.Integer(compute="_compute_counts")
    expired_registration_count = fields.Integer(compute="_compute_counts")
    claim_count = fields.Integer(compute="_compute_counts")
    waiting_claim_count = fields.Integer(compute="_compute_counts")
    approved_claim_count = fields.Integer(compute="_compute_counts")
    rejected_claim_count = fields.Integer(compute="_compute_counts")
    warranty_cost = fields.Monetary(compute="_compute_counts", currency_field="currency_id")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)

    def _new_record_action(self, model_name, label):
        return {
            "type": "ir.actions.act_window",
            "name": label,
            "res_model": model_name,
            "view_mode": "form",
            "target": "current",
            "context": dict(self.env.context, default_company_id=self.env.company.id),
        }

    def action_new_claim(self):
        if not self.env.user.has_group("ps_warranty.group_warranty_user"):
            raise AccessError(_("You are not allowed to create warranty claims."))
        return self._new_record_action("ps.warranty.claim", _("New warranty claim"))

    def action_new_registration(self):
        if not self.env.user.has_group("ps_warranty.group_warranty_officer"):
            raise AccessError(_("Only warranty officers can create registrations."))
        return self._new_record_action(
            "ps.warranty.registration", _("New warranty registration")
        )

    def action_new_rma(self):
        if not self.env.user.has_group("ps_warranty.group_warranty_officer"):
            raise AccessError(_("Only warranty officers can create RMAs."))
        return self._new_record_action("ps.warranty.rma", _("New RMA"))

    def action_new_policy(self):
        if not self.env.user.has_group("ps_warranty.group_warranty_manager"):
            raise AccessError(_("Only warranty managers can create policies."))
        return self._new_record_action("ps.warranty.policy", _("New warranty policy"))

    @api.depends_context("uid", "company")
    def _compute_counts(self):
        Registration = self.env["ps.warranty.registration"]
        Claim = self.env["ps.warranty.claim"]
        for dashboard in self:
            company_domain = [("company_id", "=", self.env.company.id)]
            dashboard.registration_count = Registration.search_count(company_domain)
            dashboard.active_registration_count = Registration.search_count(
                company_domain + [("state", "=", "active")]
            )
            dashboard.expired_registration_count = Registration.search_count(
                company_domain + [("state", "=", "expired")]
            )
            dashboard.claim_count = Claim.search_count(company_domain)
            dashboard.waiting_claim_count = Claim.search_count(
                company_domain
                + [("state", "in", ["submitted", "under_review", "approved", "in_progress"])]
            )
            dashboard.approved_claim_count = Claim.search_count(
                company_domain
                + [("state", "in", ["approved", "in_progress", "resolved", "closed"])]
            )
            dashboard.rejected_claim_count = Claim.search_count(
                company_domain + [("state", "=", "rejected")]
            )
            claims = Claim.search(company_domain)
            dashboard.warranty_cost = sum(claims.mapped("cost_total"))
            dashboard.currency_id = self.env.company.currency_id

    def action_open_registrations(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Warranty registrations"),
            "res_model": "ps.warranty.registration",
            "view_mode": "list,form",
            "domain": [("company_id", "=", self.env.company.id)],
        }

    def action_open_active_registrations(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Active warranties"),
            "res_model": "ps.warranty.registration",
            "view_mode": "list,form",
            "domain": [("state", "=", "active"), ("company_id", "=", self.env.company.id)],
        }

    def action_open_expired_registrations(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Expired warranties"),
            "res_model": "ps.warranty.registration",
            "view_mode": "list,form",
            "domain": [("state", "=", "expired"), ("company_id", "=", self.env.company.id)],
        }

    def action_open_claims(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Warranty claims"),
            "res_model": "ps.warranty.claim",
            "view_mode": "kanban,list,form",
            "domain": [("company_id", "=", self.env.company.id)],
        }

    def action_open_waiting_claims(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Claims in process"),
            "res_model": "ps.warranty.claim",
            "view_mode": "kanban,list,form",
            "domain": [
                ("state", "in", ["submitted", "under_review", "approved", "in_progress"]),
                ("company_id", "=", self.env.company.id),
            ],
        }

    def action_open_rejected_claims(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Rejected claims"),
            "res_model": "ps.warranty.claim",
            "view_mode": "list,form",
            "domain": [("state", "=", "rejected"), ("company_id", "=", self.env.company.id)],
        }
