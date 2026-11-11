from odoo import fields, models
from odoo.exceptions import UserError


class PsMfgRouting(models.Model):
    _name = "ps.mfg.routing"
    _description = "Manufacturing Routing"
    _order = "sequence, id"
    _inherit = ["mail.thread"]

    bom_id = fields.Many2one(
        "ps.mfg.bom",
        string="Bill of Materials",
        required=True,
        index=True,
        check_company=True,
        ondelete="cascade",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company", "Company", related="bom_id.company_id", store=True
    )
    operation_id = fields.Many2one(
        "ps.mfg.operation",
        required=True,
        index=True,
        check_company=True,
        ondelete="restrict",
        tracking=True,
        domain="[('enabled', '=', True)]",
    )
    operation_code = fields.Char(
        string="Operation Code", related="operation_id.code", readonly=True
    )
    name = fields.Char(
        string="Operation Name", related="operation_id.name", store=True, readonly=True
    )
    enabled = fields.Boolean(string="Enabled", default=True, tracking=True)
    sequence = fields.Integer(string="Sequence", default=1, tracking=True)
    # Resources / costs are defined on the operation (master) only.
    resource_ids = fields.One2many(related="operation_id.resource_ids")
    description = fields.Html(related="operation_id.description")
    bom_line_ids = fields.One2many(
        "ps.mfg.bom.line", "operation_id", "Components", readonly=True
    )
    possible_bom_product_template_attribute_value_ids = fields.Many2many(
        related="bom_id.possible_product_template_attribute_value_ids"
    )
    bom_product_template_attribute_value_ids = fields.Many2many(
        "product.template.attribute.value",
        string="Apply on Variants",
        ondelete="restrict",
        domain="[('id', 'in', possible_bom_product_template_attribute_value_ids)]",
        help="Routing Variants needed to apply this operation.",
    )

    _ps_mfg_routing_operation_unique = models.Constraint(
        "UNIQUE(bom_id, operation_id)", "Operation must be unique per BoM"
    )

    def action_open_operation_form(self):
        """Open a new operation (catalog) form linked to the BoM in context.

        Called from the BoM "Add an operation" control button: once saved,
        ``ps.mfg.operation.create`` adds the routing line to that BoM.
        """
        bom = self.env["ps.mfg.bom"].browse(self.env.context.get("ps_mfg_bom_id"))
        if not bom.exists():
            raise UserError(
                self.env._("Save the Bill of Materials before adding an operation.")
            )
        return {
            "name": self.env._("New Operation"),
            "type": "ir.actions.act_window",
            "res_model": "ps.mfg.operation",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "ps_mfg_link_bom_id": bom.id,
                "default_company_id": bom.company_id.id or self.env.company.id,
            },
        }

    def action_open_routing(self):
        """Open this BoM operation as a full page (not a dialog)."""
        self.ensure_one()
        return {
            "name": self.display_name,
            "type": "ir.actions.act_window",
            "res_model": "ps.mfg.routing",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(self.env.ref("ps_mfg.ps_mfg_routing_view_form").id, "form")],
            "target": "current",
        }

    def action_open_operation(self):
        """Open the operation master, where resources / costs are edited."""
        self.ensure_one()
        return {
            "name": self.operation_id.display_name,
            "type": "ir.actions.act_window",
            "res_model": "ps.mfg.operation",
            "res_id": self.operation_id.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def _skip_routing(self, product, never_attribute_values=False):
        self.ensure_one()
        if not product or product._name == "product.template":
            return False
        return self.env["ps.mfg.bom"]._skip_for_no_variant(
            product,
            self.bom_product_template_attribute_value_ids,
            never_attribute_values,
        )
