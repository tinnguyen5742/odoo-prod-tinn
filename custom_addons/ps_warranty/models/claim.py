from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class WarrantyClaim(models.Model):
    _name = "ps.warranty.claim"
    _description = "Warranty Claim"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "claim_date desc, id desc"

    name = fields.Char(string="Claim reference", required=True, default="/", copy=False, index=True)
    registration_id = fields.Many2one(
        "ps.warranty.registration", string="Warranty registration", tracking=True, index=True
    )
    partner_id = fields.Many2one(
        "res.partner", string="Customer", required=True, tracking=True, index=True
    )
    product_id = fields.Many2one(
        "product.product", string="Product", required=True, tracking=True, index=True
    )
    serial_number = fields.Char(string="Serial number", tracking=True, index=True)
    lot_ref = fields.Reference(
        selection="_selection_lot_models", string="Inventory lot / serial record"
    )
    policy_id = fields.Many2one(
        "ps.warranty.policy", related="registration_id.policy_id", store=True, readonly=True
    )
    source_ref = fields.Reference(
        selection="_selection_order_models", string="Sales / purchase order"
    )
    document_ref = fields.Reference(
        selection="_selection_document_models", string="Warranty document"
    )
    fsm_task_ref = fields.Reference(
        selection="_selection_fsm_models", string="Field Service task", readonly=True
    )
    replacement_delivery_ref = fields.Reference(
        selection="_selection_picking_models", string="Replacement delivery", readonly=True
    )
    fsm_available = fields.Boolean(compute="_compute_optional_integrations")
    inventory_available = fields.Boolean(compute="_compute_optional_integrations")
    claim_date = fields.Date(
        string="Claim date", required=True, default=fields.Date.context_today, tracking=True, index=True
    )
    description = fields.Html(string="Reported problem", required=True)
    priority = fields.Selection(
        [("0", "Normal"), ("1", "High"), ("2", "Urgent")],
        string="Priority",
        default="0",
        tracking=True,
    )
    user_id = fields.Many2one(
        "res.users", string="Responsible", default=lambda self: self.env.user, tracking=True
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("under_review", "Under Review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("in_progress", "In Progress"),
            ("resolved", "Resolved"),
            ("closed", "Closed"),
        ],
        string="Status",
        required=True,
        default="draft",
        tracking=True,
        index=True,
    )
    eligibility = fields.Selection(
        [
            ("unregistered", "No registration"),
            ("covered", "Covered"),
            ("expired", "Warranty expired"),
            ("cancelled", "Registration cancelled"),
            ("draft", "Registration not active"),
        ],
        string="Warranty eligibility",
        compute="_compute_eligibility",
    )
    coverage_type = fields.Selection(related="policy_id.coverage_type", string="Coverage type")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "ps_warranty_claim_attachment_rel",
        "claim_id",
        "attachment_id",
        string="Attachments",
        copy=False,
    )
    line_ids = fields.One2many("ps.warranty.claim.line", "claim_id", string="Repair / replacement lines")
    rma_ids = fields.One2many("ps.warranty.rma", "claim_id", string="RMA records")
    rma_count = fields.Integer(compute="_compute_rma_count")
    review_note = fields.Text(string="Review note / rejection reason", tracking=True)
    approved_by_id = fields.Many2one("res.users", string="Approved by", readonly=True, copy=False)
    approved_date = fields.Datetime(string="Approval date", readonly=True, copy=False)
    resolution_note = fields.Html(string="Resolution details", tracking=True)
    resolved_date = fields.Datetime(string="Resolved at", readonly=True, copy=False)
    closed_date = fields.Datetime(string="Closed at", readonly=True, copy=False)
    resolution_days = fields.Integer(compute="_compute_resolution_days", store=True)
    cost_total = fields.Monetary(
        string="Warranty cost", compute="_compute_cost_total", store=True, currency_field="currency_id"
    )
    currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", store=True, readonly=True
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )

    _claim_reference_unique = models.Constraint(
        "unique(name)", "Warranty claim references must be unique."
    )

    @api.depends_context("uid")
    def _compute_optional_integrations(self):
        fsm_available = (
            "project.task" in self.env.registry.models
            and "is_fsm" in self.env["project.task"]._fields
        )
        inventory_available = "stock.picking" in self.env.registry.models
        for claim in self:
            claim.fsm_available = fsm_available
            claim.inventory_available = inventory_available

    @api.model
    def _selection_lot_models(self):
        if "stock.lot" in self.env.registry.models:
            return [("stock.lot", _("Inventory lot / serial"))]
        return []

    @api.model
    def _selection_order_models(self):
        return [
            (model_name, label)
            for model_name, label in [
                ("sale.order", _("Sales order")),
                ("purchase.order", _("Purchase order")),
            ]
            if model_name in self.env.registry.models
        ]

    @api.model
    def _selection_document_models(self):
        if "documents.document" in self.env.registry.models:
            return [("documents.document", _("Documents record"))]
        return []

    @api.model
    def _selection_fsm_models(self):
        if (
            "project.task" in self.env.registry.models
            and "is_fsm" in self.env["project.task"]._fields
        ):
            return [("project.task", _("Field Service task"))]
        return []

    @api.model
    def _selection_picking_models(self):
        if "stock.picking" in self.env.registry.models:
            return [("stock.picking", _("Stock transfer"))]
        return []

    @api.depends("registration_id", "registration_id.state", "registration_id.end_date", "claim_date")
    def _compute_eligibility(self):
        today = fields.Date.context_today(self)
        for claim in self:
            registration = claim.registration_id
            if not registration:
                claim.eligibility = "unregistered"
            elif registration.state == "cancelled":
                claim.eligibility = "cancelled"
            elif registration.state == "draft":
                claim.eligibility = "draft"
            elif registration.end_date and registration.end_date < (claim.claim_date or today):
                claim.eligibility = "expired"
            elif registration.state == "active" and registration.end_date >= (claim.claim_date or today):
                claim.eligibility = "covered"
            else:
                claim.eligibility = "expired"

    @api.depends("line_ids.subtotal")
    def _compute_cost_total(self):
        for claim in self:
            claim.cost_total = sum(claim.line_ids.mapped("subtotal"))

    @api.depends("claim_date", "resolved_date")
    def _compute_resolution_days(self):
        for claim in self:
            claim.resolution_days = (
                (fields.Datetime.to_datetime(claim.resolved_date).date() - claim.claim_date).days
                if claim.resolved_date and claim.claim_date
                else 0
            )

    @api.depends("rma_ids")
    def _compute_rma_count(self):
        counts = dict(
            self.env["ps.warranty.rma"]._read_group(
                [("claim_id", "in", self.ids)], ["claim_id"], ["__count"]
            )
        )
        for claim in self:
            claim.rma_count = counts.get(claim, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals["state"] = "draft"
            vals["approved_by_id"] = False
            vals["approved_date"] = False
            vals["resolved_date"] = False
            vals["closed_date"] = False
            if not vals.get("name") or vals["name"] == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("ps.warranty.claim") or "/"
        claims = super().create(vals_list)
        claims.message_post(body=_("Warranty claim created."))
        claims.mapped("registration_id").sudo().message_post(
            body=_("A warranty claim was created for this registration.")
        )
        return claims

    def write(self, vals):
        vals = dict(vals)
        if "state" in vals:
            for claim in self:
                claim._check_workflow_transition(vals["state"], vals)
            if vals["state"] == "under_review":
                vals["user_id"] = self.env.user.id
            elif vals["state"] == "approved":
                approver_id = vals.get("approved_by_id", self.env.user.id)
                if approver_id != self.env.user.id:
                    raise AccessError(_("The approving user must be the current user."))
                vals["approved_by_id"] = self.env.user.id
                vals["approved_date"] = fields.Datetime.now()
            elif vals["state"] == "resolved":
                vals["resolved_date"] = fields.Datetime.now()
            elif vals["state"] == "closed":
                vals["closed_date"] = fields.Datetime.now()
        if "approved_by_id" in vals and not self.env.user.has_group(
            "ps_warranty.group_warranty_manager"
        ):
            raise AccessError(_("Only warranty managers can set approval details."))
        if "approved_by_id" in vals and (
            vals.get("state") != "approved" or vals["approved_by_id"] != self.env.user.id
        ):
            raise AccessError(_("Approval details must match the current approval transition."))
        if "approved_date" in vals and vals.get("state") != "approved":
            raise AccessError(_("Approval date can only be recorded when a claim is approved."))
        if "resolved_date" in vals and vals.get("state") != "resolved":
            raise AccessError(_("Resolution date can only be recorded when a claim is resolved."))
        if "closed_date" in vals and vals.get("state") != "closed":
            raise AccessError(_("Close date can only be recorded when a claim is closed."))
        result = super().write(vals)
        if vals.get("state") == "submitted":
            for claim in self:
                claim.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=claim.user_id.id or self.env.user.id,
                    date_deadline=fields.Date.context_today(claim),
                    summary=_("Warranty claim review"),
                    note=_("Review the submitted claim %s.") % claim.name,
                )
        return result

    def _check_workflow_transition(self, target, incoming_values=None):
        self.ensure_one()
        incoming_values = incoming_values or {}
        is_user = self.env.user.has_group("ps_warranty.group_warranty_user")
        is_officer = self.env.user.has_group("ps_warranty.group_warranty_officer")
        is_manager = self.env.user.has_group("ps_warranty.group_warranty_manager")
        transitions = {
            "submitted": (self.state in ("draft", "rejected") and is_user),
            "under_review": (self.state == "submitted" and is_officer),
            "approved": (self.state == "under_review" and is_manager),
            "rejected": (self.state == "under_review" and is_manager),
            "in_progress": (self.state == "approved" and is_officer),
            "resolved": (self.state == "in_progress" and is_officer),
            "closed": (self.state == "resolved" and (is_officer or is_manager)),
        }
        if not transitions.get(target, False):
            raise AccessError(_("This user or claim status is not allowed to perform that transition."))
        if target == "submitted":
            self._check_warranty_eligibility()
        if target == "rejected" and not (
            self.review_note or incoming_values.get("review_note")
        ):
            raise UserError(_("Enter a reason before rejecting the claim."))
        if target == "resolved" and not (
            self.resolution_note or incoming_values.get("resolution_note")
        ):
            raise UserError(_("Enter resolution details before resolving the claim."))

    def _check_warranty_eligibility(self):
        self.ensure_one()
        registration = self.registration_id
        if not registration:
            raise UserError(_("Select the warranty registration before submitting this claim."))
        if registration.state != "active":
            raise UserError(_("The linked warranty registration is not active."))
        if registration.end_date and registration.end_date < self.claim_date:
            raise UserError(_("The warranty has expired. This claim cannot be submitted as an in-warranty claim."))
        if registration.partner_id != self.partner_id or registration.product_id != self.product_id:
            raise ValidationError(_("Customer and product must match the selected warranty registration."))
        if registration.serial_number and self.serial_number != registration.serial_number:
            raise ValidationError(_("The serial number must match the selected warranty registration."))
        if registration.company_id != self.company_id:
            raise ValidationError(_("The claim and warranty registration must belong to the same company."))

    def _transition(self, target, extra_values=None):
        self.ensure_one()
        values = {"state": target}
        values.update(extra_values or {})
        self.write(values)
        label = dict(self._fields["state"].selection).get(target, target)
        self.message_post(body=_("Claim status changed to: %s") % label)
        return True

    def action_submit(self):
        for claim in self:
            claim._transition("submitted", {"review_note": False})
        return True

    def action_start_review(self):
        for claim in self:
            claim._transition("under_review", {"user_id": self.env.user.id})
        return True

    def action_approve(self):
        for claim in self:
            claim._transition(
                "approved",
                {"approved_by_id": self.env.user.id, "approved_date": fields.Datetime.now()},
            )
        return True

    def action_reject(self):
        for claim in self:
            if not claim.review_note:
                raise UserError(_("Enter a reason before rejecting the claim."))
            claim._transition("rejected")
        return True

    def action_start_work(self):
        for claim in self:
            claim._transition("in_progress")
        return True

    def action_resolve(self):
        for claim in self:
            if not claim.resolution_note:
                raise UserError(_("Enter resolution details before resolving the claim."))
            claim._transition("resolved", {"resolved_date": fields.Datetime.now()})
        return True

    def action_close(self):
        for claim in self:
            claim._transition("closed", {"closed_date": fields.Datetime.now()})
        return True

    @api.onchange("registration_id")
    def _onchange_registration(self):
        for claim in self:
            registration = claim.registration_id
            if registration:
                claim.partner_id = registration.partner_id
                claim.product_id = registration.product_id
                claim.serial_number = registration.serial_number
                claim.lot_ref = registration.lot_ref
                claim.source_ref = registration.source_ref
                claim.company_id = registration.company_id

    @api.onchange("lot_ref")
    def _onchange_lot_ref(self):
        if self.lot_ref:
            if "product_id" in self.lot_ref._fields:
                self.product_id = self.lot_ref.product_id
            serial = getattr(self.lot_ref, "name", False) or getattr(
                self.lot_ref, "lot_name", False
            )
            if serial:
                self.serial_number = serial

    def action_create_rma(self):
        self.ensure_one()
        if self.state not in ("approved", "in_progress", "resolved"):
            raise UserError(_("An RMA can be opened for an approved claim."))
        rma = self.env["ps.warranty.rma"].create(
            {
                "claim_id": self.id,
                "partner_id": self.partner_id.id,
                "product_id": self.product_id.id,
                "serial_number": self.serial_number,
                "company_id": self.company_id.id,
            }
        )
        self.message_post(body=_("RMA %s was created.") % rma.name)
        return {
            "type": "ir.actions.act_window",
            "name": rma.name,
            "res_model": "ps.warranty.rma",
            "res_id": rma.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_fsm_task(self):
        self.ensure_one()
        if not self.env.user.has_group("ps_warranty.group_warranty_officer"):
            raise AccessError(_("Only warranty officers can create or open Field Service tasks."))
        if self.fsm_task_ref:
            return {
                "type": "ir.actions.act_window",
                "name": self.fsm_task_ref.display_name,
                "res_model": self.fsm_task_ref._name,
                "res_id": self.fsm_task_ref.id,
                "view_mode": "form",
                "target": "current",
            }
        if (
            "project.task" not in self.env.registry.models
            or "is_fsm" not in self.env["project.task"]._fields
        ):
            raise UserError(_("Install Odoo Field Service to create a field service task."))
        project_domain = [("company_id", "in", [False, self.company_id.id])]
        if "is_fsm" in self.env["project.project"]._fields:
            project_domain.append(("is_fsm", "=", True))
        projects = self.env["project.project"].search(project_domain, limit=1)
        if not projects:
            raise UserError(_("Create a Field Service project before linking a warranty claim."))
        task_model = self.env["project.task"]
        values = {
            "name": _("Warranty repair: %s") % self.name,
            "project_id": projects.id,
        }
        if "partner_id" in task_model._fields:
            values["partner_id"] = self.partner_id.id
        if "description" in task_model._fields:
            values["description"] = self.description or ""
        if "company_id" in task_model._fields:
            values["company_id"] = self.company_id.id
        task = task_model.create(values)
        self.fsm_task_ref = task
        self.message_post(body=_("Linked Field Service task %s.") % task.display_name)
        return {
            "type": "ir.actions.act_window",
            "name": task.display_name,
            "res_model": task._name,
            "res_id": task.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_create_replacement_delivery(self):
        self.ensure_one()
        if not self.env.user.has_group("ps_warranty.group_warranty_officer"):
            raise AccessError(_("Only warranty officers can create replacement deliveries."))
        if self.state not in ("approved", "in_progress"):
            raise UserError(_("Replacement deliveries require an approved claim in progress."))
        if "stock.picking" not in self.env.registry.models:
            raise UserError(_("Install Inventory to create a replacement delivery."))
        lines = self.line_ids.filtered(
            lambda line: line.line_type in ("part", "replacement") and line.product_id
        )
        if not lines:
            raise UserError(_("Add replacement product or part lines before creating a delivery."))
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)], limit=1
        )
        if not warehouse or not warehouse.out_type_id or not warehouse.lot_stock_id:
            raise UserError(_("Configure a warehouse and outgoing operation type for this company."))
        customer_location = self.partner_id.with_company(self.company_id).property_stock_customer
        if not customer_location:
            customer_location = self.env.ref("stock.stock_location_customers", raise_if_not_found=False)
        if not customer_location:
            raise UserError(_("Could not find the customer stock location."))
        picking_model = self.env["stock.picking"]
        picking_values = {
            "partner_id": self.partner_id.id,
            "picking_type_id": warehouse.out_type_id.id,
            "location_id": warehouse.lot_stock_id.id,
            "location_dest_id": customer_location.id,
            "origin": self.name,
            "company_id": self.company_id.id,
        }
        picking = picking_model.create(picking_values)
        move_model = self.env["stock.move"]
        for line in lines:
            move_values = {
                "name": line.name or line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom_qty": line.quantity,
                "location_id": warehouse.lot_stock_id.id,
                "location_dest_id": customer_location.id,
                "picking_id": picking.id,
                "company_id": self.company_id.id,
            }
            if "product_uom" in move_model._fields:
                move_values["product_uom"] = line.product_id.uom_id.id
            move_model.create(move_values)
        picking.action_confirm()
        picking.action_assign()
        self.replacement_delivery_ref = picking
        self.message_post(body=_("Created replacement delivery %s.") % picking.display_name)
        return {
            "type": "ir.actions.act_window",
            "name": picking.display_name,
            "res_model": picking._name,
            "res_id": picking.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_rmas(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("RMA records"),
            "res_model": "ps.warranty.rma",
            "view_mode": "list,form",
            "domain": [("claim_id", "=", self.id)],
            "context": {"default_claim_id": self.id},
        }


class WarrantyClaimLine(models.Model):
    _name = "ps.warranty.claim.line"
    _description = "Warranty Repair or Replacement Line"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    claim_id = fields.Many2one(
        "ps.warranty.claim", required=True, ondelete="cascade", index=True
    )
    line_type = fields.Selection(
        [("repair", "Repair"), ("part", "Replacement part"), ("replacement", "Product replacement")],
        string="Operation",
        required=True,
        default="repair",
    )
    name = fields.Char(string="Description")
    product_id = fields.Many2one("product.product", string="Product / part")
    quantity = fields.Float(string="Quantity", required=True, default=1.0)
    unit_cost = fields.Monetary(string="Unit cost", currency_field="currency_id")
    subtotal = fields.Monetary(
        string="Subtotal", compute="_compute_subtotal", store=True, currency_field="currency_id"
    )
    currency_id = fields.Many2one(
        "res.currency", related="claim_id.currency_id", store=True, readonly=True
    )
    company_id = fields.Many2one(
        "res.company", related="claim_id.company_id", store=True, readonly=True, index=True
    )

    @api.depends("quantity", "unit_cost")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_cost

    @api.constrains("quantity", "unit_cost")
    def _check_quantity_and_cost(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("Quantity must be greater than zero."))
            if line.unit_cost < 0:
                raise ValidationError(_("Unit cost cannot be negative."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            claim = self.env["ps.warranty.claim"].browse(vals.get("claim_id"))
            if claim and claim.state not in ("approved", "in_progress"):
                raise UserError(_("Repair and replacement lines can only be added to approved claims."))
        return super().create(vals_list)

    def write(self, vals):
        if "claim_id" in vals:
            raise AccessError(_("A repair line cannot be moved to another claim."))
        if any(line.claim_id.state not in ("approved", "in_progress") for line in self):
            raise UserError(_("Repair and replacement lines can only be changed on approved claims in progress."))
        return super().write(vals)
