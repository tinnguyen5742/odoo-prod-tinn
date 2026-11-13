from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class WarrantyRegistration(models.Model):
    _name = "ps.warranty.registration"
    _description = "Product Warranty Registration"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"

    name = fields.Char(string="Registration reference", required=True, default="/", copy=False, index=True)
    partner_id = fields.Many2one(
        "res.partner", string="Customer", required=True, tracking=True, index=True
    )
    product_id = fields.Many2one(
        "product.product", string="Product", required=True, tracking=True, index=True
    )
    serial_number = fields.Char(string="Serial number", tracking=True, index=True)
    lot_ref = fields.Reference(
        selection="_selection_lot_models", string="Inventory lot / serial record", copy=False
    )
    policy_id = fields.Many2one(
        "ps.warranty.policy", string="Warranty policy", required=True, tracking=True, index=True
    )
    source_ref = fields.Reference(
        selection="_selection_order_models", string="Sales / purchase order", copy=False
    )
    document_ref = fields.Reference(
        selection="_selection_document_models", string="Warranty document", copy=False
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "ps_warranty_registration_attachment_rel",
        "registration_id",
        "attachment_id",
        string="Attachments",
        copy=False,
    )
    purchase_date = fields.Date(string="Purchase date", tracking=True, index=True)
    start_date = fields.Date(
        string="Activation date", required=True, default=fields.Date.context_today, tracking=True
    )
    end_date = fields.Date(
        string="Warranty expiration date", compute="_compute_end_date", store=True, index=True
    )
    days_remaining = fields.Integer(compute="_compute_days_remaining")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="draft",
        tracking=True,
        index=True,
    )
    user_id = fields.Many2one(
        "res.users", string="Responsible", default=lambda self: self.env.user, tracking=True
    )
    notes = fields.Text(string="Notes")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", store=True, readonly=True
    )
    claim_ids = fields.One2many("ps.warranty.claim", "registration_id", string="Claims")
    claim_count = fields.Integer(compute="_compute_claim_count")

    _registration_reference_unique = models.Constraint(
        "unique(name)", "Warranty registration references must be unique."
    )

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

    @api.depends("start_date", "policy_id.duration", "policy_id.duration_unit")
    def _compute_end_date(self):
        for registration in self:
            if not registration.start_date or not registration.policy_id:
                registration.end_date = False
                continue
            duration = registration.policy_id.duration
            unit = registration.policy_id.duration_unit
            delta = {
                "day": relativedelta(days=duration),
                "month": relativedelta(months=duration),
                "year": relativedelta(years=duration),
            }[unit]
            registration.end_date = registration.start_date + delta - relativedelta(days=1)

    @api.depends("end_date")
    def _compute_days_remaining(self):
        today = fields.Date.context_today(self)
        for registration in self:
            registration.days_remaining = (
                (registration.end_date - today).days if registration.end_date else 0
            )

    @api.depends("claim_ids")
    def _compute_claim_count(self):
        counts = dict(
            self.env["ps.warranty.claim"]._read_group(
                [("registration_id", "in", self.ids)], ["registration_id"], ["__count"]
            )
        )
        for registration in self:
            registration.claim_count = counts.get(registration, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals["state"] = "draft"
            if not vals.get("name") or vals["name"] == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "ps.warranty.registration"
                ) or "/"
        records = super().create(vals_list)
        for registration in records:
            registration.message_post(body=_("Warranty registration created."))
        return records

    def write(self, vals):
        if "state" in vals:
            for registration in self:
                registration._check_state_transition(vals["state"])
        return super().write(vals)

    def _check_state_transition(self, target):
        self.ensure_one()
        is_officer = self.env.user.has_group("ps_warranty.group_warranty_officer")
        is_manager = self.env.user.has_group("ps_warranty.group_warranty_manager")
        if target == "active":
            if self.state != "draft" or not (is_officer or is_manager):
                raise AccessError(_("Only warranty officers can activate a draft registration."))
            if not self.policy_id.sudo().active:
                raise UserError(_("The selected warranty policy is archived."))
            if self.end_date and self.end_date < fields.Date.context_today(self):
                raise UserError(_("The warranty period has already ended."))
            return
        if target == "cancelled":
            if self.state not in ("draft", "active") or not is_manager:
                raise AccessError(_("Only a warranty manager can cancel a draft or active registration."))
            open_claims = self.claim_ids.filtered(
                lambda claim: claim.state not in ("closed", "rejected")
            )
            if open_claims:
                raise UserError(_("Close or reject open claims before cancelling this registration."))
            return
        if target == "expired":
            if not self.env.su or self.state != "active":
                raise AccessError(_("Warranty registrations expire through the scheduled job."))
            return
        raise AccessError(_("Invalid warranty registration status transition."))

    @api.constrains("policy_id", "product_id", "purchase_date", "start_date", "company_id")
    def _check_policy_applicability(self):
        for registration in self:
            policy = registration.policy_id
            if not policy:
                continue
            if policy.company_id != registration.company_id:
                raise ValidationError(_("The warranty policy must belong to the registration company."))
            if not policy.matches_product(registration.product_id):
                raise ValidationError(_("The selected warranty policy does not cover this product."))
            policy_date = registration.purchase_date or registration.start_date
            if policy_date and policy.date_start and policy_date < policy.date_start:
                raise ValidationError(_("The selected policy was not yet valid on the purchase date."))
            if policy_date and policy.date_end and policy_date > policy.date_end:
                raise ValidationError(_("The selected policy had expired on the purchase date."))

    @api.constrains("serial_number", "product_id", "company_id", "state")
    def _check_duplicate_active_serial(self):
        for registration in self.filtered(
            lambda record: record.serial_number and record.state in ("draft", "active")
        ):
            duplicate = self.search(
                [
                    ("id", "!=", registration.id),
                    ("company_id", "=", registration.company_id.id),
                    ("product_id", "=", registration.product_id.id),
                    ("serial_number", "=", registration.serial_number),
                    ("state", "in", ["draft", "active"]),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("An active or draft warranty already exists for this product serial number.")
                )

    @api.onchange("product_id", "company_id")
    def _onchange_product_policy(self):
        for registration in self:
            if not registration.product_id:
                continue
            policies = self.env["ps.warranty.policy"].search(
                [
                    ("active", "=", True),
                    ("company_id", "=", registration.company_id.id or self.env.company.id),
                ],
                order="sequence, name",
            )
            matching = policies.filtered(
                lambda policy: policy.matches_product(registration.product_id)
            )
            registration.policy_id = matching[:1]

    @api.onchange("source_ref")
    def _onchange_source_ref(self):
        for registration in self:
            order = registration.source_ref
            if not order:
                continue
            if "partner_id" in order._fields:
                registration.partner_id = order.partner_id
            order_date = getattr(order, "date_order", False) or getattr(
                order, "date_approve", False
            )
            if order_date:
                registration.purchase_date = fields.Date.to_date(order_date)
            order_lines = getattr(order, "order_line", self.env["product.product"])
            products = order_lines.mapped("product_id")
            if len(products) == 1:
                registration.product_id = products
            if "company_id" in order._fields and order.company_id:
                registration.company_id = order.company_id

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

    def action_activate(self):
        for registration in self:
            if registration.state != "draft":
                raise UserError(_("Only draft registrations can be activated."))
            registration.write({"state": "active"})
            registration.message_post(body=_("Warranty registration activated through %(end)s.") % {
                "end": registration.end_date or "—",
            })
        return True

    def action_cancel(self):
        for registration in self:
            registration.write({"state": "cancelled"})
            registration.message_post(body=_("Warranty registration cancelled."))
        return True

    def action_view_claims(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Warranty claims"),
            "res_model": "ps.warranty.claim",
            "view_mode": "kanban,list,form",
            "domain": [("registration_id", "=", self.id)],
            "context": {"default_registration_id": self.id},
        }

    @api.model
    def _cron_expire_registrations(self):
        today = fields.Date.context_today(self)
        expired = self.sudo().search(
            [("state", "=", "active"), ("end_date", "<", today)]
        )
        for registration in expired:
            registration.write({"state": "expired"})
            registration.message_post(body=_("Warranty period expired automatically."))
