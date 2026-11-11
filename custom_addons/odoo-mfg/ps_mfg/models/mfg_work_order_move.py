from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PsMfgWorkOrderMove(models.Model):
    _name = "ps.mfg.workorder.move"
    _description = "MFG Work Order Move"
    _check_company_auto = True
    _inherit = ["mail.thread"]

    company_id = fields.Many2one(
        "res.company",
        "Company",
        related="production_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        "Currency",
        compute="_compute_currency_id",
        store=True,
        readonly=True,
    )
    # Chọn xưởng trước, MO lọc theo xưởng, rồi mới tới công đoạn.
    workcenter_id = fields.Many2one(
        "ps.mfg.work.center",
        "Work Center",
        required=True,
        tracking=True,
        index=True,
    )
    production_id = fields.Many2one(
        "ps.mfg.production",
        "Manufacturing Order",
        required=True,
        tracking=True,
        domain="[('state', '=', 'in_progress'), ('workcenter_id', '=', workcenter_id)]",
    )
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
    processing_date = fields.Date(
        string="Processing Date",
        required=True,
        tracking=True,
        default=lambda self: fields.Date.context_today(self),
    )
    allowed_from_workorder_ids = fields.One2many(
        "ps.mfg.workorder", compute="_compute_allowed_from_workorder_ids"
    )
    allowed_to_workorder_ids = fields.One2many(
        "ps.mfg.workorder", compute="_compute_allowed_to_workorder_ids"
    )
    # Để trống = "Bắt đầu" (vật tư mới cấp vào công đoạn đầu, chưa có BTP từ công đoạn trước).
    from_workorder_id = fields.Many2one(
        "ps.mfg.workorder",
        "From Work Order",
        tracking=True,
        domain='[("id", "in", allowed_from_workorder_ids)]',
    )
    from_label = fields.Char(
        "From Work Order Label",
        compute="_compute_from_label",
        help="Tên công đoạn nguồn, hoặc 'Bắt đầu' khi chưa có công đoạn nguồn.",
    )
    to_workorder_id = fields.Many2one(
        "ps.mfg.workorder",
        "To Work Order",
        tracking=True,
        domain='[("id", "in", allowed_to_workorder_ids)]',
        required=True,
    )
    shift = fields.Integer(string="Shift", default=1, required=True, aggregator=None)
    previous_qty = fields.Float(
        "Previous Quantity",
        compute="_compute_previous_qty",
        store=False,
        readonly=True,
        help="SL trước của ca: bán thành phẩm còn lại từ công đoạn trước. "
        "Bằng 0 khi từ 'Bắt đầu'.",
    )
    available_qty = fields.Float(
        "Available Quantity",
        compute="_compute_available_qty",
        store=False,
        readonly=True,
        help="SL khả dụng của ca (trần của SL chuyển): theo NVL đã cấp và "
        "output công đoạn trước, đã trừ các ca cùng from→to làm trước.",
    )
    routing_progress = fields.Json(
        "Routing Progress",
        compute="_compute_routing_progress",
        help="Tiến độ các công đoạn của lệnh SX, dùng cho widget hiển thị.",
    )
    move_qty = fields.Float(
        "Move Quantity",
        required=True,
        default=0.0,
    )
    material_amount = fields.Monetary(
        "Material Amount",
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
        help="NVL tiêu hao theo BoM của ca.",
    )
    extra_amount = fields.Monetary(
        "Extra Component Amount",
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
    )
    amount_total = fields.Monetary(
        "Amount Total",
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
        help="ThanhTien của ca: tổng amount các dòng vật tư (NVL + extra). WIP dùng field này.",
    )
    resource_amount = fields.Monetary(
        "Resource Amount",
        currency_field="currency_id",
        compute="_compute_costs",
        store=True,
        help="Tổng chi phí tài nguyên thực tế nhập trên ca.",
    )
    stage_cost = fields.Monetary(
        "Operation Cost",
        currency_field="currency_id",
        compute="_compute_costs",
        store=True,
        help="Chi phí riêng của công đoạn trong ca = NVL + extra + tài nguyên.",
    )
    stage_unit_cost = fields.Monetary(
        "Operation Unit Cost",
        currency_field="currency_id",
        compute="_compute_costs",
        store=True,
    )
    transferred_in_unit_cost = fields.Monetary(
        "Transferred-in Unit Cost",
        currency_field="currency_id",
        compute="_compute_transferred_in_unit_cost",
        store=True,
        readonly=False,
        help="Giá đơn vị bán thành phẩm nhận từ công đoạn trước (cộng dồn), "
        "chốt lại lúc Complete.",
    )
    transferred_in_cost = fields.Monetary(
        "Transferred-in Cost",
        currency_field="currency_id",
        compute="_compute_costs",
        store=True,
    )
    total_cost = fields.Monetary(
        "Total Cost",
        currency_field="currency_id",
        compute="_compute_costs",
        store=True,
        help="Giá thành cộng dồn = giá nhận từ công đoạn trước + chi phí công đoạn.",
    )
    unit_cost = fields.Monetary(
        "Unit Cost",
        currency_field="currency_id",
        compute="_compute_costs",
        store=True,
        help="Giá thành đơn vị cộng dồn áp cho SL đầu ra của ca.",
    )
    resource_line_ids = fields.One2many(
        "ps.mfg.workorder.move.resource",
        "workorder_move_id",
        "Resources",
        compute="_compute_resource_line_ids",
        store=True,
        precompute=True,
        readonly=False,
    )
    workorder_component_line_ids = fields.One2many(
        "ps.mfg.workorder.move.line",
        "workorder_move_id",
        "Components",
        compute="_compute_component_line_ids",
        store=True,
        precompute=True,
        readonly=False,
    )
    extra_component_line_ids = fields.One2many(
        "ps.mfg.workorder.move.extra.line",
        "workorder_move_id",
        "Extra Components",
    )
    consumption_move_ids = fields.One2many(
        "stock.move",
        "ps_workorder_move_id",
        string="Consumption Moves",
        readonly=True,
        copy=False,
    )
    consumption_move_count = fields.Integer(
        string="Consumption Count", compute="_compute_consumption_move_count"
    )
    # Dữ liệu cũ: trước 19.0.0.9 ca tiêu hao qua phiếu internal transfer.
    picking_ids = fields.Many2many(
        "stock.picking",
        "ps_mfg_workorder_move_picking_rel",
        "workorder_move_id",
        "picking_id",
        string="Internal Transfers (legacy)",
        readonly=True,
        copy=False,
    )
    picking_count = fields.Integer(
        string="Transfer Count", compute="_compute_picking_count"
    )
    lot_line_ids = fields.One2many(
        "ps.mfg.workorder.move.lot",
        "workorder_move_id",
        "Lot / Serial Lines",
    )
    has_tracked_components = fields.Boolean(
        "Has Tracked Components",
        compute="_compute_has_tracked_components",
    )

    _workorder_move_unique = models.Constraint(
        "UNIQUE(company_id, production_id, from_workorder_id, to_workorder_id, shift)",
        _(
            "A move for the same product, from work order, to work order, and shift already exists."
        ),
    )

    def _get_first_workorder(self):
        return self.env["ps.mfg.workorder"].search(
            [("production_id", "=", self.production_id.id)], limit=1
        )

    @api.depends("company_id")
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.company_id.currency_id or self.env.company.currency_id

    @api.depends("production_id.code", "to_workorder_id.code", "shift")
    def _compute_display_name(self):
        # Tên ca = MO/Mã công đoạn/Ca, trùng tham chiếu của stock move tiêu hao
        super()._compute_display_name()
        for rec in self:
            name = rec._consumption_origin()
            if name:
                rec.display_name = name

    @api.depends(
        "workorder_component_line_ids.amount", "extra_component_line_ids.amount"
    )
    def _compute_amount_total(self):
        for rec in self:
            rec.material_amount = sum(rec.workorder_component_line_ids.mapped("amount"))
            rec.extra_amount = sum(rec.extra_component_line_ids.mapped("amount"))
            rec.amount_total = rec.material_amount + rec.extra_amount

    @api.depends(
        "amount_total",
        "resource_line_ids.actual_cost",
        "transferred_in_unit_cost",
        "move_qty",
    )
    def _compute_costs(self):
        for rec in self:
            qty = rec.move_qty or 0.0
            rec.resource_amount = sum(rec.resource_line_ids.mapped("actual_cost"))
            rec.stage_cost = rec.amount_total + rec.resource_amount
            rec.transferred_in_cost = (rec.transferred_in_unit_cost or 0.0) * qty
            rec.total_cost = rec.transferred_in_cost + rec.stage_cost
            rec.stage_unit_cost = rec.stage_cost / qty if qty else 0.0
            rec.unit_cost = rec.total_cost / qty if qty else 0.0

    @api.depends("production_id", "from_workorder_id")
    def _compute_transferred_in_unit_cost(self):
        # Không depends vào unit_cost của công đoạn trước: ca đã duyệt giữ giá đã chốt
        # kể cả khi công đoạn trước có thêm ca mới. Chốt lại ở action_approve.
        for rec in self:
            rec.transferred_in_unit_cost = rec._get_transferred_in_unit_cost()

    def _get_transferred_in_unit_cost(self):
        self.ensure_one()
        if not self.from_workorder_id:
            return 0.0
        return self.from_workorder_id.unit_cost or 0.0

    @api.depends("production_id", "to_workorder_id")
    def _compute_resource_line_ids(self):
        for rec in self:
            if rec.state == "approved":
                # Ca đã duyệt (kể cả ca cũ lúc upgrade): giữ nguyên tài nguyên đã ghi.
                rec.resource_line_ids = rec.resource_line_ids
                continue
            if (
                rec.resource_line_ids
                and rec.production_id == rec._origin.production_id
                and rec.to_workorder_id == rec._origin.to_workorder_id
            ):
                continue
            commands = [Command.clear()]
            for res in rec.to_workorder_id.resource_ids:
                commands.append(
                    Command.create(
                        {
                            "sequence": res.sequence,
                            "resource_id": res.resource_id.id,
                        }
                    )
                )
            rec.resource_line_ids = commands

    @api.depends("picking_ids")
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    @api.depends("consumption_move_ids")
    def _compute_consumption_move_count(self):
        for rec in self:
            rec.consumption_move_count = len(rec.consumption_move_ids)

    @api.depends(
        "workorder_component_line_ids.tracking",
        "extra_component_line_ids.tracking",
    )
    def _compute_has_tracked_components(self):
        for rec in self:
            rec.has_tracked_components = any(
                line.tracking and line.tracking != "none"
                for line in rec.workorder_component_line_ids
            ) or any(
                line.tracking and line.tracking != "none"
                for line in rec.extra_component_line_ids
            )

    def action_submit_approval(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "pending"})

    def action_approve(self):
        for rec in self:
            if rec.state not in ("draft", "pending"):
                raise UserError(_("Only draft or pending moves can be approved."))
            if not rec.move_qty or rec.move_qty <= 0:
                raise UserError(
                    _(
                        "Cannot approve: move quantity must be greater than 0.",
                    )
                )
            remaining = rec._get_remaining_qty()
            if rec.move_qty > remaining:
                raise UserError(
                    _(
                        "Cannot approve: move quantity (%(move)s) exceeds the remaining quantity "
                        "(%(remaining)s) for this shift.",
                        move=rec.move_qty,
                        remaining=remaining,
                    )
                )
            rec._refresh_line_prices()
            # Chốt giá bán thành phẩm nhận từ công đoạn trước tại thời điểm Complete
            rec.transferred_in_unit_cost = rec._get_transferred_in_unit_cost()
            rec._create_and_done_consumption_moves()
            rec.state = "approved"

    def action_reject(self):
        self.filtered(lambda r: r.state in ("draft", "pending")).write(
            {"state": "rejected"}
        )

    def action_reset_draft(self):
        self.filtered(lambda r: r.state in ("pending", "rejected")).write(
            {"state": "draft"}
        )

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
            action["name"] = _("Transfers")
            action["view_mode"] = "list,form"
            action["domain"] = [("id", "in", self.picking_ids.ids)]
        return action

    def action_view_stock_moves(self):
        """Dịch chuyển kho (xuất tiêu hao) của ca: view Lịch sử dịch chuyển
        (stock.move.line), giống nút Product Moves của mrp.
        """
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
            "domain": [("move_id.ps_workorder_move_id", "=", self.id)],
            "context": {"create": False},
            "target": "current",
        }

    def _refresh_line_prices(self):
        """Snapshot ``standard_price`` onto every line at Complete, same source as stock OUT."""
        self.ensure_one()
        company = self.company_id or self.env.company
        for line in self.workorder_component_line_ids:
            if line.component_id:
                line.price_unit = (
                    line.component_id.with_company(company).standard_price or 0.0
                )
        extras = self.extra_component_line_ids.with_context(ps_mfg_refresh_price=True)
        for line in extras:
            if line.component_id:
                line.price_unit = (
                    line.component_id.with_company(company).standard_price or 0.0
                )

    def _get_production_location(self):
        """Company Production location (Odoo 19: per company, no xmlid)."""
        self.ensure_one()
        return (self.company_id or self.env.company)._ps_mfg_production_location()

    def _consumption_origin(self):
        self.ensure_one()
        parts = [
            self.production_id.code or "",
            self.to_workorder_id.code or "",
            str(self.shift or ""),
        ]
        return "/".join(part for part in parts if part)

    def _line_product_qty(self, line):
        qty = line.actual_qty or 0.0
        if qty <= 0:
            return 0.0
        product_uom = line.component_id.uom_id
        if line.uom_id and product_uom and line.uom_id != product_uom:
            return line.uom_id._compute_quantity(qty, product_uom)
        return qty

    def _lot_line_product_qty(self, lot_line):
        qty = lot_line.qty or 0.0
        if qty <= 0:
            return 0.0
        line = lot_line.component_line_id or lot_line.extra_line_id
        product_uom = lot_line.component_id.uom_id
        if line and line.uom_id and product_uom and line.uom_id != product_uom:
            return line.uom_id._compute_quantity(qty, product_uom)
        return qty

    def _iter_consumption_lines(self):
        self.ensure_one()
        yield from self.workorder_component_line_ids
        yield from self.extra_component_line_ids

    def _check_tracked_line_lots(self, line):
        product = line.component_id
        tracking = product.tracking
        lot_lines = line.lot_line_ids
        if tracking == "none":
            if lot_lines:
                raise UserError(
                    _(
                        "Product %(product)s is not tracked; remove its lot/serial lines.",
                        product=product.display_name,
                    )
                )
            return
        if not lot_lines or any(not lot_line.lot_id for lot_line in lot_lines):
            raise UserError(
                _(
                    "Select a lot/serial for %(product)s.",
                    product=product.display_name,
                )
            )
        uom = line.uom_id or product.uom_id
        lot_qty = sum(lot_lines.mapped("qty"))
        if uom.compare(lot_qty, line.actual_qty or 0.0) != 0:
            raise UserError(
                _(
                    "Lot/serial quantities for %(product)s (%(lot_qty)s) must equal "
                    "the actual quantity (%(actual)s).",
                    product=product.display_name,
                    lot_qty=lot_qty,
                    actual=line.actual_qty or 0.0,
                )
            )

    def _check_workshop_availability(self, src, qty_by_product, qty_by_product_lot):
        Quant = self.env["stock.quant"]
        for product, needed in qty_by_product.items():
            if not product.is_storable or needed <= 0:
                continue
            available = Quant._get_available_quantity(product, src)
            if product.uom_id.compare(available, needed) < 0:
                raise UserError(
                    _(
                        "Not enough stock of %(product)s at %(location)s: "
                        "available %(available)s, needed %(needed)s.",
                        product=product.display_name,
                        location=src.display_name,
                        available=available,
                        needed=needed,
                    )
                )
        for (product, lot), needed in qty_by_product_lot.items():
            if not product.is_storable or needed <= 0:
                continue
            available = Quant._get_available_quantity(
                product, src, lot_id=lot, strict=True
            )
            if product.uom_id.compare(available, needed) < 0:
                raise UserError(
                    _(
                        "Not enough stock of %(product)s (%(lot)s) at %(location)s: "
                        "available %(available)s, needed %(needed)s.",
                        product=product.display_name,
                        lot=lot.display_name,
                        location=src.display_name,
                        available=available,
                        needed=needed,
                    )
                )

    def _prepare_consumption_move_vals(self, src, dest):
        self.ensure_one()
        qty_by_product = {}
        qty_by_product_lot = {}
        line_rows = []
        for line in self._iter_consumption_lines():
            if not line.component_id:
                continue
            qty = self._line_product_qty(line)
            if qty <= 0:
                continue
            self._check_tracked_line_lots(line)
            if line.component_id.tracking == "none":
                qty_by_product[line.component_id] = (
                    qty_by_product.get(line.component_id, 0.0) + qty
                )
            else:
                for lot_line in line.lot_line_ids:
                    lot_qty = self._lot_line_product_qty(lot_line)
                    if lot_qty <= 0:
                        continue
                    key = (line.component_id, lot_line.lot_id)
                    qty_by_product_lot[key] = qty_by_product_lot.get(key, 0.0) + lot_qty
            line_rows.append((line, qty))
        self._check_workshop_availability(src, qty_by_product, qty_by_product_lot)
        origin = self._consumption_origin()
        vals_list = [
            {
                "description_picking": line.component_id.display_name,
                "product_id": line.component_id.id,
                "product_uom_qty": qty,
                "product_uom": line.component_id.uom_id.id,
                "location_id": src.id,
                "location_dest_id": dest.id,
                "company_id": self.company_id.id,
                "price_unit": line.price_unit,
                "origin": origin,
                "warehouse_id": src.warehouse_id.id,
                "ps_workorder_move_id": self.id,
            }
            for line, qty in line_rows
        ]
        return vals_list, line_rows

    def _apply_lots_to_consumption_moves(self, moves, line_rows, src, dest):
        unused = moves
        MoveLine = self.env["stock.move.line"]
        for line, qty in line_rows:
            move = unused.filtered(
                lambda m, product=line.component_id, demand=qty: (
                    m.product_id == product
                    and m.product_uom.compare(m.product_uom_qty, demand) == 0
                )
            )[:1]
            if not move:
                raise UserError(_("Could not complete the consumption transfer."))
            unused -= move
            if line.component_id.tracking == "none":
                if move.product_uom.is_zero(
                    move.quantity
                ) and not move.product_uom.is_zero(move.product_uom_qty):
                    move.quantity = move.product_uom_qty
                move.picked = True
                continue
            move.move_line_ids.unlink()
            sml_vals = []
            for lot_line in line.lot_line_ids:
                lot_qty = self._lot_line_product_qty(lot_line)
                if lot_qty <= 0:
                    continue
                sml_vals.append(
                    {
                        "move_id": move.id,
                        "product_id": line.component_id.id,
                        "lot_id": lot_line.lot_id.id,
                        "quantity": lot_qty,
                        "product_uom_id": line.component_id.uom_id.id,
                        "location_id": src.id,
                        "location_dest_id": dest.id,
                        "company_id": self.company_id.id,
                        "picked": True,
                    }
                )
            if sml_vals:
                MoveLine.create(sml_vals)
            move.picked = True

    def _create_and_done_consumption_moves(self):
        """Xuất tiêu hao NVL xưởng → kho ảo Production (giống move_raw_ids của mrp).

        Không tạo phiếu: stock.move gắn ca qua ``ps_workorder_move_id`` và được
        ``_action_done`` ngay. Đích usage=production nên move là OUT (có định giá).
        """
        self.ensure_one()
        if self.consumption_move_ids or self.picking_ids:
            return
        src = self.workcenter_id.location_id
        if not src:
            raise UserError(_("The work center has no location."))
        dest = self._get_production_location()
        vals_list, line_rows = self._prepare_consumption_move_vals(src, dest)
        if not vals_list:
            return
        moves = self.env["stock.move"].create(vals_list)
        moves._action_confirm()
        self._apply_lots_to_consumption_moves(moves, line_rows, src, dest)
        moves._action_done()
        if any(move.state != "done" for move in moves):
            raise UserError(_("Could not complete the component consumption."))

    def write(self, vals):
        locked_fields = {
            "move_qty",
            "previous_qty",
            "production_id",
            "from_workorder_id",
            "to_workorder_id",
            "shift",
            "processing_date",
            "workorder_component_line_ids",
            "extra_component_line_ids",
            "lot_line_ids",
            "picking_ids",
            "consumption_move_ids",
            "resource_line_ids",
            "transferred_in_unit_cost",
        }
        if any(rec.state == "approved" for rec in self) and locked_fields & set(vals):
            raise ValidationError(
                _(
                    "Approved moves are locked to preserve quantity/amount history. "
                    "Create a new shift move to adjust."
                )
            )
        res = super().write(vals)
        # Ghi move_qty từ code/import: rescale dòng theo move_qty mới.
        # Skip khi vals đã chứa commands (form/onchange đã build lines đúng).
        if "move_qty" in vals and "workorder_component_line_ids" not in vals:
            for rec in self:
                if rec.state == "approved" or not rec.move_qty:
                    continue
                if not rec.production_id or not rec.to_workorder_id:
                    continue
                rec.workorder_component_line_ids = rec._prepare_component_lines(
                    rec.move_qty
                )
        return res

    def unlink(self):
        if any(rec.state == "approved" for rec in self):
            raise ValidationError(
                _(
                    "Approved moves are locked to preserve quantity/amount history. "
                    "Create a new shift move to adjust."
                )
            )
        return super().unlink()

    @api.depends("production_id", "from_workorder_id", "to_workorder_id", "shift")
    def _compute_previous_qty(self):
        for rec in self:
            # Từ "Bắt đầu" chưa có BTP nào từ công đoạn trước → 0.
            rec.previous_qty = (
                rec._get_remaining_qty() if rec.from_workorder_id else 0.0
            )

    @api.depends("production_id", "from_workorder_id", "to_workorder_id", "shift")
    def _compute_available_qty(self):
        for rec in self:
            rec.available_qty = rec._get_remaining_qty()

    @api.depends("from_workorder_id")
    def _compute_from_label(self):
        for rec in self:
            rec.from_label = (
                rec.from_workorder_id.display_name
                if rec.from_workorder_id
                else _("Start")
            )

    @api.depends(
        "production_id.workorder_ids.total_qty",
        "from_workorder_id",
        "to_workorder_id",
    )
    def _compute_routing_progress(self):
        for rec in self:
            if not rec.production_id:
                rec.routing_progress = False
                continue
            workorders = rec._get_production_workorders()
            # Chỉ công đoạn hợp lệ cho "Đến công đoạn" mới được chọn trên stepper.
            selectable_ids = set(rec.allowed_to_workorder_ids._origin.ids)
            rec.routing_progress = {
                "product_qty": rec.production_id.product_qty,
                "from_id": rec.from_workorder_id.id or False,
                "to_id": rec.to_workorder_id.id or False,
                "steps": [
                    {
                        "id": False,
                        "code": "",
                        "name": _("Start"),
                        "done_qty": 0,
                        "selectable": False,
                    }
                ]
                + [
                    {
                        "id": wo.id,
                        "code": wo.code,
                        "name": wo.name,
                        "done_qty": wo.total_qty,
                        "selectable": wo.id in selectable_ids,
                    }
                    for wo in workorders
                ],
            }

    def _get_production_workorders(self):
        """Công đoạn của lệnh SX theo thứ tự `(sequence, id)`."""
        self.ensure_one()
        return self.env["ps.mfg.workorder"].search(
            [("production_id", "=", self.production_id.id)]
        )

    def _get_previous_workorder(self):
        """Công đoạn liền trước `to_workorder_id` (rỗng nếu là công đoạn đầu)."""
        self.ensure_one()
        if not self.production_id or not self.to_workorder_id:
            return self.env["ps.mfg.workorder"]
        workorders = self._get_production_workorders()
        to_id = self.to_workorder_id.id
        if to_id not in workorders.ids:
            return workorders.browse()
        index = workorders.ids.index(to_id)
        return workorders[index - 1] if index > 0 else workorders.browse()

    def _get_available_qty(self):
        """Tổng vào của công đoạn:
        - CĐ đầu: Giới hạn theo lượng thành phẩm tối đa tương ứng với NVL đã thực nhận từ YCCP (hoặc full nếu YCCP cũ).
        - CĐ sau: Giới hạn bởi min(tổng output approved của CĐ trước, lượng NVL thực nhận của chính CĐ này nếu có).
        """
        self.ensure_one()
        if not self.production_id or not self.to_workorder_id:
            return 0.0
        first_workorder = self._get_first_workorder()
        cmp_request = self.env["ps.mfg.component.request"].search(
            [
                ("production_id", "=", self.production_id.id),
                ("state", "!=", "cancelled"),
            ],
            limit=1,
        )

        # Lượng sản phẩm khả dụng theo tiến độ nhận NVL của công đoạn đích
        material_producible_qty = (
            cmp_request._get_producible_qty(self.to_workorder_id)
            if cmp_request
            else 0.0
        )

        if not self.from_workorder_id and self.to_workorder_id == first_workorder:
            return material_producible_qty
        if (
            self.from_workorder_id
            and self.to_workorder_id
            and self.from_workorder_id != self.to_workorder_id
        ):
            upstream = self.search(
                [
                    ("production_id", "=", self.production_id.id),
                    ("to_workorder_id", "=", self.from_workorder_id.id),
                    ("state", "=", "approved"),
                ]
            )
            upstream_qty = sum(upstream.mapped("move_qty"))
            # CĐ sau: Bị chặn bởi cả bán thành phẩm CĐ trước VÀ NVL cấp cho CĐ này (nếu có)
            return min(upstream_qty, material_producible_qty)
        return 0.0

    def _get_remaining_qty(self):
        """SL trước của ca = available - move_qty các ca cùng from→to, shift nhỏ hơn (trừ rejected, trừ chính nó)."""
        self.ensure_one()
        if not self.production_id or not self.to_workorder_id:
            return 0.0
        available = self._get_available_qty()
        domain = [
            ("production_id", "=", self.production_id.id),
            ("to_workorder_id", "=", self.to_workorder_id.id),
            ("state", "!=", "rejected"),
            ("shift", "<", self.shift or 0),
        ]
        if self.from_workorder_id:
            domain.append(("from_workorder_id", "=", self.from_workorder_id.id))
        else:
            domain.append(("from_workorder_id", "=", False))
        if self._origin.id:
            domain.append(("id", "!=", self._origin.id))
        consumed_before = sum(self.search(domain).mapped("move_qty"))
        return max(available - consumed_before, 0.0)

    def _get_next_shift(self):
        """Ca mặc định = max(shift hiện có) + 1 của cùng from→to.

        Không lọc state: UNIQUE constraint áp cả rejected.
        """
        self.ensure_one()
        if not self.production_id or not self.to_workorder_id:
            return 1
        domain = [
            ("production_id", "=", self.production_id.id),
            ("to_workorder_id", "=", self.to_workorder_id.id),
        ]
        if self.from_workorder_id:
            domain.append(("from_workorder_id", "=", self.from_workorder_id.id))
        else:
            domain.append(("from_workorder_id", "=", False))
        if self._origin.id:
            domain.append(("id", "!=", self._origin.id))
        max_shift = max(self.search(domain).mapped("shift") or [0])
        return max_shift + 1

    @api.onchange("to_workorder_id")
    def _onchange_to_workorder_id(self):
        # Đảo luồng: chọn "Đến công đoạn" trước, "Từ công đoạn" tự suy ra
        # (công đoạn gần nhất phía trước còn WIP, hoặc "Bắt đầu" = rỗng nếu không có).
        # Định nghĩa trước _onchange_default_move_qty để SL/ca tính theo From mới.
        for rec in self:
            if not rec.to_workorder_id:
                continue
            to_key = (rec.to_workorder_id.sequence, rec.to_workorder_id.id)
            candidates = rec._get_workorders_with_wip().filtered(
                lambda w, key=to_key: (w.sequence, w.id) < key
            )
            rec.from_workorder_id = candidates[-1:]

    @api.onchange("production_id", "from_workorder_id", "to_workorder_id")
    def _onchange_default_move_qty(self):
        for rec in self:
            # Chỉ default ca khi tạo mới. Form record đã lưu là NewId bọc origin:
            # gán lại max+1 ở đây làm shift tăng mỗi lần save.
            if rec.to_workorder_id and not rec._origin.id:
                rec.shift = rec._get_next_shift()
            if not rec.move_qty:
                rec.move_qty = rec._get_remaining_qty()
                # Dòng vật tư phải khớp ngay với move_qty mặc định.
                if rec.move_qty and rec.production_id and rec.to_workorder_id:
                    rec.workorder_component_line_ids = rec._prepare_component_lines(
                        rec.move_qty
                    )

    @api.onchange("move_qty")
    def _onchange_move_qty(self):
        for rec in self:
            if rec.state == "approved" or not rec.move_qty:
                continue
            if not rec.production_id or not rec.to_workorder_id:
                continue
            rec.workorder_component_line_ids = rec._prepare_component_lines(
                rec.move_qty
            )

    def _prepare_component_lines(self, qty):
        """Dòng vật tư của công đoạn (to_workorder_id) scale theo BoM cho ``qty``.

        Dùng lại ``bom._compute_scaled_components`` — chính là hàm YCCP đang
        dùng để tính qty_planned — nên planned_qty luôn nhất quán với BoM.
        ``actual_qty`` default = planned_qty, user chỉnh tự do sau đó.
        """
        self.ensure_one()
        mo = self.production_id
        if not mo or not self.to_workorder_id or not mo.bom_id:
            return [Command.clear()]
        cmp_request = self.env["ps.mfg.component.request"].search(
            [("production_id", "=", mo.id), ("state", "!=", "cancelled")], limit=1
        )
        if not cmp_request:
            raise ValidationError(
                _("No component request found for the selected production order.")
            )
        wo_map = {w.routing_id.id: w.id for w in mo.workorder_ids if w.routing_id}
        company = self.company_id or self.env.company
        vals_list = [Command.clear()]
        for line in mo.bom_id._compute_scaled_components(
            mo.product_id, qty, mo.product_uom_id
        ):
            if wo_map.get(line["operation_id"]) != self.to_workorder_id.id:
                continue
            planned = line["qty_planned"]
            product = self.env["product.product"].browse(line["product_id"])
            line_vals = {
                "component_id": line["product_id"],
                "planned_qty": planned,
                "actual_qty": planned,  # Default actual quantity to planned quantity
                "uom_id": line["product_uom_id"],
                "price_unit": product.with_company(company).standard_price or 0.0,
            }
            if product.tracking == "lot":
                line_vals["lot_line_ids"] = [Command.create({"qty": planned})]
            vals_list.append(Command.create(line_vals))
        return vals_list

    @api.depends("production_id", "to_workorder_id")
    def _compute_component_line_ids(self):
        for rec in self:
            if not rec.production_id or not rec.to_workorder_id:
                rec.workorder_component_line_ids = [Command.clear()]
                continue
            if (
                rec.workorder_component_line_ids
                and rec.production_id == rec._origin.production_id
                and rec.to_workorder_id == rec._origin.to_workorder_id
            ):
                continue  # No change in production_id or to_workorder_id, skip recomputation
            # planned_qty scale theo move_qty (hoặc full SL hiện có từ CĐ trước:
            # CĐ đầu lấy theo YCCP, CĐ sau theo output approved của from).
            rec.workorder_component_line_ids = rec._prepare_component_lines(
                rec.move_qty or rec._get_remaining_qty()
            )

    @api.constrains("from_workorder_id", "to_workorder_id")
    def _check_workorder_move(self):
        for rec in self:
            if (
                rec.from_workorder_id
                and rec.to_workorder_id
                and rec.from_workorder_id == rec.to_workorder_id
            ):
                raise ValidationError(
                    _("The 'From Work Order' and 'To Work Order' cannot be the same.")
                )
            if not rec.to_workorder_id:
                continue
            if rec.from_workorder_id:
                # (sequence, id) là thứ tự của _order.
                if (rec.from_workorder_id.sequence, rec.from_workorder_id.id) > (
                    rec.to_workorder_id.sequence,
                    rec.to_workorder_id.id,
                ):
                    raise ValidationError(
                        _("The 'From Work Order' must come before the 'To Work Order'.")
                    )
            elif rec.to_workorder_id != rec._get_first_workorder():
                raise ValidationError(
                    _(
                        "Only the first work order can receive from 'Start'. "
                        "Select the preceding work order in 'From Work Order'."
                    )
                )

    @api.constrains(
        "move_qty", "shift", "production_id", "from_workorder_id", "to_workorder_id"
    )
    def _check_move_qty(self):
        for rec in self:
            if rec.state == "rejected":
                continue
            if not rec.move_qty:
                continue
            remaining = rec._get_remaining_qty()
            if rec.move_qty > remaining:
                available = rec._get_available_qty()
                raise ValidationError(
                    _(
                        "The 'Move Quantity' (%(move)s) cannot exceed the remaining quantity (%(remaining)s) "
                        "for this shift (available for work order based on received materials/upstream: %(available)s).",
                        move=rec.move_qty,
                        remaining=remaining,
                        available=available,
                    )
                )

    @api.onchange("production_id")
    def _onchange_production_id(self):
        self.from_workorder_id = False
        self.to_workorder_id = False

    @api.onchange("workcenter_id")
    def _onchange_workcenter_id(self):
        if (
            self.production_id
            and self.production_id.workcenter_id != self.workcenter_id
        ):
            self.production_id = False

    @api.constrains("workcenter_id", "production_id")
    def _check_workcenter_production(self):
        for rec in self:
            if (
                rec.production_id
                and rec.production_id.workcenter_id != rec.workcenter_id
            ):
                raise ValidationError(
                    _(
                        "Manufacturing order %(mo)s does not belong to work center %(wc)s.",
                        mo=rec.production_id.display_name,
                        wc=rec.workcenter_id.display_name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        # Import / code cũ không truyền xưởng: lấy theo MO
        for vals in vals_list:
            if not vals.get("workcenter_id") and vals.get("production_id"):
                production = self.env["ps.mfg.production"].browse(vals["production_id"])
                vals["workcenter_id"] = production.workcenter_id.id
        return super().create(vals_list)

    def _get_workorders_with_wip(self):
        """Công đoạn đã hoàn thành và còn bán thành phẩm (WIP) chưa chuyển đi.

        WIP = total_qty (ca đã duyệt vào công đoạn) - SL các ca chuyển đi từ công
        đoạn này (trừ rejected, trừ chính ca đang mở).
        """
        self.ensure_one()
        workorders = self._get_production_workorders()
        if not workorders:
            return workorders
        domain = [
            ("production_id", "=", self.production_id.id),
            ("from_workorder_id", "in", workorders.ids),
            ("state", "!=", "rejected"),
        ]
        if self._origin.id:
            domain.append(("id", "!=", self._origin.id))
        groups = self.env["ps.mfg.workorder.move"]._read_group(
            domain, ["from_workorder_id"], ["move_qty:sum"]
        )
        outgoing_qty = {workorder.id: qty for workorder, qty in groups}
        uom = self.production_id.product_uom_id
        return workorders.filtered(
            lambda w: uom.compare(w.total_qty - outgoing_qty.get(w.id, 0.0), 0.0) > 0
        )

    @api.depends("production_id", "production_id.workorder_ids.total_qty")
    def _compute_allowed_to_workorder_ids(self):
        # Chọn "Đến công đoạn" trước. "Từ công đoạn" chỉ có thể là "Bắt đầu" (công
        # đoạn đầu) hoặc công đoạn còn WIP, nên chỉ cho chọn công đoạn đầu và các
        # công đoạn đứng sau một công đoạn còn WIP.
        for rec in self:
            if not rec.production_id:
                rec.allowed_to_workorder_ids = [Command.clear()]
                continue
            workorders = rec._get_production_workorders()
            wip_workorders = rec._get_workorders_with_wip()
            first_workorder = workorders[:1]
            if wip_workorders:
                min_key = min((w.sequence, w.id) for w in wip_workorders)
                allowed = workorders.filtered(
                    lambda w, first=first_workorder, key=min_key: (
                        w == first or (w.sequence, w.id) > key
                    )
                )
            else:
                allowed = first_workorder
            # Giữ giá trị đã lưu để mở lại ca cũ không lỗi domain.
            allowed |= rec._origin.to_workorder_id
            rec.allowed_to_workorder_ids = [Command.set(allowed.ids)]

    @api.depends(
        "production_id",
        "to_workorder_id",
        "production_id.workorder_ids.total_qty",
    )
    def _compute_allowed_from_workorder_ids(self):
        for rec in self:
            if not rec.production_id:
                rec.allowed_from_workorder_ids = [Command.clear()]
                continue
            workorders = rec._get_workorders_with_wip()
            if rec.to_workorder_id:
                # Chỉ các công đoạn đứng trước "Đến công đoạn".
                to_key = (rec.to_workorder_id.sequence, rec.to_workorder_id.id)
                workorders = workorders.filtered(lambda w: (w.sequence, w.id) < to_key)
            # Giữ giá trị đã lưu để mở lại ca cũ không lỗi domain.
            workorders |= rec._origin.from_workorder_id
            rec.allowed_from_workorder_ids = [Command.set(workorders.ids)]


class PsMfgWorkOrderMoveResource(models.Model):
    _name = "ps.mfg.workorder.move.resource"
    _description = "MFG Work Order Move Resource"
    _order = "sequence, id"
    _check_company_auto = True

    workorder_move_id = fields.Many2one(
        "ps.mfg.workorder.move",
        "Work Order Move",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        related="workorder_move_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        "Currency",
        related="workorder_move_id.currency_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer("Sequence", default=1)
    resource_id = fields.Many2one(
        "ps.mfg.resource", "Resource", required=True, check_company=True
    )
    cost_item_id = fields.Many2one(
        related="resource_id.cost_item_id", string="Cost Item", store=True
    )
    account_id = fields.Many2one(
        related="resource_id.account_id", string="Account", readonly=True
    )
    unit_cost = fields.Monetary(
        "Unit Cost",
        currency_field="currency_id",
        compute="_compute_unit_cost",
        store=True,
        readonly=True,
        help="Chi phí tài nguyên trên mỗi đơn vị thành phẩm "
        "(chi phí BoM / SL thành phẩm BoM), lấy từ công đoạn.",
    )
    planned_cost = fields.Monetary(
        "Planned Cost",
        currency_field="currency_id",
        compute="_compute_planned_cost",
        store=True,
        readonly=True,
        help="Định mức = đơn giá tài nguyên x SL chuyển (tham khảo).",
    )
    actual_cost = fields.Monetary(
        "Actual Cost",
        currency_field="currency_id",
        compute="_compute_actual_cost",
        store=True,
        readonly=False,
        help="Chi phí tài nguyên thực tế của ca. Mặc định = đơn giá x SL chuyển, "
        "có thể sửa tay.",
    )

    @api.depends("resource_id", "workorder_move_id.to_workorder_id")
    def _compute_unit_cost(self):
        for rec in self:
            if rec.workorder_move_id.state == "approved" and rec.id:
                continue
            wo_resource = rec.workorder_move_id.to_workorder_id.resource_ids.filtered(
                lambda r, res=rec.resource_id: r.resource_id == res
            )[:1]
            rec.unit_cost = wo_resource.unit_cost or 0.0

    @api.depends("unit_cost", "workorder_move_id.move_qty")
    def _compute_planned_cost(self):
        for rec in self:
            if rec.workorder_move_id.state == "approved" and rec.id:
                continue
            rec.planned_cost = rec.unit_cost * (rec.workorder_move_id.move_qty or 0.0)

    @api.depends("unit_cost", "workorder_move_id.move_qty")
    def _compute_actual_cost(self):
        for rec in self:
            if rec.workorder_move_id.state == "approved" and rec.id:
                continue
            rec.actual_cost = rec.unit_cost * (rec.workorder_move_id.move_qty or 0.0)

    @api.constrains("actual_cost")
    def _check_actual_cost(self):
        for rec in self:
            if rec.actual_cost < 0:
                raise ValidationError(_("Resource cost cannot be negative."))

    def _check_move_not_approved(self):
        if any(rec.workorder_move_id.state == "approved" for rec in self):
            raise ValidationError(
                _(
                    "Approved moves are locked to preserve quantity/amount history. "
                    "Create a new shift move to adjust."
                )
            )

    def write(self, vals):
        self._check_move_not_approved()
        return super().write(vals)

    def unlink(self):
        self._check_move_not_approved()
        return super().unlink()


class PsMfgWorkOrderMoveLineLotMixin(models.AbstractModel):
    _name = "ps.mfg.workorder.move.line.lot.mixin"
    _description = "Work Order Move Line Lot Mixin"

    component_id = fields.Many2one("product.product", "Component")
    company_id = fields.Many2one("res.company", "Company")
    location_id = fields.Many2one("stock.location", "Location")
    actual_qty = fields.Float("Actual Quantity")
    tracking = fields.Selection(
        related="component_id.tracking",
        string="Tracking",
    )
    lot_line_ids = fields.One2many(
        "ps.mfg.workorder.move.lot",
        "component_line_id",
        "Lot / Serial",
    )
    allowed_lot_ids = fields.Many2many(
        "stock.lot",
        compute="_compute_allowed_lot_ids",
        string="Available Lot/Serial Numbers",
        help="Lots with available quantity at the workshop location.",
    )
    lot_ids = fields.Many2many(
        "stock.lot",
        string="Lot/Serial Numbers",
        compute="_compute_lot_ids",
        inverse="_set_lot_ids",
        readonly=False,
        domain="[('id', 'in', allowed_lot_ids)]",
    )

    @api.depends("component_id", "location_id", "tracking")
    def _compute_allowed_lot_ids(self):
        Quant = self.env["stock.quant"]
        tracked = self.filtered(
            lambda r: (
                r.component_id and r.location_id and r.tracking in ("lot", "serial")
            )
        )
        (self - tracked).allowed_lot_ids = False
        if not tracked:
            return
        groups = Quant._read_group(
            [
                ("product_id", "in", tracked.component_id.ids),
                ("location_id", "in", tracked.location_id.ids),
                ("lot_id", "!=", False),
            ],
            groupby=["product_id", "location_id", "lot_id"],
            aggregates=["quantity:sum", "reserved_quantity:sum"],
        )
        lots_by_key = {}
        for product, location, lot, qty, reserved in groups:
            if not lot:
                continue
            if product.uom_id.compare((qty or 0.0) - (reserved or 0.0), 0.0) > 0:
                lots_by_key.setdefault((product.id, location.id), []).append(lot.id)
        for rec in tracked:
            rec.allowed_lot_ids = lots_by_key.get(
                (rec.component_id.id, rec.location_id.id), []
            )

    @api.depends("lot_line_ids.lot_id")
    def _compute_lot_ids(self):
        for rec in self:
            rec.lot_ids = rec.lot_line_ids.lot_id

    def _set_lot_ids(self):
        for rec in self:
            rec._apply_lot_ids(rec.lot_ids)

    def _apply_lot_ids(self, lots):
        self.ensure_one()
        if self.tracking == "none" or not self.tracking:
            self.lot_line_ids = [Command.clear()]
            return
        if self.tracking == "serial":
            self.lot_line_ids = [Command.clear()] + [
                Command.create({"lot_id": lot.id, "qty": 1.0}) for lot in lots
            ]
            self.actual_qty = float(len(lots))
            return
        qty_by_lot = {
            lot_line.lot_id.id: lot_line.qty
            for lot_line in self.lot_line_ids
            if lot_line.lot_id
        }
        kept = sum(qty_by_lot.get(lot.id, 0.0) for lot in lots if lot.id in qty_by_lot)
        remaining = (self.actual_qty or 0.0) - kept
        commands = [Command.clear()]
        dumped = False
        for lot in lots:
            if lot.id in qty_by_lot:
                qty = qty_by_lot[lot.id]
            elif not dumped:
                qty = remaining if remaining > 0 else 0.0
                dumped = True
            else:
                qty = 0.0
            commands.append(Command.create({"lot_id": lot.id, "qty": qty}))
        self.lot_line_ids = commands

    def _sync_default_lot_line(self):
        self.ensure_one()
        if self.tracking == "lot":
            self.lot_line_ids = [
                Command.clear(),
                Command.create({"qty": self.actual_qty or 0.0}),
            ]
        else:
            self.lot_line_ids = [Command.clear()]

    def action_show_lot_details(self):
        self.ensure_one()
        if not self._origin.id:
            raise UserError(_("Save the shift before opening lot/serial details."))
        xmlid = {
            "ps.mfg.workorder.move.line": "ps_mfg.ps_mfg_workorder_move_line_lot_form",
            "ps.mfg.workorder.move.extra.line": "ps_mfg.ps_mfg_workorder_move_extra_line_lot_form",
        }[self._name]
        view = self.env.ref(xmlid)
        return {
            "name": _("Lot/Serial Numbers"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": self._name,
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "res_id": self.id,
        }


class PsMfgWorkOrderMoveLine(models.Model):
    _name = "ps.mfg.workorder.move.line"
    _description = "MFG Work Order Move Line"
    _inherit = ["ps.mfg.workorder.move.line.lot.mixin"]
    _check_company_auto = True

    workorder_move_id = fields.Many2one(
        "ps.mfg.workorder.move", "Work Order Move", required=True, ondelete="cascade"
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        related="workorder_move_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        "Currency",
        compute="_compute_currency_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer("Sequence")
    component_id = fields.Many2one(
        "product.product", "Component", required=True, check_company=True
    )
    workorder_id = fields.Many2one(
        "ps.mfg.workorder",
        "Work Order",
        related="workorder_move_id.to_workorder_id",
        store=True,
        readonly=True,
    )
    planned_qty = fields.Float("Quantity", required=True, readonly=True)
    actual_qty = fields.Float("Actual Quantity", required=True)
    uom_id = fields.Many2one("uom.uom", "Unit of Measure", required=True)
    price_unit = fields.Monetary(
        "Unit Price",
        currency_field="currency_id",
        required=True,
        readonly=True,
        default=0.0,
        help="product.standard_price lúc Complete — cùng giá stock.move dùng khi xuất.",
    )
    amount = fields.Monetary(
        "Amount",
        currency_field="currency_id",
        compute="_compute_amount",
        store=True,
        help="ThanhTien dòng = actual_qty * price_unit.",
    )
    qty_variance_percent = fields.Float(
        "Variance %",
        digits=(16, 4),
        compute="_compute_qty_variance_percent",
        store=True,
        readonly=True,
        help="Phần trăm chênh lệch giữa SL thực tế và SL kế hoạch: (actual - planned) / planned.",
    )
    location_id = fields.Many2one(
        "stock.location",
        "Location",
        related="workorder_move_id.workcenter_id.location_id",
        store=True,
        readonly=True,
        help="Kho xưởng của lệnh sản xuất — nguồn NVL khi sản xuất tại công đoạn.",
    )
    lot_line_ids = fields.One2many(
        "ps.mfg.workorder.move.lot",
        "component_line_id",
        "Lot / Serial",
    )

    @api.depends("company_id")
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.company_id.currency_id or self.env.company.currency_id

    @api.depends("actual_qty", "price_unit")
    def _compute_amount(self):
        for rec in self:
            rec.amount = (rec.actual_qty or 0.0) * (rec.price_unit or 0.0)

    @api.depends("planned_qty", "actual_qty")
    def _compute_qty_variance_percent(self):
        for rec in self:
            if rec.planned_qty:
                rec.qty_variance_percent = (
                    (rec.actual_qty or 0.0) - rec.planned_qty
                ) / rec.planned_qty
            else:
                rec.qty_variance_percent = 0.0

    @api.onchange("component_id")
    def _onchange_component_id(self):
        for rec in self:
            if rec.component_id:
                company = rec.company_id or self.env.company
                rec.price_unit = (
                    rec.component_id.with_company(company).standard_price or 0.0
                )
                if not rec.uom_id:
                    rec.uom_id = rec.component_id.uom_id
            rec._sync_default_lot_line()

    @api.onchange("actual_qty")
    def _onchange_actual_qty_lot(self):
        for rec in self:
            if rec.tracking == "lot" and len(rec.lot_line_ids) == 1:
                rec.lot_line_ids.qty = rec.actual_qty or 0.0

    def write(self, vals):
        if any(rec.workorder_move_id.state == "approved" for rec in self):
            raise ValidationError(
                _(
                    "Approved moves are locked to preserve quantity/amount history. "
                    "Create a new shift move to adjust."
                )
            )
        return super().write(vals)

    def unlink(self):
        if any(rec.workorder_move_id.state == "approved" for rec in self):
            raise ValidationError(
                _(
                    "Approved moves are locked to preserve quantity/amount history. "
                    "Create a new shift move to adjust."
                )
            )
        return super().unlink()


class PsMfgWorkOrderMoveExtraLine(models.Model):
    _name = "ps.mfg.workorder.move.extra.line"
    _description = "MFG Work Order Move Extra Line"
    _inherit = ["ps.mfg.workorder.move.line.lot.mixin"]
    _check_company_auto = True

    workorder_move_id = fields.Many2one(
        "ps.mfg.workorder.move", "Work Order Move", required=True, ondelete="cascade"
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        related="workorder_move_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        "Currency",
        compute="_compute_currency_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer("Sequence")
    component_id = fields.Many2one(
        "product.product", "Component", required=True, check_company=True
    )
    workorder_id = fields.Many2one(
        "ps.mfg.workorder",
        "Work Order",
        related="workorder_move_id.to_workorder_id",
        store=True,
        readonly=True,
    )
    actual_qty = fields.Float("Actual Quantity", required=True)
    uom_id = fields.Many2one("uom.uom", "Unit of Measure", required=True)
    price_unit = fields.Monetary(
        "Unit Price",
        currency_field="currency_id",
        required=True,
        readonly=True,
        default=0.0,
        help="product.standard_price lúc Complete — cùng giá stock.move dùng khi xuất.",
    )
    amount = fields.Monetary(
        "Amount",
        currency_field="currency_id",
        compute="_compute_amount",
        store=True,
        help="Thành tiền dòng = actual_qty * price_unit.",
    )
    location_id = fields.Many2one(
        "stock.location",
        "Location",
        related="workorder_move_id.workcenter_id.location_id",
        store=True,
        readonly=True,
        help="Kho xưởng của lệnh sản xuất — nguồn NVL khi sản xuất tại công đoạn.",
    )
    lot_line_ids = fields.One2many(
        "ps.mfg.workorder.move.lot",
        "extra_line_id",
        "Lot / Serial",
    )

    @api.depends("company_id")
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.company_id.currency_id or self.env.company.currency_id

    @api.depends("actual_qty", "price_unit")
    def _compute_amount(self):
        for rec in self:
            rec.amount = (rec.actual_qty or 0.0) * (rec.price_unit or 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            component_id = vals.get("component_id")
            if component_id:
                product = self.env["product.product"].browse(component_id)
                company = self.env.company
                if vals.get("workorder_move_id"):
                    company = (
                        self.env["ps.mfg.workorder.move"]
                        .browse(vals["workorder_move_id"])
                        .company_id
                        or company
                    )
                vals["price_unit"] = product.with_company(company).standard_price or 0.0
                if not vals.get("uom_id") and product.uom_id:
                    vals["uom_id"] = product.uom_id.id
                if product.tracking == "lot" and "lot_line_ids" not in vals:
                    vals["lot_line_ids"] = [
                        Command.create(
                            {
                                "qty": vals.get("actual_qty") or 0.0,
                            }
                        )
                    ]
        return super().create(vals_list)

    def write(self, vals):
        if any(rec.workorder_move_id.state == "approved" for rec in self):
            raise ValidationError(
                _(
                    "Approved moves are locked to preserve quantity/amount history. "
                    "Create a new shift move to adjust."
                )
            )
        if "component_id" in vals and vals.get("component_id"):
            product = self.env["product.product"].browse(vals["component_id"])
            company = self.company_id[:1] or self.env.company
            if vals.get("workorder_move_id"):
                company = (
                    self.env["ps.mfg.workorder.move"]
                    .browse(vals["workorder_move_id"])
                    .company_id
                    or company
                )
            vals["price_unit"] = product.with_company(company).standard_price or 0.0
        elif "price_unit" in vals and not self.env.context.get("ps_mfg_refresh_price"):
            vals.pop("price_unit")
        return super().write(vals)

    @api.onchange("component_id")
    def _onchange_component_id(self):
        for rec in self:
            if rec.component_id:
                rec.price_unit = (
                    rec.component_id.with_company(
                        rec.company_id or self.env.company
                    ).standard_price
                    or 0.0
                )
                if not rec.uom_id:
                    rec.uom_id = rec.component_id.uom_id
            rec._sync_default_lot_line()

    @api.onchange("actual_qty")
    def _onchange_actual_qty_lot(self):
        for rec in self:
            if rec.tracking == "lot" and len(rec.lot_line_ids) == 1:
                rec.lot_line_ids.qty = rec.actual_qty or 0.0

    def unlink(self):
        if any(rec.workorder_move_id.state == "approved" for rec in self):
            raise ValidationError(
                _(
                    "Approved moves are locked to preserve quantity/amount history. "
                    "Create a new shift move to adjust."
                )
            )
        return super().unlink()


class PsMfgWorkOrderMoveLot(models.Model):
    _name = "ps.mfg.workorder.move.lot"
    _description = "MFG Work Order Move Lot/Serial"
    _check_company_auto = True

    workorder_move_id = fields.Many2one(
        "ps.mfg.workorder.move",
        "Work Order Move",
        required=True,
        index=True,
        ondelete="cascade",
    )
    component_line_id = fields.Many2one(
        "ps.mfg.workorder.move.line",
        "Component Line",
        index=True,
        ondelete="cascade",
    )
    extra_line_id = fields.Many2one(
        "ps.mfg.workorder.move.extra.line",
        "Extra Component Line",
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        related="workorder_move_id.company_id",
        store=True,
        readonly=True,
    )
    component_id = fields.Many2one(
        "product.product",
        "Component",
        compute="_compute_component_id",
        store=True,
        readonly=True,
    )
    tracking = fields.Selection(
        related="component_id.tracking",
        string="Tracking",
    )
    allowed_lot_ids = fields.Many2many(
        "stock.lot",
        compute="_compute_allowed_lot_ids",
        string="Available Lot/Serial Numbers",
        help="Lots with available quantity at the workshop location.",
    )
    lot_id = fields.Many2one(
        "stock.lot",
        "Lot/Serial Number",
        check_company=True,
        domain="[('id', 'in', allowed_lot_ids)]",
    )
    qty = fields.Float("Quantity", required=True, default=0.0)

    @api.depends(
        "component_line_id.allowed_lot_ids",
        "extra_line_id.allowed_lot_ids",
    )
    def _compute_allowed_lot_ids(self):
        for rec in self:
            rec.allowed_lot_ids = (
                rec.component_line_id.allowed_lot_ids
                or rec.extra_line_id.allowed_lot_ids
            )

    @api.depends("component_line_id.component_id", "extra_line_id.component_id")
    def _compute_component_id(self):
        for rec in self:
            rec.component_id = (
                rec.component_line_id.component_id or rec.extra_line_id.component_id
            )

    @api.model_create_multi
    def create(self, vals_list):
        Line = self.env["ps.mfg.workorder.move.line"]
        Extra = self.env["ps.mfg.workorder.move.extra.line"]
        for vals in vals_list:
            if vals.get("workorder_move_id"):
                continue
            if vals.get("component_line_id"):
                vals["workorder_move_id"] = Line.browse(
                    vals["component_line_id"]
                ).workorder_move_id.id
            elif vals.get("extra_line_id"):
                vals["workorder_move_id"] = Extra.browse(
                    vals["extra_line_id"]
                ).workorder_move_id.id
        return super().create(vals_list)

    @api.onchange("component_line_id")
    def _onchange_component_line_id(self):
        for rec in self:
            if rec.component_line_id:
                rec.extra_line_id = False
                rec.workorder_move_id = rec.component_line_id.workorder_move_id
                if rec.tracking == "serial":
                    rec.qty = 1.0
                elif not rec.qty and rec.component_line_id.actual_qty:
                    rec.qty = rec.component_line_id.actual_qty

    @api.onchange("extra_line_id")
    def _onchange_extra_line_id(self):
        for rec in self:
            if rec.extra_line_id:
                rec.component_line_id = False
                rec.workorder_move_id = rec.extra_line_id.workorder_move_id
                if rec.tracking == "serial":
                    rec.qty = 1.0
                elif not rec.qty and rec.extra_line_id.actual_qty:
                    rec.qty = rec.extra_line_id.actual_qty

    @api.onchange("lot_id", "tracking")
    def _onchange_lot_serial_qty(self):
        for rec in self:
            if rec.tracking == "serial":
                rec.qty = 1.0

    @api.constrains("component_line_id", "extra_line_id")
    def _check_single_parent(self):
        for rec in self:
            if bool(rec.component_line_id) == bool(rec.extra_line_id):
                raise ValidationError(
                    _(
                        "A lot/serial line must belong to either a component line or an extra line."
                    )
                )

    @api.constrains("lot_id", "component_id")
    def _check_lot_product(self):
        for rec in self:
            if (
                rec.lot_id
                and rec.component_id
                and rec.lot_id.product_id != rec.component_id
            ):
                raise ValidationError(
                    _(
                        "Lot/serial %(lot)s does not belong to %(product)s.",
                        lot=rec.lot_id.display_name,
                        product=rec.component_id.display_name,
                    )
                )

    @api.constrains("component_id", "qty")
    def _check_serial_qty(self):
        for rec in self:
            if (
                rec.tracking == "serial"
                and rec.component_id.uom_id.compare(rec.qty or 0.0, 1.0) != 0
            ):
                raise ValidationError(
                    _(
                        "Serial number %(lot)s must have quantity 1.",
                        lot=rec.lot_id.display_name or rec.component_id.display_name,
                    )
                )

    @api.constrains("component_id")
    def _check_untracked_has_no_lot(self):
        for rec in self:
            if rec.component_id and rec.tracking == "none":
                raise ValidationError(
                    _(
                        "Product %(product)s is not tracked; remove its lot/serial lines.",
                        product=rec.component_id.display_name,
                    )
                )

    @api.constrains("component_line_id", "extra_line_id", "lot_id")
    def _check_unique_lot_on_parent(self):
        for rec in self:
            if not rec.lot_id:
                continue
            domain = [("id", "!=", rec.id), ("lot_id", "=", rec.lot_id.id)]
            if rec.component_line_id:
                domain.append(("component_line_id", "=", rec.component_line_id.id))
            elif rec.extra_line_id:
                domain.append(("extra_line_id", "=", rec.extra_line_id.id))
            else:
                continue
            if self.search_count(domain):
                raise ValidationError(
                    _(
                        "Lot/serial %(lot)s is already used on this line.",
                        lot=rec.lot_id.display_name,
                    )
                )

    @api.constrains("workorder_move_id", "lot_id", "component_id")
    def _check_unique_serial_on_move(self):
        for rec in self:
            if rec.tracking != "serial" or not rec.lot_id or not rec.workorder_move_id:
                continue
            dupes = self.search_count(
                [
                    ("id", "!=", rec.id),
                    ("workorder_move_id", "=", rec.workorder_move_id.id),
                    ("lot_id", "=", rec.lot_id.id),
                ]
            )
            if dupes:
                raise ValidationError(
                    _(
                        "Serial number %(lot)s is already used on this shift.",
                        lot=rec.lot_id.display_name,
                    )
                )

    def write(self, vals):
        if any(rec.workorder_move_id.state == "approved" for rec in self):
            raise ValidationError(
                _(
                    "Approved moves are locked to preserve quantity/amount history. "
                    "Create a new shift move to adjust."
                )
            )
        return super().write(vals)

    def unlink(self):
        if any(rec.workorder_move_id.state == "approved" for rec in self):
            raise ValidationError(
                _(
                    "Approved moves are locked to preserve quantity/amount history. "
                    "Create a new shift move to adjust."
                )
            )
        return super().unlink()
