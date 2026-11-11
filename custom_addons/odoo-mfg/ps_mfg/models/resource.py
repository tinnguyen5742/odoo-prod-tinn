from odoo import _, fields, models


class PsMfgResource(models.Model):
    _name = "ps.mfg.resource"
    _description = "Manufacturing Resource"
    _inherit = ["mail.thread"]

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    code = fields.Char(string="Resource Code", required=True, copy=False, tracking=True)
    name = fields.Char(string="Resource Name", required=True, tracking=True)
    account_id = fields.Many2one(
        "account.account", string="Account", required=True, tracking=True
    )
    cost_item_id = fields.Many2one(
        "ps.mfg.cost.item", string="Cost Item", required=True, tracking=True
    )
    enabled = fields.Boolean(string="Enabled", default=True, tracking=True)

    _mrp_resource_code_unique = models.Constraint(
        "UNIQUE(code, company_id)", _("Resource code must be unique")
    )
