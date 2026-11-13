from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class WarrantyRMA(models.Model):
    _name = "ps.warranty.rma"
    _description = "Warranty Return Merchandise Authorization"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(string="RMA reference", required=True, default="/", copy=False, index=True)
    claim_id = fields.Many2one(
        "ps.warranty.claim", string="Warranty claim", required=True, ondelete="restrict", index=True
    )
    partner_id = fields.Many2one(
        "res.partner", string="Customer", required=True, tracking=True, index=True
    )
    product_id = fields.Many2one(
        "product.product", string="Returned product", required=True, tracking=True, index=True
    )
    serial_number = fields.Char(string="Serial number", tracking=True)
    lot_ref = fields.Reference(
        selection="_selection_lot_models", string="Inventory lot / serial record"
    )
    date_requested = fields.Date(
        string="RMA requested", required=True, default=fields.Date.context_today
    )
    date_received = fields.Date(string="Product received", tracking=True)
    condition = fields.Selection(
        [
            ("unknown", "Not inspected"),
            ("good", "Good condition"),
            ("damaged", "Damaged"),
            ("incomplete", "Incomplete / missing parts"),
        ],
        string="Received condition",
        default="unknown",
        tracking=True,
    )
    inspection_result = fields.Html(string="Inspection result", tracking=True)
    replacement_product_id = fields.Many2one(
        "product.product", string="Replacement product", tracking=True
    )
    replacement_serial = fields.Char(string="Replacement serial number", tracking=True)
    resolution = fields.Selection(
        [("repair", "Repair and return"), ("replace", "Replace"), ("refund", "Refund"), ("no_fault", "No fault found")],
        string="RMA resolution",
        tracking=True,
    )
    date_closed = fields.Date(string="RMA closed", readonly=True, copy=False)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("received", "Received"),
            ("inspected", "Inspected"),
            ("returned", "Returned to customer"),
            ("replaced", "Replaced"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="draft",
        tracking=True,
        index=True,
    )
    description = fields.Html(string="Notes")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "ps_warranty_rma_attachment_rel",
        "rma_id",
        "attachment_id",
        string="Attachments",
        copy=False,
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )

    _rma_reference_unique = models.Constraint(
        "unique(name)", "RMA references must be unique."
    )

    @api.model
    def _selection_lot_models(self):
        if "stock.lot" in self.env.registry.models:
            return [("stock.lot", _("Inventory lot / serial"))]
        return []

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals["state"] = "draft"
            if not vals.get("name") or vals["name"] == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("ps.warranty.rma") or "/"
            if vals.get("claim_id"):
                claim = self.env["ps.warranty.claim"].browse(vals["claim_id"])
                if claim.state not in ("approved", "in_progress", "resolved"):
                    raise UserError(_("An RMA can only be created for an approved claim."))
                vals.setdefault("company_id", claim.company_id.id)
                vals.setdefault("partner_id", claim.partner_id.id)
                vals.setdefault("product_id", claim.product_id.id)
                vals.setdefault("serial_number", claim.serial_number)
                if vals.get("company_id") != claim.company_id.id:
                    raise ValidationError(_("The RMA and its claim must belong to the same company."))
        rmas = super().create(vals_list)
        rmas.message_post(body=_("RMA record created."))
        return rmas

    def write(self, vals):
        vals = dict(vals)
        if "state" in vals:
            for rma in self:
                rma._check_state_transition(vals["state"])
            if vals["state"] == "received":
                vals.setdefault("date_received", fields.Date.context_today(self))
            elif vals["state"] in ("returned", "replaced"):
                vals["date_closed"] = fields.Date.context_today(self)
        if "claim_id" in vals:
            raise AccessError(_("An RMA cannot be moved to another claim."))
        if "date_closed" in vals and vals.get("state") not in ("returned", "replaced"):
            raise AccessError(_("The RMA close date is set by the return or replacement action."))
        return super().write(vals)

    def _check_state_transition(self, target):
        self.ensure_one()
        is_officer = self.env.user.has_group("ps_warranty.group_warranty_officer")
        is_manager = self.env.user.has_group("ps_warranty.group_warranty_manager")
        transitions = {
            "received": (self.state == "draft" and is_officer),
            "inspected": (self.state == "received" and is_officer),
            "returned": (self.state == "inspected" and is_officer),
            "replaced": (self.state == "inspected" and is_officer),
            "cancelled": (self.state in ("draft", "received") and is_manager),
        }
        if not transitions.get(target, False):
            raise AccessError(_("This user or RMA status is not allowed to perform that transition."))
        if target == "inspected" and not self.inspection_result:
            raise UserError(_("Enter the inspection result before completing inspection."))
        if target == "returned" and (
            not self.resolution or self.resolution == "replace"
        ):
            raise UserError(_("Select a non-replacement resolution before returning the product."))
        if target == "replaced" and (
            not self.replacement_product_id or self.resolution != "replace"
        ):
            raise UserError(_("Select 'Replace' as the resolution and choose a replacement product."))

    def _transition(self, target, values=None):
        self.ensure_one()
        vals = {"state": target}
        vals.update(values or {})
        self.write(vals)
        label = dict(self._fields["state"].selection).get(target, target)
        self.message_post(body=_("RMA status changed to: %s") % label)
        return True

    def action_mark_received(self):
        for rma in self:
            rma._transition(
                "received", {"date_received": rma.date_received or fields.Date.context_today(rma)}
            )
        return True

    def action_inspect(self):
        for rma in self:
            rma._transition("inspected")
        return True

    def action_return_to_customer(self):
        for rma in self:
            if not rma.resolution or rma.resolution == "replace":
                raise UserError(_("Select a non-replacement resolution before returning the product."))
            rma._transition("returned", {"date_closed": fields.Date.context_today(rma)})
        return True

    def action_mark_replaced(self):
        for rma in self:
            if not rma.replacement_product_id or rma.resolution != "replace":
                raise UserError(_("Set the resolution to Replace and select the replacement product first."))
            rma._transition("replaced", {"date_closed": fields.Date.context_today(rma)})
        return True

    def action_cancel(self):
        for rma in self:
            rma._transition("cancelled")
        return True

    @api.onchange("claim_id")
    def _onchange_claim(self):
        for rma in self:
            if rma.claim_id:
                rma.partner_id = rma.claim_id.partner_id
                rma.product_id = rma.claim_id.product_id
                rma.serial_number = rma.claim_id.serial_number
                rma.lot_ref = rma.claim_id.lot_ref
                rma.company_id = rma.claim_id.company_id

    @api.constrains("replacement_product_id", "replacement_serial", "state")
    def _check_replacement_data(self):
        for rma in self:
            if rma.state == "replaced" and not rma.replacement_product_id:
                raise ValidationError(_("A replacement product is required for a replaced RMA."))

    @api.constrains("claim_id", "partner_id", "product_id", "company_id")
    def _check_claim_consistency(self):
        for rma in self:
            if rma.claim_id and (
                rma.company_id != rma.claim_id.company_id
                or rma.partner_id != rma.claim_id.partner_id
                or rma.product_id != rma.claim_id.product_id
            ):
                raise ValidationError(_("RMA customer, product and company must match the linked claim."))

    def action_open_claim(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.claim_id.name,
            "res_model": "ps.warranty.claim",
            "res_id": self.claim_id.id,
            "view_mode": "form",
            "target": "current",
        }
