from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools import float_compare


class PsMfgProposalFinish(models.Model):
    _name = "ps.mfg.proposal.finish"
    _description = "MFG Proposal Finish"
    _rec_name = "code"
    _check_company_auto = True
    _inherit = ["mail.thread"]

    company_id = fields.Many2one(
        "res.company", "Company", required=True, default=lambda self: self.env.company
    )
    code = fields.Char("Reference", default="New", copy=False, readonly=True)
    description = fields.Html(string="Description")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        string="Status",
        readonly=True,
        default="draft",
        tracking=True,
    )
    transaction_date = fields.Date(
        string="Transaction Date",
        required=True,
        tracking=True,
        default=lambda self: fields.Date.context_today(self),
    )
    from_date = fields.Date(
        string="From Date",
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    to_date = fields.Date(
        string="To Date",
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    dst_location_id = fields.Many2one(
        "stock.location",
        string="Default Destination",
        tracking=True,
        default=lambda self: self._default_dst_location(),
        domain="[('usage', '=', 'internal')]",
    )
    line_ids = fields.One2many(
        "ps.mfg.proposal.finish.line",
        "proposal_id",
        "Lines",
        copy=True,
    )
    production_ids = fields.Many2many(
        "ps.mfg.production",
        string="Manufacturing Orders",
        compute="_compute_production_ids",
        search="_search_production_ids",
    )
    move_ids = fields.Many2many(
        "stock.move",
        string="Stock Moves",
        compute="_compute_move_ids",
    )
    move_count = fields.Integer("Stock Move Count", compute="_compute_move_ids")
    # Dữ liệu cũ: trước 19.0.0.11 nhập TP qua phiếu Receipts (Vendors → kho), để nháp.
    picking_ids = fields.Many2many(
        "stock.picking",
        "ps_mfg_proposal_finish_picking_rel",
        "proposal_id",
        "picking_id",
        string="Receipts (legacy)",
        readonly=True,
        copy=False,
    )
    picking_count = fields.Integer(
        string="Receipt Count", compute="_compute_picking_count"
    )

    @api.model
    def _default_dst_location(self):
        picking_type = self.env["stock.picking.type"].search(
            [
                ("code", "=", "incoming"),
                ("company_id", "in", (self.env.company.id, False)),
            ],
            limit=1,
        )
        if picking_type and picking_type.default_location_dest_id:
            return picking_type.default_location_dest_id.id
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "in", (self.env.company.id, False))], limit=1
        )
        if warehouse and warehouse.lot_stock_id:
            return warehouse.lot_stock_id.id
        return False

    @api.depends("line_ids.production_id")
    def _compute_production_ids(self):
        for rec in self:
            rec.production_ids = rec.line_ids.production_id

    def _search_production_ids(self, operator, value):
        return [("line_ids.production_id", operator, value)]

    @api.depends("line_ids.move_id")
    def _compute_move_ids(self):
        for rec in self:
            rec.move_ids = rec.line_ids.move_id
            rec.move_count = len(rec.move_ids)

    @api.depends("picking_ids")
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    def _first_production_from_vals(self, vals):
        commands = vals.get("line_ids")
        if not commands:
            return False
        for cmd in commands:
            if not cmd:
                continue
            opcode = cmd[0]
            if opcode in (Command.CREATE, 0) and cmd[2]:
                production_id = cmd[2].get("production_id")
                if production_id:
                    return production_id
            if opcode in (Command.UPDATE, 1) and cmd[2]:
                production_id = cmd[2].get("production_id")
                if production_id:
                    return production_id
        return False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", "New") in (False, "New"):
                sequence = False
                production_id = self._first_production_from_vals(vals)
                if production_id:
                    production = self.env["ps.mfg.production"].browse(production_id)
                    workcenter = production.workcenter_id
                    if workcenter and workcenter.receipt_request_sequence_id:
                        sequence = workcenter.receipt_request_sequence_id.next_by_id()
                vals["code"] = (
                    sequence
                    or self.env["ir.sequence"].next_by_code("ps.mfg.proposal.finish")
                    or "New"
                )
        return super().create(vals_list)

    def _require_lines(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Select at least one manufacturing order line."))

    def _check_lines_ready(self):
        self.ensure_one()
        self._require_lines()
        self.line_ids._sync_finish_move()
        for line in self.line_ids:
            line._check_finish_lots()

    def action_submit_approval(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only draft proposals can be submitted for approval."))
        self._check_lines_ready()
        self.state = "pending"

    def action_reject(self):
        self.ensure_one()
        if self.state not in ("draft", "pending"):
            raise UserError(_("Only draft or pending proposals can be rejected."))
        self.line_ids.move_id.filtered(
            lambda m: m.state not in ("done", "cancel")
        )._action_cancel()
        self.state = "rejected"

    def action_approve(self):
        """Nhập kho thành phẩm: move Production → kho đích, done ngay (không picking)."""
        self.ensure_one()
        if self.state == "approved":
            return
        if self.state not in ("draft", "pending"):
            raise UserError(_("Only draft or pending proposals can be approved."))
        if self.picking_ids:
            # Phiếu cũ đã sinh Receipts trước 19.0.0.11
            self.state = "approved"
            return
        self._check_lines_ready()
        moves = self.env["stock.move"]
        for line in self.line_ids:
            move = line.move_id
            # Giá nhập = giá thành cộng dồn của công đoạn tại thời điểm Complete
            move.price_unit = line._get_finish_price_unit()
            if (line.tracking or "none") == "none":
                move.quantity = move.product_uom_qty
            moves |= move
        moves.picked = True
        moves._action_done()
        if any(move.state != "done" for move in moves):
            raise UserError(_("Could not complete the finished goods receipt."))
        self.state = "approved"

    def action_view_stock_moves(self):
        """Dịch chuyển kho của phiếu: view Lịch sử dịch chuyển (như Product Moves của mrp)."""
        self.ensure_one()
        return {
            "name": _("Stock Moves"),
            "type": "ir.actions.act_window",
            "res_model": "stock.move.line",
            "view_mode": "list,form",
            "views": [
                (self.env.ref("stock.view_move_line_tree").id, "list"),
                (False, "form"),
            ],
            "domain": [("move_id.ps_finish_line_id.proposal_id", "=", self.id)],
            "context": {"create": False},
            "target": "current",
        }

    def action_view_picking(self):
        self.ensure_one()
        if not self.picking_ids:
            return None
        action = {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "target": "current",
        }
        if len(self.picking_ids) == 1:
            action["view_mode"] = "form"
            action["res_id"] = self.picking_ids.id
        else:
            action["name"] = _("Receipts")
            action["view_mode"] = "list,form"
            action["domain"] = [("id", "in", self.picking_ids.ids)]
        return action


class PsMfgProposalFinishLine(models.Model):
    _name = "ps.mfg.proposal.finish.line"
    _description = "MFG Proposal Finish Line"
    _order = "sequence, id"
    _check_company_auto = True

    proposal_id = fields.Many2one(
        "ps.mfg.proposal.finish",
        "Proposal Finish",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        related="proposal_id.company_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer("Sequence", default=10)
    production_id = fields.Many2one(
        "ps.mfg.production",
        "Manufacturing Order",
        required=True,
        check_company=True,
        domain="[('state', '=', 'in_progress'), ('company_id', '=', company_id)]",
    )
    workorder_id = fields.Many2one(
        "ps.mfg.workorder",
        "Work Order",
        required=True,
        check_company=True,
        domain="[('production_id', '=', production_id), ('total_qty', '>', 0)]",
    )
    workorder_qty = fields.Float(
        "Work Order Quantity",
        related="workorder_id.total_qty",
        readonly=True,
    )
    remaining_qty = fields.Float(
        "Remaining Quantity",
        compute="_compute_remaining_qty",
    )
    product_id = fields.Many2one(
        "product.product",
        "Product",
        related="production_id.product_id",
        store=True,
        readonly=True,
    )
    x_product_code = fields.Char("Product Code")
    product_uom_id = fields.Many2one(
        "uom.uom",
        "Unit of Measure",
        related="product_id.uom_id",
        store=True,
        readonly=True,
    )
    tracking = fields.Selection(related="product_id.tracking", string="Tracking")
    finish_qty = fields.Float("Finish Quantity", required=True, default=0.0)
    dst_location_id = fields.Many2one(
        "stock.location",
        "Destination Location",
        required=True,
        domain="[('usage', '=', 'internal')]",
    )
    # Dữ liệu cũ (trước 19.0.0.11): 1 lot / dòng. Lot/serial giờ nằm trên move line.
    lot_id = fields.Many2one(
        "stock.lot",
        "Lot/Serial Number (legacy)",
        check_company=True,
        readonly=True,
        copy=False,
    )
    move_id = fields.Many2one(
        "stock.move",
        "Stock Move",
        readonly=True,
        copy=False,
        index=True,
    )
    lot_ids = fields.Many2many(
        "stock.lot",
        string="Lots/Serials",
        compute="_compute_lot_info",
    )
    lot_names = fields.Char("Lot/Serial Numbers", compute="_compute_lot_info")
    lot_qty = fields.Float("Lot/Serial Quantity", compute="_compute_lot_info")

    @api.depends(
        "move_id.move_line_ids.lot_id",
        "move_id.move_line_ids.lot_name",
        "move_id.move_line_ids.quantity",
    )
    def _compute_lot_info(self):
        for line in self:
            mls = line.move_id.move_line_ids.filtered(
                lambda ml: ml.lot_id or ml.lot_name
            )
            line.lot_ids = mls.lot_id
            line.lot_names = ", ".join(ml.lot_id.name or ml.lot_name for ml in mls)
            uom = line.move_id.product_uom
            line.lot_qty = sum(
                ml.product_uom_id._compute_quantity(ml.quantity, uom)
                if uom and ml.product_uom_id
                else ml.quantity
                for ml in mls
            )

    # ------------------------------------------------------------------
    # Stock move (Production → kho đích, không picking)
    # ------------------------------------------------------------------
    _FINISH_MOVE_FIELDS = (
        "production_id",
        "finish_qty",
        "dst_location_id",
        "x_product_code",
    )

    def _get_finish_picking_type(self):
        self.ensure_one()
        warehouse = self.dst_location_id.warehouse_id or self.env[
            "stock.warehouse"
        ].search([("company_id", "=", self.company_id.id)], limit=1)
        if not warehouse:
            raise UserError(_("No warehouse found for the destination location."))
        return warehouse._ps_mfg_get_finish_picking_type()

    def _prepare_finish_move_vals(self):
        self.ensure_one()
        proposal = self.proposal_id
        vals = {
            "description_picking": self.x_product_code or self.product_id.display_name,
            "product_id": self.product_id.id,
            "product_uom_qty": self.finish_qty,
            "product_uom": (self.product_uom_id or self.product_id.uom_id).id,
            "location_id": self.company_id._ps_mfg_production_location().id,
            "location_dest_id": self.dst_location_id.id,
            "picking_type_id": self._get_finish_picking_type().id,
            "company_id": self.company_id.id,
            "origin": proposal.code,
            "ps_finish_line_id": self.id,
        }
        if proposal.from_date:
            vals["date"] = datetime.combine(proposal.from_date, time.min)
        return vals

    def _sync_finish_move(self):
        """Tạo/cập nhật stock move của dòng khi phiếu còn draft/pending."""
        for line in self:
            if line.proposal_id.state not in ("draft", "pending"):
                continue
            if not line.product_id or not line.dst_location_id or line.finish_qty <= 0:
                continue
            move = line.move_id
            if move.state == "done":
                continue
            if move and move.product_id != line.product_id:
                move._action_cancel()
                move.unlink()
                move = self.env["stock.move"]
            if not move:
                move = self.env["stock.move"].create(line._prepare_finish_move_vals())
                move._action_confirm()
                line.move_id = move
                continue
            vals = {}
            if move.product_uom.compare(move.product_uom_qty, line.finish_qty) != 0:
                vals["product_uom_qty"] = line.finish_qty
            if move.location_dest_id != line.dst_location_id:
                vals["location_dest_id"] = line.dst_location_id.id
                vals["picking_type_id"] = line._get_finish_picking_type().id
            description = line.x_product_code or line.product_id.display_name
            if move.description_picking != description:
                vals["description_picking"] = description
            if vals:
                move.write(vals)
            if "location_dest_id" in vals:
                move.move_line_ids.filtered(lambda ml: ml.state != "done").write(
                    {"location_dest_id": line.dst_location_id.id}
                )

    def _check_finish_lots(self):
        """Hàng tracked: lot/serial nhập ở popup Details phải đủ SL nhập."""
        self.ensure_one()
        if (self.tracking or "none") == "none":
            return
        mls = self.move_id.move_line_ids
        if not mls or any(not (ml.lot_id or ml.lot_name) for ml in mls):
            raise UserError(
                _(
                    "Set the lot/serial numbers of %(product)s with the Details button.",
                    product=self.product_id.display_name,
                )
            )
        if self._compare_qty(self.lot_qty, self.finish_qty) != 0:
            raise UserError(
                _(
                    "Lot/serial quantities of %(product)s (%(lot_qty)s) must equal "
                    "the finish quantity (%(qty)s).",
                    product=self.product_id.display_name,
                    lot_qty=self.lot_qty,
                    qty=self.finish_qty,
                )
            )
        if self.tracking == "serial" and any(
            ml.product_uom_id.compare(ml.quantity, 1.0) != 0 for ml in mls
        ):
            raise UserError(
                _(
                    "Each serial number of %(product)s must have quantity 1.",
                    product=self.product_id.display_name,
                )
            )

    def action_show_lot_details(self):
        """Popup Detailed Operations chuẩn của Odoo (Generate Serials / Import Lots)."""
        self.ensure_one()
        if not self._origin.id:
            raise UserError(_("Save the receipt before entering lot/serial numbers."))
        line = self._origin
        line._sync_finish_move()
        if not line.move_id:
            raise UserError(
                _("Set the manufacturing order, quantity and destination first.")
            )
        return line.move_id.action_show_details()

    def _qty_uom(self):
        self.ensure_one()
        return self.product_uom_id or (
            self.product_id.uom_id if self.product_id else False
        )

    def _compare_qty(self, left, right):
        self.ensure_one()
        uom = self._qty_uom()
        if uom:
            return uom.compare(left, right)
        return float_compare(left or 0.0, right or 0.0, precision_digits=6)

    def _get_finish_price_unit(self):
        """Giá nhập kho = giá thành đơn vị cộng dồn của công đoạn trên dòng,
        quy đổi theo UoM của dòng (giá công đoạn tính theo UoM sản phẩm).
        """
        self.ensure_one()
        unit_cost = self.workorder_id.unit_cost or 0.0
        product_uom = self.product_id.uom_id
        line_uom = self.product_uom_id or product_uom
        if line_uom and product_uom and line_uom != product_uom:
            return product_uom._compute_price(unit_cost, line_uom)
        return unit_cost

    def _get_remaining_qty(self, workorder=None):
        self.ensure_one()
        wo = workorder or self.workorder_id
        if not wo:
            return 0.0
        origin_id = self._origin.id
        others = self.search(
            [
                ("workorder_id", "=", wo.id),
                ("proposal_id.state", "!=", "rejected"),
                ("id", "!=", origin_id or 0),
            ]
        )
        used = sum(others.mapped("finish_qty"))
        if self.proposal_id:
            for sibling in self.proposal_id.line_ids:
                if sibling is self or sibling.workorder_id != wo:
                    continue
                if not sibling._origin.id:
                    used += sibling.finish_qty or 0.0
        return (wo.total_qty or 0.0) - used

    @api.depends(
        "workorder_id",
        "workorder_id.total_qty",
        "finish_qty",
        "proposal_id.line_ids.finish_qty",
        "proposal_id.line_ids.workorder_id",
        "proposal_id.state",
    )
    def _compute_remaining_qty(self):
        wo_ids = self.workorder_id.ids
        used_by_wo = dict.fromkeys(wo_ids, 0.0)
        if wo_ids:
            grouped = self._read_group(
                [
                    ("workorder_id", "in", wo_ids),
                    ("proposal_id.state", "!=", "rejected"),
                ],
                ["workorder_id"],
                ["finish_qty:sum"],
            )
            for workorder, qty in grouped:
                used_by_wo[workorder.id] = qty or 0.0
        for line in self:
            wo = line.workorder_id
            if not wo:
                line.remaining_qty = 0.0
                continue
            consumed = used_by_wo.get(wo.id, 0.0)
            origin_id = line._origin.id
            if origin_id:
                consumed -= line._origin.finish_qty or 0.0
            if line.proposal_id:
                for sibling in line.proposal_id.line_ids:
                    if sibling is line or sibling.workorder_id != wo:
                        continue
                    if not sibling._origin.id:
                        consumed += sibling.finish_qty or 0.0
            line.remaining_qty = (wo.total_qty or 0.0) - consumed

    def _get_default_workorder(self):
        self.ensure_one()
        wos = self.production_id.workorder_ids.filtered(
            lambda w: float_compare(w.total_qty or 0.0, 0.0, precision_digits=6) > 0
        ).sorted("sequence")
        for wo in reversed(wos):
            if float_compare(self._get_remaining_qty(wo), 0.0, precision_digits=6) > 0:
                return wo
        return wos[-1:] if wos else self.env["ps.mfg.workorder"]

    def _default_product_code(self, production=None):
        production = production or self.production_id
        product = production.product_id if production else False
        return product.x_product_code if product else False

    @api.onchange("production_id")
    def _onchange_production_id(self):
        self.workorder_id = False
        self.lot_id = False
        self.finish_qty = 0.0
        self.x_product_code = self._default_product_code()
        if not self.dst_location_id and self.proposal_id.dst_location_id:
            self.dst_location_id = self.proposal_id.dst_location_id
        if not self.production_id:
            return
        workorder = self._get_default_workorder()
        if workorder:
            self.workorder_id = workorder
            remaining = self._get_remaining_qty(workorder)
            if float_compare(remaining, 0.0, precision_digits=6) > 0:
                self.finish_qty = remaining

    @api.onchange("workorder_id")
    def _onchange_workorder_id(self):
        if not self.workorder_id:
            return
        remaining = self._get_remaining_qty()
        if (
            not self.finish_qty
            and float_compare(remaining, 0.0, precision_digits=6) > 0
        ):
            self.finish_qty = remaining

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            production = (
                self.env["ps.mfg.production"].browse(vals["production_id"])
                if vals.get("production_id")
                else False
            )
            if production and not vals.get("x_product_code"):
                vals["x_product_code"] = production.product_id.x_product_code
            if not vals.get("dst_location_id") and vals.get("proposal_id"):
                proposal = self.env["ps.mfg.proposal.finish"].browse(
                    vals["proposal_id"]
                )
                if proposal.dst_location_id:
                    vals["dst_location_id"] = proposal.dst_location_id.id
            if production and not vals.get("workorder_id"):
                line = self.new(dict(vals))
                workorder = line._get_default_workorder()
                if workorder:
                    vals["workorder_id"] = workorder.id
                    if not vals.get("finish_qty"):
                        vals["finish_qty"] = line._get_remaining_qty(workorder)
        lines = super().create(vals_list)
        lines._sync_finish_move()
        return lines

    def write(self, vals):
        if "production_id" in vals and "x_product_code" not in vals:
            production = (
                self.env["ps.mfg.production"].browse(vals["production_id"])
                if vals["production_id"]
                else False
            )
            vals = dict(
                vals,
                x_product_code=production.product_id.x_product_code
                if production
                else False,
            )
        res = super().write(vals)
        if any(fname in vals for fname in self._FINISH_MOVE_FIELDS):
            self._sync_finish_move()
        return res

    def unlink(self):
        moves = self.move_id.filtered(lambda m: m.state not in ("done", "cancel"))
        moves._action_cancel()
        moves.unlink()
        return super().unlink()

    @api.constrains("finish_qty", "workorder_id", "proposal_id")
    def _check_finish_qty(self):
        checked = set()
        for line in self:
            if line.proposal_id.state == "rejected":
                continue
            if line._compare_qty(line.finish_qty or 0.0, 0.0) <= 0:
                raise ValidationError(_("Finish Quantity must be positive."))
            wo = line.workorder_id
            if not wo or wo.id in checked:
                continue
            checked.add(wo.id)
            used = sum(
                self.search(
                    [
                        ("workorder_id", "=", wo.id),
                        ("proposal_id.state", "!=", "rejected"),
                    ]
                ).mapped("finish_qty")
            )
            if line._compare_qty(used, wo.total_qty or 0.0) > 0:
                raise ValidationError(
                    _(
                        "Finish quantity for %(workorder)s (%(used)s) cannot exceed "
                        "the work order output (%(total)s).",
                        workorder=wo.display_name,
                        used=used,
                        total=wo.total_qty or 0.0,
                    )
                )

    @api.constrains("workorder_id", "production_id")
    def _check_workorder(self):
        for line in self:
            if (
                line.workorder_id
                and line.production_id
                and line.workorder_id.production_id != line.production_id
            ):
                raise ValidationError(
                    _("The work order must belong to the selected manufacturing order.")
                )
            if (
                line.workorder_id
                and float_compare(
                    line.workorder_id.total_qty or 0.0, 0.0, precision_digits=6
                )
                <= 0
            ):
                raise ValidationError(
                    _("Select a work order that has completed output.")
                )

    @api.constrains("dst_location_id")
    def _check_dst_location(self):
        for line in self:
            if line.dst_location_id and line.dst_location_id.usage != "internal":
                raise ValidationError(
                    _("Destination location must be an internal location.")
                )
