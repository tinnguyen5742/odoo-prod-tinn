from odoo import _, fields, models


class PsMfgCostItem(models.Model):
    _name = "ps.mfg.cost.item"
    _description = "Cost Item"
    _inherit = ["mail.thread"]

    name = fields.Char(string="Cost Item Name", required=True, tracking=True)
    code = fields.Char(
        string="Cost Item Code", required=True, copy=False, tracking=True
    )
    enabled = fields.Boolean(string="Enabled", default=True, tracking=True)

    _ps_mfg_cost_item_code_unique = models.Constraint(
        "UNIQUE(code)", _("Cost item code must be unique")
    )
