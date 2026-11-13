from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class QualityStandard(models.Model):
    _name = "ps.quality.standard"
    _description = "Quality Standard"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "product_id, code, version desc"

    name = fields.Char(required=True, tracking=True, index=True)
    code = fields.Char(required=True, copy=False, readonly=True, default="/", index=True)
    version = fields.Integer(required=True, default=1, readonly=True, tracking=True)
    supersedes_id = fields.Many2one("ps.quality.standard", readonly=True, copy=False)
    product_id = fields.Many2one("product.product", required=True, tracking=True, index=True)
    valid_from = fields.Date(default=fields.Date.context_today, tracking=True)
    valid_until = fields.Date(tracking=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("obsolete", "Obsolete")],
        required=True,
        default="draft",
        tracking=True,
        index=True,
    )
    line_ids = fields.One2many(
        "ps.quality.standard.line", "standard_id", string="Inspection criteria", copy=True
    )
    inspection_count = fields.Integer(compute="_compute_inspection_count")
    description = fields.Html()

    _standard_version_unique = models.Constraint(
        "unique(code, version, company_id)",
        "A standard code and version must be unique per company.",
    )

    @api.depends("code")
    def _compute_inspection_count(self):
        counts = dict(
            self.env["ps.quality.inspection"]._read_group(
                [("standard_id", "in", self.ids)], ["standard_id"], ["__count"]
            )
        )
        for standard in self:
            standard.inspection_count = counts.get(standard, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") or vals["code"] == "/":
                vals["code"] = self.env["ir.sequence"].next_by_code(
                    "ps.quality.standard"
                ) or "/"
        return super().create(vals_list)

    def write(self, vals):
        if "state" in vals:
            for standard in self:
                target = vals["state"]
                is_admin = self.env.user.has_group("ps_quality.group_quality_administrator")
                if target == "active":
                    if standard.state != "draft" or not is_admin:
                        raise AccessError(_("Only a Quality Administrator can activate a draft standard."))
                    if not standard.line_ids:
                        raise UserError(_("Add at least one inspection criterion before activation."))
                elif target == "obsolete":
                    if standard.state != "active" or not is_admin:
                        raise AccessError(_("Only a Quality Administrator can obsolete an active standard."))
                else:
                    raise AccessError(_("Invalid quality standard status transition."))
        return super().write(vals)

    @api.constrains("valid_from", "valid_until", "version", "company_id", "product_id")
    def _check_standard_values(self):
        for standard in self:
            if standard.version < 1:
                raise ValidationError(_("Standard version must be at least 1."))
            if standard.valid_from and standard.valid_until and standard.valid_until < standard.valid_from:
                raise ValidationError(_("The standard end date cannot precede its start date."))
            if standard.product_id.company_id and standard.product_id.company_id != standard.company_id:
                raise ValidationError(_("The product must be shared or belong to the standard company."))

    def action_activate(self):
        for standard in self:
            standard.write({"state": "active"})
        return True

    def action_obsolete(self):
        for standard in self:
            standard.write({"state": "obsolete"})
        return True

    def action_new_version(self):
        self.ensure_one()
        if not self.env.user.has_group("ps_quality.group_quality_administrator"):
            raise AccessError(_("Only a Quality Administrator can create a standard version."))
        if self.state != "active":
            raise UserError(_("Create a new version from an active standard."))
        new_standard = self.copy(
            {
                "name": self.name,
                "code": self.code,
                "version": self.version + 1,
                "supersedes_id": self.id,
                "state": "draft",
            }
        )
        self.action_obsolete()
        return {
            "type": "ir.actions.act_window",
            "name": new_standard.display_name,
            "res_model": self._name,
            "res_id": new_standard.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_inspections(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Quality inspections"),
            "res_model": "ps.quality.inspection",
            "view_mode": "list,form",
            "domain": [("standard_id", "=", self.id)],
            "context": {"default_standard_id": self.id, "default_product_id": self.product_id.id},
        }


class QualityStandardLine(models.Model):
    _name = "ps.quality.standard.line"
    _description = "Quality Standard Criterion"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    standard_id = fields.Many2one(
        "ps.quality.standard", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        "res.company", related="standard_id.company_id", store=True, index=True
    )
    name = fields.Char(required=True)
    criterion_type = fields.Selection(
        [("numeric", "Numeric"), ("pass_fail", "Pass / Fail"), ("text", "Text observation")],
        required=True,
        default="numeric",
    )
    has_minimum = fields.Boolean(string="Use minimum limit")
    min_value = fields.Float(digits=(16, 4))
    has_maximum = fields.Boolean(string="Use maximum limit")
    max_value = fields.Float(digits=(16, 4))
    unit = fields.Char(string="Unit of measure")
    method = fields.Selection(
        [
            ("measure", "Measurement"),
            ("visual", "Visual inspection"),
            ("functional", "Functional test"),
            ("document", "Document review"),
            ("laboratory", "Laboratory test"),
        ],
        required=True,
        default="measure",
    )
    required = fields.Boolean(default=True)
    instruction = fields.Text()

    @api.constrains(
        "criterion_type", "has_minimum", "min_value", "has_maximum", "max_value", "standard_id"
    )
    def _check_limits(self):
        for line in self:
            if line.criterion_type != "numeric" and (line.has_minimum or line.has_maximum):
                raise ValidationError(_("Min/Max limits are only valid for numeric criteria."))
            if line.has_minimum and line.has_maximum and line.min_value > line.max_value:
                raise ValidationError(_("The minimum value cannot exceed the maximum value."))
            if line.standard_id.state != "draft":
                raise UserError(_("Create a new standard version before changing active criteria."))

    @api.model_create_multi
    def create(self, vals_list):
        standards = self.env["ps.quality.standard"].browse(
            [vals.get("standard_id") for vals in vals_list if vals.get("standard_id")]
        )
        if any(standard.state != "draft" for standard in standards):
            raise UserError(_("Inspection criteria can only be added to a draft standard."))
        return super().create(vals_list)

    def write(self, vals):
        if any(line.standard_id.state != "draft" for line in self):
            raise UserError(_("Create a new standard version before changing active criteria."))
        return super().write(vals)

    def unlink(self):
        if any(line.standard_id.state != "draft" for line in self):
            raise UserError(_("Criteria on an active standard cannot be deleted."))
        return super().unlink()


class QualityPlan(models.Model):
    _name = "ps.quality.plan"
    _description = "Quality Inspection Plan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "next_date, name"

    name = fields.Char(required=True, tracking=True, index=True)
    code = fields.Char(required=True, copy=False, readonly=True, default="/", index=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    product_id = fields.Many2one("product.product", required=True, tracking=True, index=True)
    standard_id = fields.Many2one(
        "ps.quality.standard", required=True, tracking=True, domain="[('state', '=', 'active')]"
    )
    inspection_type = fields.Selection(
        [("iqc", "IQC - Incoming"), ("ipqc", "IPQC - In Process"), ("oqc", "OQC - Outgoing")],
        required=True,
        default="iqc",
        tracking=True,
        index=True,
    )
    frequency = fields.Selection(
        [
            ("per_receipt", "Each receipt"),
            ("per_lot", "Each lot / serial"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
        ],
        required=True,
        default="per_receipt",
        tracking=True,
    )
    frequency_interval = fields.Integer(default=1)
    sample_size = fields.Integer(required=True, default=1)
    next_date = fields.Date(tracking=True, index=True)
    inspector_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("archived", "Archived")],
        required=True,
        default="draft",
        tracking=True,
        index=True,
    )
    inspection_ids = fields.One2many("ps.quality.inspection", "plan_id")
    inspection_count = fields.Integer(compute="_compute_inspection_count")
    description = fields.Text()

    _plan_code_unique = models.Constraint(
        "unique(code, company_id)", "An inspection plan code must be unique per company."
    )

    @api.depends("inspection_ids")
    def _compute_inspection_count(self):
        counts = dict(
            self.env["ps.quality.inspection"]._read_group(
                [("plan_id", "in", self.ids)], ["plan_id"], ["__count"]
            )
        )
        for plan in self:
            plan.inspection_count = counts.get(plan, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") or vals["code"] == "/":
                vals["code"] = self.env["ir.sequence"].next_by_code("ps.quality.plan") or "/"
        return super().create(vals_list)

    @api.onchange("standard_id")
    def _onchange_standard_id(self):
        if self.standard_id:
            self.product_id = self.standard_id.product_id
            self.company_id = self.standard_id.company_id

    @api.constrains(
        "sample_size", "frequency_interval", "frequency", "standard_id", "product_id", "company_id", "state"
    )
    def _check_plan_values(self):
        for plan in self:
            if plan.sample_size <= 0 or plan.frequency_interval <= 0:
                raise ValidationError(_("Sample size and frequency interval must be greater than zero."))
            if plan.standard_id.product_id != plan.product_id:
                raise ValidationError(_("The plan product must match the standard product."))
            if plan.standard_id.company_id != plan.company_id:
                raise ValidationError(_("The plan and standard must belong to the same company."))
            if plan.state == "active" and plan.frequency in ("daily", "weekly", "monthly") and not plan.next_date:
                raise ValidationError(_("A recurring plan requires its next inspection date."))

    def write(self, vals):
        if "state" in vals:
            for plan in self:
                if vals["state"] == "active":
                    if plan.state != "draft" or not self.env.user.has_group("ps_quality.group_quality_manager"):
                        raise AccessError(_("Only a Quality Manager can activate a draft plan."))
                    if plan.standard_id.state != "active":
                        raise UserError(_("Activate the linked standard before activating this plan."))
                elif vals["state"] == "archived":
                    if plan.state != "active" or not self.env.user.has_group("ps_quality.group_quality_manager"):
                        raise AccessError(_("Only a Quality Manager can archive an active plan."))
                else:
                    raise AccessError(_("Invalid quality plan status transition."))
        return super().write(vals)

    def action_activate(self):
        for plan in self:
            plan.write({"state": "active"})
        return True

    def action_archive(self):
        for plan in self:
            plan.write({"state": "archived"})
        return True

    def action_create_inspection(self):
        self.ensure_one()
        if not self.env.user.has_group("ps_quality.group_quality_inspector"):
            raise AccessError(_("Only Quality Inspectors can create inspections from a plan."))
        if self.state != "active":
            raise UserError(_("Only an active quality plan can create an inspection."))
        inspection = self.env["ps.quality.inspection"].create(
            {
                "plan_id": self.id,
                "standard_id": self.standard_id.id,
                "product_id": self.product_id.id,
                "inspection_type": self.inspection_type,
                "inspector_id": self.inspector_id.id,
                "planned_date": self.next_date or fields.Date.context_today(self),
                "quantity_sampled": self.sample_size,
                "company_id": self.company_id.id,
            }
        )
        if self.frequency in ("daily", "weekly", "monthly") and self.next_date:
            from dateutil.relativedelta import relativedelta

            increments = {
                "daily": relativedelta(days=self.frequency_interval),
                "weekly": relativedelta(weeks=self.frequency_interval),
                "monthly": relativedelta(months=self.frequency_interval),
            }
            next_date = self.next_date + increments[self.frequency]
            self.sudo().write({"next_date": next_date})
            self.sudo().message_post(body=_("Inspection %(inspection)s created. Next inspection: %(date)s") % {
                "inspection": inspection.name,
                "date": next_date,
            }, author_id=self.env.user.partner_id.id)
        return {
            "type": "ir.actions.act_window",
            "name": inspection.name,
            "res_model": inspection._name,
            "res_id": inspection.id,
            "view_mode": "form",
            "target": "current",
        }
