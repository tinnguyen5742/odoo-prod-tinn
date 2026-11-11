from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command


class PsMfgWip(models.Model):
    _name = "ps.mfg.wip"
    _description = "MFG WIP Closing"
    _rec_name = "code"
    _order = "id desc"
    _check_company_auto = True
    _inherit = ["mail.thread"]

    code = fields.Char("In Progress Nbr", default="New", copy=False, readonly=True)
    company_id = fields.Many2one(
        "res.company", "Company", required=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        "res.currency",
        "Currency",
        compute="_compute_currency_id",
        store=True,
        readonly=True,
    )
    account_id = fields.Many2one(
        "account.account", "Account", required=True, check_company=True, tracking=True
    )
    period_date = fields.Date(
        "In Progress Period",
        required=True,
        tracking=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date = fields.Date(
        "In Progress Date",
        required=True,
        tracking=True,
        default=lambda self: fields.Date.context_today(self),
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("complete", "Complete"),
        ],
        string="Status",
        required=True,
        default="draft",
        copy=False,
        index=True,
        tracking=True,
    )
    beginning_value = fields.Monetary(
        "Beginning Value", currency_field="currency_id", default=10000000.0
    )
    total_debit = fields.Monetary(
        "Total Debit", currency_field="currency_id", default=50000000.0
    )
    total_credit = fields.Monetary(
        "Total Credit", currency_field="currency_id", default=20000000.0
    )
    allocated_value = fields.Monetary(
        "Allocated Value", currency_field="currency_id", default=5000000.0
    )
    wip_value = fields.Monetary(
        "WIP Value",
        currency_field="currency_id",
        compute="_compute_wip_value",
        store=True,
        readonly=True,
    )
    line_ids = fields.One2many("ps.mfg.wip.line", "wip_id", "Lines", copy=True)

    _wip_period_unique = models.Constraint(
        "UNIQUE(company_id, account_id, period_date)",
        _("A WIP closing for the same company, account and period already exists."),
    )

    @api.depends("company_id")
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.company_id.currency_id or self.env.company.currency_id

    @api.depends("beginning_value", "total_debit", "total_credit", "allocated_value")
    def _compute_wip_value(self):
        for rec in self:
            rec.wip_value = (
                (rec.beginning_value or 0.0)
                + (rec.total_debit or 0.0)
                - (rec.total_credit or 0.0)
                - (rec.allocated_value or 0.0)
            )

    @api.constrains("beginning_value", "total_debit", "total_credit", "allocated_value")
    def _check_amounts(self):
        for rec in self:
            if any(
                v < 0
                for v in (
                    rec.beginning_value,
                    rec.total_debit,
                    rec.total_credit,
                    rec.allocated_value,
                )
            ):
                raise ValidationError(_("Header amounts cannot be negative."))

    @api.onchange("period_date")
    def _onchange_period_date(self):
        if not self.period_date:
            return
        had_lines = bool(self.line_ids)
        self.period_date = self.period_date.replace(day=1)
        if self.state == "draft":
            self._refill_lines()
            if had_lines:
                return {
                    "warning": {
                        "title": _("Lines refilled"),
                        "message": _(
                            "Finished MOs were re-fetched and previous lines "
                            "(including manually entered costs) were replaced."
                        ),
                    }
                }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", "New") in (False, "New"):
                vals["code"] = (
                    self.env["ir.sequence"].next_by_code("ps.mfg.wip") or "New"
                )
            if vals.get("period_date"):
                vals["period_date"] = fields.Date.to_date(vals["period_date"]).replace(
                    day=1
                )
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("period_date"):
            vals["period_date"] = fields.Date.to_date(vals["period_date"]).replace(
                day=1
            )
        return super().write(vals)

    @staticmethod
    def _split_amount(total, weights, round_func):
        """Split ``total`` proportionally to ``weights`` with rounding.

        Remainder from rounding goes to the largest-weight line so the
        sum always equals ``total``.
        """
        amounts = [0.0] * len(weights)
        weight_total = sum(weights)
        if not weights or weight_total <= 0 or not total:
            return amounts
        running = 0.0
        biggest = max(range(len(weights)), key=lambda i: weights[i])
        for i, weight in enumerate(weights):
            if i == biggest:
                continue
            amounts[i] = round_func(total * weight / weight_total)
            running += amounts[i]
        amounts[biggest] = round_func(total - running)
        return amounts

    def _get_receipt_tran_cost(self, production):
        moves = self.env["ps.mfg.workorder.move"].search(
            [
                ("production_id", "=", production.id),
                ("state", "=", "approved"),
            ]
        )
        return sum(moves.mapped("amount_total"))

    def _get_estimated_cost(self, production):
        product = production.product_id
        if not product:
            return 0.0
        bom = (
            self.env["ps.mfg.bom"]
            ._bom_find(
                product,
                company_id=self.company_id.id if self.company_id else False,
            )
            .get(product)
        )
        if bom:
            total = 0.0
            for vals in bom._compute_scaled_components(
                product, 1.0, production.product_uom_id
            ):
                component = self.env["product.product"].browse(vals["product_id"])
                total += (vals["qty_planned"] or 0.0) * (
                    component.standard_price or 0.0
                )
            return total
        return product.standard_price or 0.0

    def _get_available_proposals(self):
        """Approved finish lines up to the period, not on other WIPs.

        Backlog (`transaction_date` on or before the period month-end) flows
        into the closing; later proposals wait for the next period. Receipt
        qty is the sum of finish lines per production. Description uses the
        latest proposal code. Own WIP lines are ignored so a refill keeps
        the current record's productions.
        """
        self.ensure_one()
        domain = [
            ("proposal_id.state", "=", "approved"),
            ("production_id", "!=", False),
        ]
        if self.company_id:
            domain.append(("proposal_id.company_id", "=", self.company_id.id))
        if self.period_date:
            import calendar

            last_day = calendar.monthrange(
                self.period_date.year, self.period_date.month
            )[1]
            cutoff = self.period_date.replace(day=last_day)
            domain.append(
                ("proposal_id.transaction_date", "<=", fields.Date.to_string(cutoff))
            )
        finish_lines = self.env["ps.mfg.proposal.finish.line"].search(
            domain, order="proposal_id desc, id desc"
        )
        qty_by_prod = defaultdict(float)
        latest_code = {}
        latest_key = {}
        for line in finish_lines:
            production = line.production_id
            qty_by_prod[production.id] += line.finish_qty or 0.0
            key = (line.proposal_id.transaction_date, line.proposal_id.id)
            if production.id not in latest_key or key > latest_key[production.id]:
                latest_key[production.id] = key
                latest_code[production.id] = line.proposal_id.code
        prod_ids = list(qty_by_prod)
        if not prod_ids:
            return []
        line_domain = [("production_id", "in", prod_ids)]
        if self._origin.id:
            line_domain.append(("wip_id", "!=", self._origin.id))
        used_ids = set(
            self.env["ps.mfg.wip.line"].search(line_domain).mapped("production_id").ids
        )
        Production = self.env["ps.mfg.production"]
        rows = []
        for prod_id, _key in sorted(latest_key.items(), key=lambda item: item[1]):
            if prod_id in used_ids:
                continue
            rows.append(
                {
                    "production": Production.browse(prod_id),
                    "receipt_qty": qty_by_prod[prod_id],
                    "description": latest_code[prod_id],
                }
            )
        return rows

    def _round(self, amount):
        if self.currency_id:
            return self.currency_id.round(amount or 0.0)
        return round(amount or 0.0, 2)

    def _refill_lines(self):
        for rec in self:
            if rec.state != "draft":
                continue
            rows = []
            for proposal in rec._get_available_proposals():
                production = proposal["production"]
                discrete_qty = production.product_qty or 0.0
                receipt_qty = proposal["receipt_qty"] or 0.0
                estimated_cost = rec._get_estimated_cost(production)
                rows.append(
                    {
                        "production_id": production.id,
                        "discrete_qty": discrete_qty,
                        "receipt_qty": receipt_qty,
                        "receipt_tran_cost": rec._get_receipt_tran_cost(production),
                        "estimated_cost": estimated_cost,
                        "weight": max(discrete_qty - receipt_qty, 0.0)
                        * (estimated_cost or 0.0),
                        "description": proposal["description"],
                    }
                )
            in_progress = self._split_amount(
                rec.wip_value or 0.0, [r["weight"] for r in rows], rec._round
            )
            commands = [Command.clear()]
            sequence = 10
            for row, allocated in zip(rows, in_progress):
                row.pop("weight")
                row["sequence"] = sequence
                row["in_progress_cost"] = allocated
                commands.append(Command.create(row))
                sequence += 10
            rec.line_ids = commands

    def action_allocate_in_progress(self):
        """Re-split the header WIP value over current lines.

        Keeps receipt/estimated costs (including manual edits) and only
        rewrites ``in_progress_cost``.
        """
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("WIP can only be allocated in draft."))
            lines = rec.line_ids.sorted(lambda l: (l.sequence, l.id))
            weights = [
                max((l.discrete_qty or 0.0) - (l.receipt_qty or 0.0), 0.0)
                * (l.estimated_cost or 0.0)
                for l in lines
            ]
            for line, allocated in zip(
                lines, self._split_amount(rec.wip_value or 0.0, weights, rec._round)
            ):
                line.in_progress_cost = allocated

    def action_fetch_finished_mos(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Finished MOs can only be fetched in draft."))
            rec._refill_lines()

    def action_complete(self):
        for rec in self:
            if rec.state != "draft":
                continue
            if rec.wip_value < 0:
                raise UserError(
                    _("WIP value cannot be negative. Check header amounts.")
                )
            rec.state = "complete"

    def action_draft(self):
        self.filtered(lambda r: r.state == "complete").write({"state": "draft"})


class PsMfgWipLine(models.Model):
    _name = "ps.mfg.wip.line"
    _description = "MFG WIP Closing Line"
    _order = "sequence, id"
    _check_company_auto = True

    wip_id = fields.Many2one(
        "ps.mfg.wip", "WIP Closing", required=True, index=True, ondelete="cascade"
    )
    company_id = fields.Many2one(
        "res.company", "Company", related="wip_id.company_id", store=True, readonly=True
    )
    currency_id = fields.Many2one(
        "res.currency",
        "Currency",
        related="wip_id.currency_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer("Sequence", default=10)
    production_id = fields.Many2one(
        "ps.mfg.production",
        "Discrete ID",
        required=True,
        check_company=True,
        domain="[('company_id', '=', company_id)]",
    )
    product_id = fields.Many2one(
        "product.product",
        "Inventory Name",
        related="production_id.product_id",
        store=True,
        readonly=True,
    )
    product_default_code = fields.Char(
        "Inventory CD", related="product_id.default_code", readonly=True
    )
    discrete_qty = fields.Float("Discrete Qty", default=0.0)
    receipt_qty = fields.Float("Receipt Qty", default=0.0)
    receipt_tran_cost = fields.Monetary(
        "Receipt Tran Cost", currency_field="currency_id", default=0.0
    )
    estimated_cost = fields.Monetary(
        "Estimated Cost", currency_field="currency_id", default=0.0
    )
    in_progress_cost = fields.Monetary(
        "In Progress Cost", currency_field="currency_id", default=0.0
    )
    unit_cost_actual = fields.Monetary(
        "Unit Cost Actual",
        currency_field="currency_id",
        compute="_compute_unit_cost_actual",
        store=True,
        readonly=True,
    )
    description = fields.Char("Description")

    @api.depends("receipt_tran_cost", "in_progress_cost", "receipt_qty")
    def _compute_unit_cost_actual(self):
        for rec in self:
            if rec.receipt_qty:
                rec.unit_cost_actual = (
                    (rec.receipt_tran_cost or 0.0) + (rec.in_progress_cost or 0.0)
                ) / rec.receipt_qty
            else:
                rec.unit_cost_actual = 0.0

    @api.constrains(
        "receipt_qty",
        "discrete_qty",
        "receipt_tran_cost",
        "estimated_cost",
        "in_progress_cost",
    )
    def _check_values(self):
        for rec in self:
            if rec.receipt_qty < 0 or rec.discrete_qty < 0:
                raise ValidationError(_("Quantities cannot be negative."))
            if (
                rec.receipt_tran_cost < 0
                or rec.estimated_cost < 0
                or rec.in_progress_cost < 0
            ):
                raise ValidationError(_("Costs cannot be negative."))

    @api.onchange("production_id")
    def _onchange_production_id(self):
        if self.production_id and not self.discrete_qty:
            self.discrete_qty = self.production_id.product_qty or 0.0
