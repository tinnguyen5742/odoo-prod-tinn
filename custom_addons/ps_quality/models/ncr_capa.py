from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class QualityNCR(models.Model):
    _name = "ps.quality.ncr"
    _description = "Quality Non-Conformance Report"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, default="/", copy=False, index=True, tracking=True)
    title = fields.Char(required=True, tracking=True, index=True)
    inspection_id = fields.Many2one("ps.quality.inspection", tracking=True, index=True)
    product_id = fields.Many2one("product.product", tracking=True, index=True)
    partner_id = fields.Many2one("res.partner", string="Supplier / Customer", tracking=True)
    lot_ref = fields.Reference(selection="_selection_lots", string="Lot / serial")
    source_type = fields.Selection(
        [
            ("iqc", "Incoming inspection"),
            ("ipqc", "In-process inspection"),
            ("oqc", "Outgoing inspection"),
            ("supplier", "Supplier"),
            ("customer", "Customer"),
            ("equipment", "Measurement equipment"),
            ("other", "Other"),
        ],
        required=True,
        default="other",
        tracking=True,
        index=True,
    )
    severity = fields.Selection(
        [("minor", "Minor"), ("major", "Major"), ("critical", "Critical")],
        required=True,
        default="minor",
        tracking=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("new", "New"),
            ("analysis", "Under Analysis"),
            ("action", "Action Planned"),
            ("verification", "Verification"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="new",
        tracking=True,
        index=True,
    )
    root_cause = fields.Html(tracking=True)
    containment_action = fields.Html(tracking=True)
    disposition = fields.Selection(
        [
            ("rework", "Rework"),
            ("repair", "Repair"),
            ("scrap", "Scrap"),
            ("return", "Return to supplier"),
            ("use_as_is", "Use as is with approval"),
            ("other", "Other"),
        ],
        tracking=True,
    )
    assigned_id = fields.Many2one("res.users", string="Owner", tracking=True, index=True)
    due_date = fields.Date(tracking=True, index=True)
    capa_ids = fields.One2many("ps.quality.capa", "ncr_id", string="CAPA actions")
    capa_count = fields.Integer(compute="_compute_capa_count")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "ps_quality_ncr_attachment_rel",
        "ncr_id",
        "attachment_id",
        string="Attachments",
        copy=False,
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    description = fields.Html()
    closed_date = fields.Datetime(readonly=True, copy=False)

    @api.model
    def _selection_lots(self):
        return [("stock.lot", _("Lot / serial"))] if "stock.lot" in self.env.registry.models else []

    @api.depends("capa_ids")
    def _compute_capa_count(self):
        for ncr in self:
            ncr.capa_count = len(ncr.capa_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("ps.quality.ncr") or "/"
            if vals.get("inspection_id"):
                inspection = self.env["ps.quality.inspection"].browse(vals["inspection_id"])
                vals.setdefault("product_id", inspection.product_id.id)
                vals.setdefault("partner_id", inspection.partner_id.id)
                vals.setdefault("lot_ref", inspection.lot_ref)
                vals.setdefault("source_type", inspection.inspection_type)
                vals.setdefault("assigned_id", inspection.inspector_id.id)
                vals.setdefault("company_id", inspection.company_id.id)
        records = super().create(vals_list)
        records.message_post(body=_("Non-conformance report created."))
        return records

    @api.constrains("inspection_id", "company_id", "product_id", "due_date")
    def _check_ncr_consistency(self):
        for ncr in self:
            if ncr.inspection_id and ncr.inspection_id.company_id != ncr.company_id:
                raise ValidationError(_("The NCR and inspection must belong to the same company."))
            if ncr.inspection_id and ncr.product_id != ncr.inspection_id.product_id:
                raise ValidationError(_("The NCR product must match the linked inspection."))

    def write(self, vals):
        vals = dict(vals)
        protected_fields = {"inspection_id", "product_id", "partner_id", "lot_ref", "source_type", "company_id"}
        if protected_fields.intersection(vals) and any(ncr.state != "new" for ncr in self):
            raise UserError(_("NCR source information cannot be changed after analysis starts."))
        analysis_fields = {"root_cause", "containment_action", "disposition", "assigned_id", "due_date"}
        if analysis_fields.intersection(vals) and any(ncr.state in ("verification", "closed", "cancelled") for ncr in self):
            raise UserError(_("NCR analysis cannot be changed during verification or after closure."))
        if "state" in vals:
            for ncr in self:
                ncr._check_state_transition(vals["state"])
            if vals["state"] == "closed":
                vals["closed_date"] = fields.Datetime.now()
        if "closed_date" in vals and vals.get("state") != "closed":
            raise AccessError(_("The NCR close date is set by the close action."))
        return super().write(vals)

    def _check_state_transition(self, target):
        self.ensure_one()
        is_inspector = self.env.user.has_group("ps_quality.group_quality_inspector")
        is_manager = self.env.user.has_group("ps_quality.group_quality_manager")
        transitions = {
            "analysis": (self.state == "new" and is_inspector),
            "action": (self.state == "analysis" and is_manager),
            "verification": (self.state == "action" and is_inspector),
            "closed": (self.state == "verification" and is_manager),
            "cancelled": (self.state in ("new", "analysis") and is_manager),
        }
        if not transitions.get(target, False):
            raise AccessError(_("This user or NCR status is not allowed to perform that transition."))
        if target == "action" and not (self.root_cause and self.containment_action and self.disposition):
            raise UserError(_("Enter the root cause, containment action and disposition before planning actions."))
        if target == "verification" and any(capa.state != "closed" for capa in self.capa_ids):
            raise UserError(_("Close all linked CAPA actions before NCR verification."))
        if target == "closed" and (not self.root_cause or any(capa.state != "closed" for capa in self.capa_ids)):
            raise UserError(_("An NCR can close only after root cause and all CAPA actions are complete."))

    def action_start_analysis(self):
        for ncr in self:
            ncr.write({"state": "analysis"})
        return True

    def action_plan_actions(self):
        for ncr in self:
            ncr.write({"state": "action"})
        return True

    def action_verify(self):
        for ncr in self:
            ncr.write({"state": "verification"})
        return True

    def action_close(self):
        for ncr in self:
            ncr.write({"state": "closed"})
            ncr.message_post(body=_("NCR closed after verification."))
        return True

    def action_cancel(self):
        for ncr in self:
            ncr.write({"state": "cancelled"})
        return True

    def action_create_capa(self):
        self.ensure_one()
        if not self.env.user.has_group("ps_quality.group_quality_manager"):
            raise AccessError(_("Only a Quality Manager can create CAPA actions."))
        if self.state not in ("analysis", "action"):
            raise UserError(_("Plan the NCR before creating CAPA actions."))
        capa = self.env["ps.quality.capa"].create(
            {
                "ncr_id": self.id,
                "action_type": "corrective",
                "assigned_id": self.assigned_id.id or self.env.user.id,
                "company_id": self.company_id.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": capa.name,
            "res_model": capa._name,
            "res_id": capa.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_inspection(self):
        self.ensure_one()
        if not self.inspection_id:
            raise UserError(_("This NCR is not linked to an inspection."))
        return {
            "type": "ir.actions.act_window",
            "name": self.inspection_id.name,
            "res_model": self.inspection_id._name,
            "res_id": self.inspection_id.id,
            "view_mode": "form",
            "target": "current",
        }


class QualityCAPA(models.Model):
    _name = "ps.quality.capa"
    _description = "Quality Corrective and Preventive Action"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "due_date, id desc"

    name = fields.Char(required=True, default="/", copy=False, index=True, tracking=True)
    ncr_id = fields.Many2one(
        "ps.quality.ncr", required=True, ondelete="restrict", tracking=True, index=True
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    action_type = fields.Selection(
        [("corrective", "Corrective"), ("preventive", "Preventive"), ("both", "Corrective and Preventive")],
        required=True,
        default="both",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "In Progress"),
            ("verification", "Effectiveness Review"),
            ("effective", "Effective"),
            ("ineffective", "Ineffective"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="draft",
        tracking=True,
        index=True,
    )
    root_cause = fields.Html(tracking=True)
    corrective_action = fields.Html(tracking=True)
    preventive_action = fields.Html(tracking=True)
    assigned_id = fields.Many2one("res.users", required=True, string="Owner", tracking=True)
    due_date = fields.Date(required=True, tracking=True, index=True)
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "ps_quality_capa_evidence_rel",
        "capa_id",
        "attachment_id",
        string="Evidence",
        copy=False,
    )
    effectiveness_result = fields.Selection(
        [("pending", "Pending"), ("effective", "Effective"), ("ineffective", "Ineffective")],
        default="pending",
        tracking=True,
    )
    effectiveness_note = fields.Html(tracking=True)
    evaluated_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    evaluated_date = fields.Datetime(readonly=True, copy=False)
    closed_date = fields.Datetime(readonly=True, copy=False)
    description = fields.Html()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("ps.quality.capa") or "/"
            if vals.get("ncr_id"):
                ncr = self.env["ps.quality.ncr"].browse(vals["ncr_id"])
                vals.setdefault("company_id", ncr.company_id.id)
                vals.setdefault("root_cause", ncr.root_cause)
            vals.setdefault("due_date", fields.Date.context_today(self) + timedelta(days=14))
        return super().create(vals_list)

    @api.constrains("ncr_id", "company_id", "due_date", "assigned_id")
    def _check_capa_values(self):
        for capa in self:
            if capa.company_id != capa.ncr_id.company_id:
                raise ValidationError(_("The CAPA and NCR must belong to the same company."))
            if capa.assigned_id.company_id and capa.assigned_id.company_id != capa.company_id:
                raise ValidationError(_("The CAPA owner must belong to the CAPA company."))

    def write(self, vals):
        vals = dict(vals)
        if "effectiveness_result" in vals and any(
            capa.state != "verification"
            and not (vals.get("state") == "open" and capa.state == "ineffective")
            for capa in self
        ):
            raise UserError(_("Effectiveness can only be recorded during the review stage."))
        if "effectiveness_note" in vals and any(
            capa.state != "verification"
            and not (vals.get("state") == "open" and capa.state == "ineffective")
            for capa in self
        ):
            raise UserError(_("The effectiveness review note can only be edited during the review stage."))
        action_fields = {
            "ncr_id", "action_type", "root_cause", "corrective_action", "preventive_action",
            "assigned_id", "due_date", "company_id",
        }
        if action_fields.intersection(vals) and any(capa.state not in ("draft", "open") for capa in self):
            raise UserError(_("CAPA action details are locked during review and after evaluation."))
        if "evidence_attachment_ids" in vals and any(capa.state in ("closed", "cancelled") for capa in self):
            raise UserError(_("Evidence is locked after CAPA closure or cancellation."))
        if {"evaluated_by_id", "evaluated_date", "closed_date"}.intersection(vals) and "state" not in vals:
            raise AccessError(_("CAPA evaluation and closure dates are managed by workflow actions."))
        if "state" in vals:
            for capa in self:
                capa._check_state_transition(vals["state"])
            if vals["state"] in ("effective", "ineffective"):
                vals.update(
                    {
                        "evaluated_by_id": self.env.user.id,
                        "evaluated_date": fields.Datetime.now(),
                    }
                )
            elif vals["state"] == "closed":
                vals["closed_date"] = fields.Datetime.now()
        return super().write(vals)

    def _check_state_transition(self, target):
        self.ensure_one()
        is_inspector = self.env.user.has_group("ps_quality.group_quality_inspector")
        is_manager = self.env.user.has_group("ps_quality.group_quality_manager")
        transitions = {
            "open": (self.state == "draft" and (is_inspector or is_manager)),
            "open_after_ineffective": (self.state == "ineffective" and (is_inspector or is_manager)),
            "verification": (self.state == "open" and (is_inspector or is_manager)),
            "effective": (self.state == "verification" and is_manager and self.effectiveness_result == "effective"),
            "ineffective": (self.state == "verification" and is_manager and self.effectiveness_result == "ineffective"),
            "closed": (self.state == "effective" and is_manager),
            "cancelled": (self.state in ("draft", "open") and is_manager),
        }
        allowed = transitions.get(target, False)
        if target == "open":
            allowed = transitions["open"] or transitions["open_after_ineffective"]
        if not allowed:
            raise AccessError(_("This user or CAPA status is not allowed to perform that transition."))
        if target == "open":
            if not self.root_cause:
                raise UserError(_("Enter the root cause before starting CAPA."))
            if self.action_type in ("corrective", "both") and not self.corrective_action:
                raise UserError(_("Enter the corrective action before starting CAPA."))
            if self.action_type in ("preventive", "both") and not self.preventive_action:
                raise UserError(_("Enter the preventive action before starting CAPA."))
        if target == "verification" and not self.evidence_attachment_ids:
            raise UserError(_("Attach evidence before submitting CAPA for effectiveness review."))
        if target in ("effective", "ineffective") and not self.effectiveness_note:
            raise UserError(_("Record the effectiveness evaluation before completing the review."))

    def action_start(self):
        for capa in self:
            values = {"state": "open"}
            if capa.state == "ineffective":
                values.update(
                    {
                        "effectiveness_result": "pending",
                        "effectiveness_note": False,
                        "evaluated_by_id": False,
                        "evaluated_date": False,
                    }
                )
            capa.write(values)
        return True

    def action_submit_effectiveness(self):
        for capa in self:
            capa.write({"state": "verification"})
        return True

    def action_evaluate_effectiveness(self):
        for capa in self:
            if capa.effectiveness_result not in ("effective", "ineffective"):
                raise UserError(_("Choose whether the action was effective or ineffective."))
            capa.write({"state": capa.effectiveness_result})
        return True

    def action_close(self):
        for capa in self:
            capa.write({"state": "closed"})
        return True

    def action_cancel(self):
        for capa in self:
            capa.write({"state": "cancelled"})
        return True

    def action_open_ncr(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.ncr_id.name,
            "res_model": self.ncr_id._name,
            "res_id": self.ncr_id.id,
            "view_mode": "form",
            "target": "current",
        }
