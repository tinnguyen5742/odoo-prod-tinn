from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WarrantyPolicy(models.Model):
    _name = "ps.warranty.policy"
    _description = "Warranty Policy"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name"

    name = fields.Char(string="Policy name", required=True, tracking=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    date_start = fields.Date(string="Valid from", tracking=True)
    date_end = fields.Date(string="Valid until", tracking=True)
    duration = fields.Integer(string="Warranty period", required=True, default=12)
    duration_unit = fields.Selection(
        [("day", "Days"), ("month", "Months"), ("year", "Years")],
        required=True,
        default="month",
    )
    product_ids = fields.Many2many(
        "product.product",
        "ps_warranty_policy_product_rel",
        "policy_id",
        "product_id",
        string="Products",
        help="Leave empty to apply to all products in the selected categories, or to all products.",
    )
    product_category_ids = fields.Many2many(
        "product.category",
        "ps_warranty_policy_category_rel",
        "policy_id",
        "category_id",
        string="Product categories",
    )
    coverage_type = fields.Selection(
        [("free", "Free warranty"), ("chargeable", "Chargeable warranty")],
        string="Coverage type",
        required=True,
        default="free",
        tracking=True,
    )
    inspection_fee = fields.Monetary(string="Inspection fee", currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", store=True, readonly=True
    )
    conditions = fields.Html(string="Warranty terms and conditions")
    notes = fields.Text(string="Internal notes")
    registration_count = fields.Integer(compute="_compute_registration_count")
    registration_ids = fields.One2many("ps.warranty.registration", "policy_id")

    _policy_name_company_unique = models.Constraint(
        "unique(name, company_id)",
        "A warranty policy with this name already exists for this company.",
    )

    @api.depends("registration_ids")
    def _compute_registration_count(self):
        Registration = self.env["ps.warranty.registration"]
        counts = dict(
            Registration._read_group(
                [("policy_id", "in", self.ids)], ["policy_id"], ["__count"]
            )
        )
        for policy in self:
            policy.registration_count = counts.get(policy, 0)

    @api.constrains("duration", "date_start", "date_end")
    def _check_policy_dates_and_duration(self):
        for policy in self:
            if policy.duration <= 0:
                raise ValidationError(_("Warranty period must be greater than zero."))
            if policy.date_start and policy.date_end and policy.date_end < policy.date_start:
                raise ValidationError(_("The policy end date must not be before its start date."))

    def matches_product(self, product):
        self.ensure_one()
        if self.product_ids and product not in self.product_ids:
            return False
        if self.product_category_ids:
            category = product.categ_id
            ancestors = (category.parent_path or "").strip("/").split("/")
            if category not in self.product_category_ids and not any(
                str(item.id) in ancestors for item in self.product_category_ids
            ):
                return False
        return True

    def action_view_registrations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Warranty registrations"),
            "res_model": "ps.warranty.registration",
            "view_mode": "list,form",
            "domain": [("policy_id", "=", self.id)],
            "context": {"default_policy_id": self.id},
        }
