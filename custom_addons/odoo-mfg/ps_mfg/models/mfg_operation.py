from odoo import api, fields, models


class PsMfgOperation(models.Model):
    """Shared operation (công đoạn) master, reused by many BoMs.

    BoMs reference it through ``ps.mfg.routing`` lines (sequence, variants,
    enabled stay per BoM). Standard resources / costs live here only.
    """

    _name = "ps.mfg.operation"
    _description = "Manufacturing Operation"
    _order = "code, id"
    _check_company_auto = True
    _inherit = ["mail.thread"]
    _rec_names_search = ["code", "name"]

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    code = fields.Char(
        required=True,
        copy=False,
        tracking=True,
        default=lambda self: self.env._("New"),
        help="Generated from the operation sequence on creation.",
    )
    name = fields.Char(string="Operation", required=True, tracking=True)
    description = fields.Html()
    enabled = fields.Boolean(default=True, tracking=True)
    resource_ids = fields.One2many(
        "ps.mfg.routing.resource", "operation_id", "Resources", copy=True
    )
    routing_ids = fields.One2many(
        "ps.mfg.routing", "operation_id", "BoM Operations", readonly=True
    )
    bom_count = fields.Integer("BoMs", compute="_compute_bom_count")

    _ps_mfg_operation_code_unique = models.Constraint(
        "UNIQUE(code, company_id)", "Operation code must be unique per company"
    )

    @api.model_create_multi
    def create(self, vals_list):
        new_labels = {"New", self.env._("New")}
        for vals in vals_list:
            # The "New" default is only applied by super(), so a missing key
            # also means "generate".
            if not vals.get("code") or vals["code"] in new_labels:
                company_id = vals.get("company_id") or self.env.company.id
                vals["code"] = self._next_free_code(company_id)
        operations = super().create(vals_list)
        if bom_id := self.env.context.get("ps_mfg_link_bom_id"):
            operations._link_to_bom(bom_id)
        return operations

    def _link_to_bom(self, bom_id):
        """Append these operations to the routing of BoM ``bom_id``."""
        bom = self.env["ps.mfg.bom"].browse(bom_id).exists()
        if not bom:
            return
        sequence = max(bom.operation_ids.mapped("sequence") or [0])
        routing_vals = []
        for operation in self:
            sequence += 1
            routing_vals.append(
                {"bom_id": bom.id, "operation_id": operation.id, "sequence": sequence}
            )
        ctx = dict(self.env.context)
        ctx.pop("ps_mfg_link_bom_id", None)
        self.env["ps.mfg.routing"].with_context(ctx).create(routing_vals)

    def _next_free_code(self, company_id):
        """Next sequence code not yet used in the company.

        Codes created by the 19.0.0.12 migration (OP001...) or typed by hand
        may already exist, so skip taken numbers instead of failing on the
        UNIQUE(code, company_id) constraint.
        """
        sequence = self.env["ir.sequence"].with_company(company_id)
        while True:
            code = sequence.next_by_code("ps.mfg.operation")
            if not code:
                return code
            taken = self.with_context(active_test=False).search_count(
                [("code", "=", code), ("company_id", "=", company_id)], limit=1
            )
            if not taken:
                return code

    @api.depends("code", "name")
    def _compute_display_name(self):
        for op in self:
            op.display_name = f"[{op.code}] {op.name}" if op.code else op.name

    @api.depends("routing_ids.bom_id")
    def _compute_bom_count(self):
        for op in self:
            op.bom_count = len(op.routing_ids.bom_id)

    def action_view_boms(self):
        self.ensure_one()
        return {
            "name": self.env._("Bills of Materials"),
            "type": "ir.actions.act_window",
            "res_model": "ps.mfg.bom",
            "view_mode": "list,form",
            "domain": [("id", "in", self.routing_ids.bom_id.ids)],
        }
