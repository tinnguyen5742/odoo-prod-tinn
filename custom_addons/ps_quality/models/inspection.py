from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class QualityInspection(models.Model):
    _name = "ps.quality.inspection"
    _description = "Quality Inspection"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "inspection_date desc, id desc"

    name = fields.Char(required=True, default="/", copy=False, index=True, tracking=True)
    plan_id = fields.Many2one("ps.quality.plan", tracking=True, index=True)
    standard_id = fields.Many2one(
        "ps.quality.standard", required=True, tracking=True, index=True
    )
    product_id = fields.Many2one("product.product", required=True, tracking=True, index=True)
    partner_id = fields.Many2one("res.partner", string="Supplier / Customer", tracking=True, index=True)
    purchase_order_ref = fields.Reference(
        selection="_selection_purchase_orders", string="Purchase order"
    )
    production_ref = fields.Reference(
        selection="_selection_productions", string="Manufacturing order"
    )
    sale_order_ref = fields.Reference(selection="_selection_sale_orders", string="Sales order")
    picking_ref = fields.Reference(selection="_selection_pickings", string="Inventory transfer")
    lot_ref = fields.Reference(selection="_selection_lots", string="Lot / serial")
    reinspection_of_id = fields.Many2one(
        "ps.quality.inspection", string="Reinspection of", readonly=True, copy=False
    )
    inspection_type = fields.Selection(
        [("iqc", "IQC - Incoming"), ("ipqc", "IPQC - In Process"), ("oqc", "OQC - Outgoing")],
        required=True,
        default="iqc",
        tracking=True,
        index=True,
    )
    inspection_date = fields.Date(
        required=True, default=fields.Date.context_today, tracking=True, index=True
    )
    planned_date = fields.Date(tracking=True, index=True)
    inspector_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, tracking=True, index=True
    )
    quantity_to_inspect = fields.Float(string="Quantity received / produced", digits=(16, 2))
    quantity_sampled = fields.Float(string="Quantity sampled", digits=(16, 2), default=1.0)
    quantity_passed = fields.Float(string="Quantity passed", digits=(16, 2), default=0.0)
    quantity_failed = fields.Float(string="Quantity failed", digits=(16, 2), default=0.0)
    disposition = fields.Selection(
        [
            ("undecided", "Undecided"),
            ("release", "Release to stock / next operation"),
            ("quarantine", "Quarantine"),
            ("return_supplier", "Return to supplier"),
            ("hold", "Hold for review"),
        ],
        default="undecided",
        tracking=True,
    )
    release_refusal_reason = fields.Text(string="Reason for shipment hold / refusal", tracking=True)
    result = fields.Selection(
        [("pending", "Pending"), ("pass", "Passed"), ("fail", "Failed")],
        required=True,
        default="pending",
        tracking=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("in_progress", "In Progress"),
            ("passed", "Passed"),
            ("failed", "Failed"),
            ("approved", "Approved"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="draft",
        tracking=True,
        index=True,
    )
    line_ids = fields.One2many(
        "ps.quality.inspection.line", "inspection_id", string="Inspection results", copy=False
    )
    ncr_ids = fields.One2many(
        "ps.quality.ncr", "inspection_id", string="Non-conformances", copy=False
    )
    ncr_count = fields.Integer(compute="_compute_ncr_count")
    capa_count = fields.Integer(compute="_compute_capa_count")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "ps_quality_inspection_attachment_rel",
        "inspection_id",
        "attachment_id",
        string="Attachments",
        copy=False,
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    description = fields.Html()

    _inspection_reference_unique = models.Constraint(
        "unique(name)", "Quality inspection references must be unique."
    )

    @api.model
    def _selection_purchase_orders(self):
        return [("purchase.order", _("Purchase order"))] if "purchase.order" in self.env.registry.models else []

    @api.model
    def _selection_productions(self):
        return [("mrp.production", _("Manufacturing order"))] if "mrp.production" in self.env.registry.models else []

    @api.model
    def _selection_sale_orders(self):
        return [("sale.order", _("Sales order"))] if "sale.order" in self.env.registry.models else []

    @api.model
    def _selection_pickings(self):
        return [("stock.picking", _("Inventory transfer"))] if "stock.picking" in self.env.registry.models else []

    @api.model
    def _selection_lots(self):
        return [("stock.lot", _("Lot / serial"))] if "stock.lot" in self.env.registry.models else []

    @api.depends("ncr_ids")
    def _compute_ncr_count(self):
        counts = dict(
            self.env["ps.quality.ncr"]._read_group(
                [("inspection_id", "in", self.ids)], ["inspection_id"], ["__count"]
            )
        )
        for inspection in self:
            inspection.ncr_count = counts.get(inspection, 0)

    @api.depends("ncr_ids.capa_ids")
    def _compute_capa_count(self):
        for inspection in self:
            inspection.capa_count = len(inspection.ncr_ids.mapped("capa_ids"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("ps.quality.inspection") or "/"
            if vals.get("plan_id"):
                plan = self.env["ps.quality.plan"].browse(vals["plan_id"])
                vals.setdefault("standard_id", plan.standard_id.id)
                vals.setdefault("product_id", plan.product_id.id)
                vals.setdefault("inspection_type", plan.inspection_type)
                vals.setdefault("inspector_id", plan.inspector_id.id)
                vals.setdefault("company_id", plan.company_id.id)
        records = super().create(vals_list)
        records.message_post(body=_("Quality inspection created."))
        return records

    @api.onchange("plan_id")
    def _onchange_plan_id(self):
        if self.plan_id:
            self.standard_id = self.plan_id.standard_id
            self.product_id = self.plan_id.product_id
            self.inspection_type = self.plan_id.inspection_type
            self.inspector_id = self.plan_id.inspector_id
            self.company_id = self.plan_id.company_id
            self.quantity_sampled = self.plan_id.sample_size

    @api.onchange("purchase_order_ref")
    def _onchange_purchase_order_ref(self):
        order = self.purchase_order_ref
        if order:
            self.partner_id = getattr(order, "partner_id", False)
            lines = getattr(order, "order_line", self.env["product.product"])
            products = lines.mapped("product_id")
            if len(products) == 1:
                self.product_id = products
            if "company_id" in order._fields:
                self.company_id = order.company_id

    @api.onchange("production_ref")
    def _onchange_production_ref(self):
        production = self.production_ref
        if production:
            if "product_id" in production._fields:
                self.product_id = production.product_id
            if "company_id" in production._fields:
                self.company_id = production.company_id

    @api.onchange("sale_order_ref")
    def _onchange_sale_order_ref(self):
        order = self.sale_order_ref
        if order:
            self.partner_id = getattr(order, "partner_id", False)
            lines = getattr(order, "order_line", self.env["product.product"])
            products = lines.mapped("product_id")
            if len(products) == 1:
                self.product_id = products
            if "company_id" in order._fields:
                self.company_id = order.company_id

    @api.onchange("lot_ref")
    def _onchange_lot_ref(self):
        if self.lot_ref and "product_id" in self.lot_ref._fields:
            self.product_id = self.lot_ref.product_id

    @api.constrains(
        "standard_id", "product_id", "plan_id", "company_id", "inspection_type",
        "quantity_to_inspect", "quantity_sampled", "quantity_passed", "quantity_failed",
    )
    def _check_inspection_values(self):
        for inspection in self:
            if inspection.standard_id.product_id != inspection.product_id:
                raise ValidationError(_("The inspection product must match the quality standard."))
            if inspection.standard_id.company_id != inspection.company_id:
                raise ValidationError(_("The inspection and standard must belong to the same company."))
            if inspection.plan_id and (
                inspection.plan_id.product_id != inspection.product_id
                or inspection.plan_id.company_id != inspection.company_id
                or inspection.plan_id.inspection_type != inspection.inspection_type
            ):
                raise ValidationError(_("The inspection must match its plan product, type and company."))
            if min(
                inspection.quantity_to_inspect,
                inspection.quantity_sampled,
                inspection.quantity_passed,
                inspection.quantity_failed,
            ) < 0:
                raise ValidationError(_("Inspection quantities cannot be negative."))
            if inspection.quantity_to_inspect and inspection.quantity_sampled > inspection.quantity_to_inspect:
                raise ValidationError(_("The sample quantity cannot exceed the received / produced quantity."))
            if inspection.quantity_passed + inspection.quantity_failed > inspection.quantity_sampled:
                raise ValidationError(_("Passed and failed quantities cannot exceed the sampled quantity."))

    def write(self, vals):
        vals = dict(vals)
        protected_fields = {
            "standard_id", "product_id", "partner_id", "purchase_order_ref", "production_ref",
            "sale_order_ref", "picking_ref", "lot_ref", "inspection_type", "quantity_to_inspect",
            "quantity_sampled", "inspector_id", "company_id",
        }
        if protected_fields.intersection(vals) and any(
            inspection.state in ("passed", "failed", "approved", "closed", "cancelled")
            for inspection in self
        ):
            raise UserError(_("Inspection setup cannot be changed after completion."))
        if vals.get("state") in ("passed", "failed"):
            if len(self) != 1:
                raise UserError(_("Complete one inspection at a time."))
            expected_result = self._evaluate_results()
            expected_state = "passed" if expected_result == "pass" else "failed"
            if vals["state"] != expected_state:
                raise ValidationError(_("The inspection state must match its measured results."))
            vals["result"] = expected_result
        elif "result" in vals and any(
            inspection.state not in ("draft", "confirmed", "in_progress") for inspection in self
        ):
            raise AccessError(_("Completed inspection results are locked; request a reinspection to test again."))
        if "state" in vals:
            for inspection in self:
                inspection._check_state_transition(vals["state"])
        result = super().write(vals)
        if vals.get("state") == "failed":
            for inspection in self:
                if not inspection.ncr_ids:
                    self.env["ps.quality.ncr"].create(
                        {
                            "inspection_id": inspection.id,
                            "title": _("Non-conformance for %s") % inspection.name,
                            "severity": "major",
                            "source_type": inspection.inspection_type,
                            "product_id": inspection.product_id.id,
                            "partner_id": inspection.partner_id.id,
                            "lot_ref": inspection.lot_ref,
                            "assigned_id": inspection.inspector_id.id,
                            "company_id": inspection.company_id.id,
                        }
                    )
                inspection.message_post(body=_("Inspection failed. A non-conformance report was created."))
        return result

    def _check_state_transition(self, target):
        self.ensure_one()
        is_inspector = self.env.user.has_group("ps_quality.group_quality_inspector")
        is_manager = self.env.user.has_group("ps_quality.group_quality_manager")
        if target == "confirmed":
            if self.state != "draft" or not is_inspector:
                raise AccessError(_("Only a Quality Inspector can confirm a draft inspection."))
            if self.standard_id.state != "active":
                raise UserError(_("The linked quality standard is not active."))
            if not self.inspector_id or self.company_id not in self.inspector_id.company_ids:
                raise ValidationError(_("The assigned inspector must belong to the inspection company."))
            if self.inspector_id != self.env.user and not is_manager:
                raise AccessError(_("Only the assigned inspector or a Quality Manager can confirm this inspection."))
            return
        if target == "in_progress":
            if self.state != "confirmed" or not is_inspector:
                raise AccessError(_("Only a Quality Inspector can start a confirmed inspection."))
            if self.inspector_id != self.env.user and not is_manager:
                raise AccessError(_("Only the assigned inspector or a Quality Manager can start this inspection."))
            return
        if target in ("passed", "failed"):
            if self.state != "in_progress" or not is_inspector:
                raise AccessError(_("Only a Quality Inspector can complete an inspection in progress."))
            expected = self._evaluate_results()
            expected_state = "passed" if expected == "pass" else "failed"
            if self.inspector_id != self.env.user and not is_manager:
                raise AccessError(_("Only the assigned inspector or a Quality Manager can complete this inspection."))
            if target != expected_state:
                raise ValidationError(_("The inspection state must match its measured results."))
            return
        if target == "approved":
            if self.state not in ("passed", "failed") or not is_manager:
                raise AccessError(_("Only a Quality Manager can approve a completed inspection."))
            if self.result == "fail" and any(ncr.state != "closed" for ncr in self.ncr_ids):
                raise UserError(_("Resolve and close all linked NCRs before approving a failed inspection."))
            return
        if target == "closed":
            if self.state != "approved" or not (is_inspector or is_manager):
                raise AccessError(_("Only a Quality Inspector or Manager can close an approved inspection."))
            return
        if target == "cancelled":
            if self.state not in ("draft", "confirmed") or not is_manager:
                raise AccessError(_("Only a Quality Manager can cancel a draft or confirmed inspection."))
            return
        raise AccessError(_("Invalid quality inspection status transition."))

    def _evaluate_results(self):
        self.ensure_one()
        required_lines = self.line_ids.filtered(lambda line: line.standard_line_id.required)
        if not required_lines:
            raise UserError(_("Add inspection criteria before completing the inspection."))
        for line in required_lines:
            criterion_type = line.standard_line_id.criterion_type
            if criterion_type == "numeric":
                if not line.observed_value:
                    raise UserError(_("Enter an observed value for '%s'.") % line.name)
                try:
                    value = float(line.observed_value.replace(",", "."))
                except (TypeError, ValueError):
                    raise ValidationError(_("Observed value for '%s' must be numeric.") % line.name)
                passed = (not line.has_minimum or value >= line.min_value) and (
                    not line.has_maximum or value <= line.max_value
                )
                line.result = "pass" if passed else "fail"
            elif line.result not in ("pass", "fail"):
                raise UserError(_("Choose Pass or Fail for '%s'.") % line.name)
            elif criterion_type == "text" and not line.observed_value:
                raise UserError(_("Enter an observation for '%s'.") % line.name)
        if self.quantity_sampled <= 0:
            raise UserError(_("Sample quantity must be greater than zero."))
        if self.quantity_passed + self.quantity_failed != self.quantity_sampled:
            raise UserError(_("Passed and failed quantities must add up to the sampled quantity."))
        if self.quantity_failed or any(line.result == "fail" for line in required_lines):
            return "fail"
        return "pass"

    def action_confirm(self):
        for inspection in self:
            if not inspection.line_ids:
                inspection.env["ps.quality.inspection.line"].create(
                    [
                        {
                            "inspection_id": inspection.id,
                            "standard_line_id": criterion.id,
                        }
                        for criterion in inspection.standard_id.line_ids
                    ]
                )
            inspection.write({"state": "confirmed"})
        return True

    def action_start(self):
        for inspection in self:
            inspection.write({"state": "in_progress"})
            inspection.message_post(body=_("Inspection started."))
        return True

    def action_complete(self):
        for inspection in self:
            result = inspection._evaluate_results()
            state = "passed" if result == "pass" else "failed"
            inspection.write({"result": result, "state": state})
            inspection.message_post(body=_("Inspection completed with result: %s") % result)
        return True

    def action_approve(self):
        for inspection in self:
            inspection.write({"state": "approved"})
            inspection.message_post(body=_("Inspection result approved."))
        return True

    def action_close(self):
        for inspection in self:
            inspection.write({"state": "closed"})
        return True

    def action_cancel(self):
        for inspection in self:
            inspection.write({"state": "cancelled"})
        return True

    def action_request_reinspection(self):
        self.ensure_one()
        if self.state != "failed":
            raise UserError(_("Reinspection can only be requested for a failed inspection."))
        if not self.env.user.has_group("ps_quality.group_quality_inspector"):
            raise AccessError(_("Only a Quality Inspector can request reinspection."))
        new_inspection = self.copy(
            {
                "name": "/",
                "state": "draft",
                "result": "pending",
                "reinspection_of_id": self.id,
                "inspection_date": fields.Date.context_today(self),
                "quantity_passed": 0,
                "quantity_failed": 0,
                "line_ids": False,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": new_inspection.name,
            "res_model": self._name,
            "res_id": new_inspection.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_create_ncr(self):
        self.ensure_one()
        if self.state != "failed":
            raise UserError(_("An NCR can only be created for a failed inspection."))
        if not self.env.user.has_group("ps_quality.group_quality_inspector"):
            raise AccessError(_("Only a Quality Inspector can create an NCR."))
        ncr = self.ncr_ids[:1]
        if not ncr:
            ncr = self.env["ps.quality.ncr"].create(
                {
                    "inspection_id": self.id,
                    "title": _("Non-conformance for %s") % self.name,
                    "severity": "major",
                    "source_type": self.inspection_type,
                    "product_id": self.product_id.id,
                    "partner_id": self.partner_id.id,
                    "lot_ref": self.lot_ref,
                    "assigned_id": self.inspector_id.id,
                    "company_id": self.company_id.id,
                }
            )
        return {
            "type": "ir.actions.act_window",
            "name": ncr.name,
            "res_model": ncr._name,
            "res_id": ncr.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_ncrs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Non-conformance reports"),
            "res_model": "ps.quality.ncr",
            "view_mode": "list,form",
            "domain": [("inspection_id", "=", self.id)],
            "context": {"default_inspection_id": self.id},
        }

    def action_view_capas(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Corrective and preventive actions"),
            "res_model": "ps.quality.capa",
            "view_mode": "list,form",
            "domain": [("ncr_id", "in", self.ncr_ids.ids)],
        }

    def action_open_source(self):
        self.ensure_one()
        source = self.picking_ref or self.purchase_order_ref or self.production_ref or self.sale_order_ref
        if not source:
            raise UserError(_("This inspection has no linked ERP document."))
        return {
            "type": "ir.actions.act_window",
            "name": source.display_name,
            "res_model": source._name,
            "res_id": source.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_release_outgoing(self):
        self.ensure_one()
        if self.inspection_type != "oqc" or self.result != "pass" or self.state not in ("approved", "closed"):
            raise UserError(_("Only an approved, passed OQC inspection can release an outgoing transfer."))
        if self.disposition != "release":
            raise UserError(_("Set the disposition to Release before authorizing the outgoing transfer."))
        if not self.picking_ref:
            raise UserError(_("Link the outgoing inventory transfer before releasing it."))
        if hasattr(self.picking_ref, "message_post"):
            self.picking_ref.message_post(body=_("Quality approved OQC inspection %s.") % self.name)
        return self.action_open_source()

    def action_refuse_outgoing(self):
        self.ensure_one()
        if self.inspection_type != "oqc":
            raise UserError(_("Shipment hold / refusal applies only to OQC inspections."))
        if self.result != "fail" and self.disposition not in ("quarantine", "return_supplier", "hold"):
            raise UserError(_("Record a failed result or hold / return disposition before refusing shipment."))
        if self.result == "pass" and self.disposition == "release":
            raise UserError(_("A passed OQC marked for release cannot be recorded as refused."))
        if not self.release_refusal_reason:
            raise UserError(_("Enter the reason for holding or refusing shipment."))
        self.message_post(body=_("Outgoing shipment held / refused: %s") % self.release_refusal_reason)
        if self.picking_ref and hasattr(self.picking_ref, "message_post"):
            self.picking_ref.message_post(
                body=_("Shipment held by quality inspection %(inspection)s: %(reason)s")
                % {"inspection": self.name, "reason": self.release_refusal_reason}
            )
        return self.action_open_source() if self.picking_ref else True


class QualityInspectionLine(models.Model):
    _name = "ps.quality.inspection.line"
    _description = "Quality Inspection Result Line"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    inspection_id = fields.Many2one(
        "ps.quality.inspection", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        "res.company", related="inspection_id.company_id", store=True, index=True
    )
    standard_line_id = fields.Many2one(
        "ps.quality.standard.line", required=True, ondelete="restrict"
    )
    name = fields.Char(related="standard_line_id.name", store=True, readonly=True)
    criterion_type = fields.Selection(related="standard_line_id.criterion_type", readonly=True)
    min_value = fields.Float(related="standard_line_id.min_value", readonly=True)
    has_minimum = fields.Boolean(related="standard_line_id.has_minimum", readonly=True)
    max_value = fields.Float(related="standard_line_id.max_value", readonly=True)
    has_maximum = fields.Boolean(related="standard_line_id.has_maximum", readonly=True)
    unit = fields.Char(related="standard_line_id.unit", readonly=True)
    method = fields.Selection(related="standard_line_id.method", readonly=True)
    observed_value = fields.Char(string="Observed value")
    result = fields.Selection(
        [("pending", "Pending"), ("pass", "Pass"), ("fail", "Fail")],
        required=True,
        default="pending",
    )
    remarks = fields.Text()

    _inspection_criterion_unique = models.Constraint(
        "unique(inspection_id, standard_line_id)",
        "A criterion can only appear once on an inspection.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        inspections = self.env["ps.quality.inspection"].browse(
            [vals.get("inspection_id") for vals in vals_list if vals.get("inspection_id")]
        )
        is_manager = self.env.user.has_group("ps_quality.group_quality_manager")
        for inspection in inspections:
            if inspection.state != "draft":
                raise UserError(_("Inspection criteria can only be generated while the inspection is draft."))
            if not is_manager and self.env.user not in (inspection.create_uid, inspection.inspector_id):
                raise AccessError(_("Only the inspection creator, assigned inspector or a Quality Manager can edit its criteria."))
        return super().create(vals_list)

    def write(self, vals):
        is_manager = self.env.user.has_group("ps_quality.group_quality_manager")
        for line in self:
            inspection = line.inspection_id
            if inspection.state not in ("draft", "confirmed", "in_progress"):
                raise UserError(_("Results cannot be changed after the inspection has been completed."))
            if not is_manager and self.env.user != inspection.inspector_id:
                if inspection.state != "draft" or self.env.user != inspection.create_uid:
                    raise AccessError(_("Only the assigned inspector or a Quality Manager can enter inspection results."))
        if "standard_line_id" in vals:
            raise AccessError(_("An inspection criterion cannot be replaced after it is created."))
        return super().write(vals)

    def unlink(self):
        is_manager = self.env.user.has_group("ps_quality.group_quality_manager")
        for line in self:
            if line.inspection_id.state != "draft":
                raise UserError(_("Inspection criteria can only be removed while the inspection is draft."))
            if not is_manager and self.env.user not in (
                line.inspection_id.create_uid, line.inspection_id.inspector_id
            ):
                raise AccessError(_("Only the inspection creator, assigned inspector or a Quality Manager can remove its criteria."))
        return super().unlink()
