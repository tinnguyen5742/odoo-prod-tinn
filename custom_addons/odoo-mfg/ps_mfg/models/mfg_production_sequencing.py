from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PsMfgProductionSequencing(models.Model):
    _name = "ps.mfg.production.sequencing"
    _description = "Production Sequencing"
    _rec_name = "code"
    _order = "id desc"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    code = fields.Char(
        string="Code", required=True, copy=False, readonly=True, default="New"
    )
    description = fields.Text(string="Description", required=True)
    sequencing_date = fields.Date(
        string="Sequencing Date", required=True, default=fields.Date.context_today
    )
    line_ids = fields.One2many(
        "ps.mfg.production.sequencing.line",
        "production_sequencing_id",
        string="Sequencing Lines",
    )
    existing_production_ids = fields.Many2many(
        "ps.mfg.production",
        compute="_compute_existing_production_ids",
        string="Existing Manufacturing Orders",
    )

    _code_unique = models.Constraint(
        "UNIQUE(code, company_id)",
        _("The sequencing code must be unique within each company!"),
    )

    @api.depends("line_ids.production_id")
    def _compute_existing_production_ids(self):
        for record in self:
            record.existing_production_ids = record.line_ids.production_id

    @api.constrains("line_ids")
    def _check_line_ids_unique(self):
        for record in self:
            production_ids = record.line_ids.mapped("production_id")
            if len(production_ids) != len(set(production_ids)):
                raise ValidationError(
                    _("Each manufacturing order can only be added once per sequencing.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", "New") == "New":
                vals["code"] = (
                    self.env["ir.sequence"].next_by_code("ps.mfg.production.sequencing")
                    or "New"
                )
        return super().create(vals_list)


class PsMfgProductionSequencingLine(models.Model):
    _name = "ps.mfg.production.sequencing.line"
    _description = "Production Sequencing Line"
    _order = "sequence asc"

    production_sequencing_id = fields.Many2one(
        "ps.mfg.production.sequencing",
        string="Production Sequencing",
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Sequence", default=1, required=True)
    line_number = fields.Integer(string="Line Number", compute="_compute_line_number")
    production_id = fields.Many2one(
        "ps.mfg.production",
        string="Manufacturing Order",
        required=True,
        ondelete="cascade",
        domain="['|', ('company_id', '=', False), ('company_id', '=', parent.company_id), ('id', 'not in', parent.existing_production_ids)]",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        related="production_id.product_id",
        store=True,
        readonly=True,
    )
    product_code = fields.Char(
        string="Product Code",
        related="production_id.product_id.x_product_code",
        store=True,
        readonly=True,
    )
    quantity = fields.Float(
        string="Quantity",
        related="production_id.product_qty",
        store=True,
        readonly=True,
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        related="production_id.product_uom_id",
        store=True,
        readonly=True,
    )

    _production_unique = models.Constraint(
        "UNIQUE(production_sequencing_id, production_id)",
        _("A manufacturing order can only be added once per sequencing!"),
    )

    @api.depends(
        "production_sequencing_id.line_ids",
        "production_sequencing_id.line_ids.sequence",
    )
    def _compute_line_number(self):
        lines_by_sequencing = defaultdict(
            lambda: self.env["ps.mfg.production.sequencing.line"]
        )
        for line in self:
            if line.production_sequencing_id:
                lines_by_sequencing[line.production_sequencing_id] |= line
            else:
                line.line_number = 1
        for sequencing, lines in lines_by_sequencing.items():
            sorted_lines = sequencing.line_ids.sorted("sequence, id")
            index_by_id = {
                line.id: idx for idx, line in enumerate(sorted_lines, start=1)
            }
            for line in lines:
                line.line_number = index_by_id.get(line.id, 1)
