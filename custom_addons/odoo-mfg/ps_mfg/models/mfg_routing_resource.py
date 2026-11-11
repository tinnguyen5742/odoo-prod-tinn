from odoo import api, fields, models


class PsMfgRoutingResource(models.Model):
    _name = "ps.mfg.routing.resource"
    _description = "Manufacturing Routing Resource"

    operation_id = fields.Many2one(
        "ps.mfg.operation",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="operation_id.company_id",
        store=True,
        readonly=True,
    )
    resource_id = fields.Many2one("ps.mfg.resource", string="Resource", required=True)
    resource_code = fields.Char(
        string="Resource Code", related="resource_id.code", readonly=True
    )
    resource_name = fields.Char(
        string="Resource Name", related="resource_id.name", readonly=True
    )
    cost_item_id = fields.Many2one(
        related="resource_id.cost_item_id",
        string="Cost Item",
        store=True,
        readonly=True,
    )
    cost_item_code = fields.Char(
        string="Cost Item Code", related="cost_item_id.code", readonly=True
    )
    cost_item_name = fields.Char(
        string="Cost Item Name", related="cost_item_id.name", readonly=True
    )
    account_id = fields.Many2one(
        related="resource_id.account_id", string="Account", readonly=True
    )
    resource_cost = fields.Monetary(string="Resource Cost", required=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        compute="_compute_currency_id",
        store=True,
        readonly=True,
    )

    @api.depends("operation_id.company_id", "resource_id.company_id")
    def _compute_currency_id(self):
        for rec in self:
            company = (
                rec.operation_id.company_id
                or rec.resource_id.company_id
                or self.env.company
            )
            rec.currency_id = company.currency_id
