from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

# Trạng thái YCCP bị khóa: không cho sửa header/dòng NVL
LOCKED_STATES = ("approved", "done", "cancelled")
# Trạng thái YCCP không cho hủy
NON_CANCELLABLE_STATES = ("approved", "done")
# Field header vẫn được ghi khi YCCP đã khóa (chuyển trạng thái nội bộ)
LOCK_ALLOWED_FIELDS = {"state", "legacy_transfer"}
# Field dòng NVL vẫn được ghi khi YCCP đã khóa (nhập SL lấy đợt này)
LINE_LOCK_ALLOWED_FIELDS = {"qty_to_pick"}


class PsMfgComponentRequest(models.Model):
    _name = "ps.mfg.component.request"
    _description = "MFG Move Order"
    _rec_name = "code"
    _check_company_auto = True
    _inherit = ["mail.thread"]

    production_id = fields.Many2one(
        "ps.mfg.production",
        string="Manufacturing Order",
        required=True,
        tracking=True,
        domain="[('state','=', 'confirmed')]",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="production_id.company_id",
        store=True,
        readonly=True,
    )
    code = fields.Char("Reference", default="New", copy=False, readonly=True)
    request_date = fields.Datetime(
        required=True, default=fields.Datetime.now, tracking=True
    )
    workcenter_id = fields.Many2one(
        "ps.mfg.work.center",
        "Work Center",
        related="production_id.workcenter_id",
        readonly=True,
        store=True,
    )
    destination_location_id = fields.Many2one(
        "stock.location",
        string="Destination",
        related="workcenter_id.location_id",
        readonly=True,
    )

    # Choose source location for the component request (no default, selected by user)
    location_id = fields.Many2one(
        "stock.location",
        string="Component Source",
        required=True,
        domain="[('usage', '=', 'internal')]",
        check_company=True,
        tracking=True,
    )

    product_qty = fields.Float(
        string="Product Quantity", default=0, required=True, tracking=True
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        readonly=True,
        default="draft",
        tracking=True,
    )
    component_line_ids = fields.One2many(
        "ps.mfg.component.request.line",
        "request_id",
        "Component Lines",
        compute="_compute_component_line_ids",
        store=True,
        precompute=True,
        # readonly=False bắt buộc: field precompute readonly bị ORM bỏ giá trị client gửi
        # khi create (models._prepare_create_values) → mất thay đổi dòng chưa lưu.
        # Việc khóa dòng do is_readonly (view) và _check_request_not_locked (server) đảm nhận.
        readonly=False,
    )
    proposal_ids = fields.Many2many(
        "ps.mfg.proposal",
        "ps_mfg_proposal_request_rel",
        "request_id",
        "proposal_id",
        string="Proposals",
    )
    proposal_count = fields.Integer(compute="_compute_proposal_count")
    is_readonly = fields.Boolean(
        string="Read Only", compute="_compute_is_readonly", store=True
    )

    # Multi-transfer support fields
    legacy_transfer = fields.Boolean(
        default=False,
        readonly=True,
        copy=False,
        help="True if this request was completed before multi-transfer support was introduced.",
    )
    transfer_status = fields.Selection(
        selection=[
            ("none", "Not Transferred"),
            ("partial", "Partially Transferred"),
            ("full", "Fully Transferred"),
        ],
        compute="_compute_transfer_status",
        store=True,
        tracking=True,
    )

    has_remaining = fields.Boolean(
        string="Has Remaining Components",
        compute="_compute_has_remaining",
        store=True,
        index=True,
        help="True if there is any component quantity still remaining to propose.",
    )

    picking_ids = fields.Many2many(
        "stock.picking",
        string="Transfers",
        compute="_compute_picking_ids",
        help="All internal transfers linked to this component request.",
    )
    picking_count = fields.Integer(
        string="Transfer Count", compute="_compute_picking_ids"
    )

    @api.constrains("location_id")
    def _check_source_diff_dest_location(self):
        for req in self:
            dest = req.destination_location_id
            if req.location_id and dest and req.location_id == dest:
                raise ValidationError(
                    req.env._(
                        "Source location (%(src)s) and workshop destination location (%(dest)s) cannot be the same.",
                        src=req.location_id.display_name,
                        dest=dest.display_name,
                    )
                )

    @api.depends("proposal_ids")
    def _compute_proposal_count(self):
        for req in self:
            req.proposal_count = len(req.proposal_ids)

    @api.depends("state")
    def _compute_is_readonly(self):
        for req in self:
            req.is_readonly = req.state in LOCKED_STATES

    @api.depends(
        "legacy_transfer",
        "state",
        "component_line_ids.qty_transferred",
        "component_line_ids.qty_planned",
    )
    def _compute_transfer_status(self):
        """Xác định trạng thái cấp phát vật tư của YCCP:
        - full: Tất cả dòng đã nhận đủ (qty_transferred >= qty_planned)
        - partial: Đã nhận được một phần (có dòng qty_transferred > 0)
        - none: Chưa chuyển tí nào
        """
        for req in self:
            if req.legacy_transfer:
                req.transfer_status = "full" if req.state == "done" else "none"
                continue
            if not req.component_line_ids:
                req.transfer_status = "none"
                continue
            # So sánh từng dòng với sai số làm tròn 1e-4
            is_full = all(
                line.qty_transferred >= (line.qty_planned - 1e-4)
                for line in req.component_line_ids
            )
            has_transferred = any(
                line.qty_transferred > 1e-4 for line in req.component_line_ids
            )
            if is_full:
                req.transfer_status = "full"
            elif has_transferred:
                req.transfer_status = "partial"
            else:
                req.transfer_status = "none"

    @api.depends("legacy_transfer", "state", "component_line_ids.qty_to_propose")
    def _compute_has_remaining(self):
        """Xác định YCCP còn NVL để tạo Proposal tiếp hay không.
        Chỉ những YCCP còn NVL (qty_to_propose > 0) và ở trạng thái approved mới hiện ở domain Proposal.
        """
        for req in self:
            if req.legacy_transfer or req.state in ("done", "cancelled"):
                req.has_remaining = False
            else:
                req.has_remaining = any(
                    line.qty_to_propose > 1e-4 for line in req.component_line_ids
                )

    @api.depends("component_line_ids.move_ids.picking_id", "proposal_ids.picking_ids")
    def _compute_picking_ids(self):
        for req in self:
            # Gom cả pickings đi qua move cấp dòng và pickings liên kết qua proposal (cho cả phiếu cũ và mới)
            pickings = (
                req.component_line_ids.move_ids.picking_id
                | req.proposal_ids.picking_ids
            )
            req.picking_ids = pickings
            req.picking_count = len(pickings)

    @api.onchange("production_id")
    def _onchange_production_id(self):
        if self.production_id and not self.product_qty:
            self.product_qty = self.production_id.product_qty

    @api.depends("production_id", "production_id.bom_id", "product_qty", "location_id")
    def _compute_component_line_ids(self):
        for req in self:
            # YCCP đã khóa (duyệt/hoàn thành/hủy): giữ nguyên dòng NVL, kể cả khi MO/BOM thay đổi
            if req.state in LOCKED_STATES:
                continue
            mo = req.production_id
            if not mo or not mo.bom_id:
                req.component_line_ids = [Command.clear()]
                continue
            # QUAN TRỌNG: Nếu đã có đề xuất/chuyển kho (move_ids hoặc proposal_line_ids),
            # TUYỆT ĐỐI không xóa và tạo lại dòng component_line_ids vì sẽ làm mất liên kết FK và lịch sử cấp phát.
            has_linked = any(
                line.move_ids or line.proposal_line_ids
                for line in req.component_line_ids
            )
            if has_linked:
                continue

            wo_map = {w.routing_id.id: w.id for w in mo.workorder_ids if w.routing_id}
            vals_list = mo.bom_id._compute_scaled_components(  # pylint: disable=protected-access
                mo.product_id, req.product_qty, mo.product_uom_id
            )
            req.component_line_ids = [Command.clear()] + [
                Command.create(
                    {
                        "product_id": line["product_id"],
                        "sequence": line["sequence"],
                        "qty_planned": line["qty_planned"],
                        "qty_bom": line["qty_bom"],
                        "is_from_bom": True,
                        "product_uom_id": line["product_uom_id"],
                        "workorder_id": wo_map.get(line["operation_id"], False),
                        "location_id": req.location_id.id if req.location_id else False,
                        "company_id": req.company_id.id if req.company_id else False,
                    }
                )
                for line in vals_list
            ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", "New") in (False, "New"):
                sequence = False
                if vals.get("production_id"):
                    prod = self.env["ps.mfg.production"].browse(vals["production_id"])
                    if prod and prod.workcenter_id:
                        sequence = (
                            prod.workcenter_id.comp_request_sequence_id.next_by_id()
                        )
                vals["code"] = (
                    sequence
                    or self.env["ir.sequence"].next_by_code("ps.mfg.component.request")
                    or "New"
                )
                if vals.get("product_qty") and vals.get("production_id"):
                    self._update_production_qty(
                        vals["product_qty"], vals["production_id"]
                    )
        return super().create(vals_list)

    def _check_locked_write(self, vals):
        """Chặn sửa YCCP đã duyệt/hoàn thành/hủy và chặn hủy YCCP đã duyệt."""
        if vals.get("state") == "cancelled":
            blocked = self.filtered(lambda r: r.state in NON_CANCELLABLE_STATES)
            if blocked:
                raise UserError(
                    self.env._(
                        "Approved or done component requests cannot be cancelled: %s",
                        ", ".join(blocked.mapped("code")),
                    )
                )
        locked_fields = [
            fname
            for fname in vals
            if fname not in LOCK_ALLOWED_FIELDS
            and not fname.startswith(("message_", "activity_"))
        ]
        if not locked_fields:
            return
        locked = self.filtered(lambda r: r.state in LOCKED_STATES)
        if locked:
            raise UserError(
                self.env._(
                    "Component request %s is approved, done or cancelled and can no longer be modified.",
                    ", ".join(locked.mapped("code")),
                )
            )

    def write(self, vals):
        self._check_locked_write(vals)
        if "product_qty" in vals:
            for req in self:
                # Chặn thay đổi sản lượng MO/YCCP nếu đã có phiếu chuyển hoặc đề xuất đang mở
                has_linked = any(
                    line.move_ids or line.proposal_line_ids
                    for line in req.component_line_ids
                )
                if has_linked:
                    raise UserError(
                        req.env._(
                            "Cannot modify product quantity after material transfers or proposals have been initiated "
                            "for component request %s.",
                            req.code,
                        )
                    )
        res = super().write(vals)
        if "product_qty" in vals:
            for req in self:
                if req.production_id:
                    self._update_production_qty(
                        vals["product_qty"], req.production_id.id
                    )
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_approved(self):
        blocked = self.filtered(lambda r: r.state in NON_CANCELLABLE_STATES)
        if blocked:
            raise UserError(
                self.env._(
                    "Approved or done component requests cannot be deleted: %s",
                    ", ".join(blocked.mapped("code")),
                )
            )

    def action_submit_approval(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(
                self.env._(
                    "Only draft component requests can be submitted for approval (%s).",
                    self.code,
                )
            )
        self.write({"state": "pending"})

    def action_cancel(self):
        self.ensure_one()
        if self.state == "cancelled":
            return
        # Chặn sớm để báo lỗi rõ; _check_locked_write vẫn là chốt chặn ở write()
        if self.state in NON_CANCELLABLE_STATES:
            raise UserError(
                self.env._(
                    "Approved or done component requests cannot be cancelled: %s",
                    self.code,
                )
            )
        self.write({"state": "cancelled"})

    def action_approve(self):
        self.ensure_one()
        if self.state not in ("draft", "pending"):
            raise UserError(
                self.env._("Only draft or pending records can be approved.")
            )
        self.state = "approved"

    def _check_transfer_complete(self):
        """Kiểm tra điều kiện hoàn thành YCCP:
        Chỉ tự động chuyển state='done' khi TẤT CẢ các dòng NVL đã nhận đủ số lượng (transfer_status == 'full').
        """
        for req in self:
            if req.legacy_transfer:
                continue
            if req.state == "approved" and req.transfer_status == "full":
                req.state = "done"
                req.message_post(
                    body=req.env._(
                        "All requested components have been fully transferred to the workshop. Request marked as Done."
                    )
                )

    def action_force_done(self):
        """Đóng YCCP thủ công khi quản lý quyết định chấp nhận số lượng đã nhận,
        không tiếp tục tạo đề xuất cho lượng NVL còn thiếu.
        """
        self.ensure_one()
        if self.state != "approved":
            raise UserError(
                self.env._("Only approved component requests can be closed manually.")
            )
        # Không được đóng nếu còn proposal đang dở dang (pending hoặc approved mà picking chưa xong)
        active_props = self.proposal_ids.filtered(
            lambda p: (
                p.state in ("pending", "approved")
                and p.transfer_state not in ("done", "cancelled")
            )
        )
        if active_props:
            raise UserError(
                self.env._(
                    "Cannot close component request %(req)s while proposals (%(proposals)s) are still active or in transit.",
                    req=self.code,
                    proposals=", ".join(active_props.mapped("code")),
                )
            )
        self.state = "done"
        self.message_post(
            body=self.env._(
                "Component request was manually closed. Remaining unsupplied components will not be proposed."
            )
        )

    def _get_producible_qty(self, workorder):
        """Tính sản lượng tối đa có thể sản xuất tại công đoạn `workorder`
        dựa trên tỷ lệ NVL đã thực nhận (qty_transferred / qty_planned).
        - Phiếu cũ (legacy_transfer): trả về self.product_qty.
        - YCCP chưa duyệt (draft/pending): trả về 0 — chưa được cấp NVL.
        - Chỉ dòng sinh từ BoM (is_from_bom) quyết định tỉ lệ; dòng thêm ngoài BoM bị bỏ qua.
        - Công đoạn không tiêu hao NVL BoM: trả về self.product_qty.
        """
        self.ensure_one()
        if self.legacy_transfer:
            return self.product_qty
        if not self.product_qty or self.state not in ("approved", "done"):
            return 0.0

        # Lấy các dòng NVL BoM thuộc về công đoạn này (nếu dòng không gán workorder_id thì mặc định thuộc CĐ đầu tiên)
        first_wo = self.production_id.workorder_ids[:1]
        relevant_lines = self.component_line_ids.filtered(
            lambda line: (
                line.is_from_bom
                and (
                    line.workorder_id == workorder
                    or (not line.workorder_id and workorder == first_wo)
                )
            )
        )
        if not relevant_lines:
            return self.product_qty

        # Tỷ lệ đáp ứng nhỏ nhất trong số các NVL của công đoạn
        ratios = [
            (line.qty_transferred / line.qty_planned) if line.qty_planned > 0 else 1.0
            for line in relevant_lines
        ]
        min_ratio = min(ratios) if ratios else 1.0
        return min(self.product_qty, round(self.product_qty * min_ratio, 4))

    @api.constrains("production_id", "state")
    def _check_production_unique_request(self):
        """1 MO chỉ có tối đa 1 YCCP hiệu lực (chưa cancel).

        YCCP đã cancel không tính → cancel xong được tạo mới.
        """
        for req in self:
            if req.state == "cancelled" or not req.production_id:
                continue
            dupes = self.search_count(
                [
                    ("production_id", "=", req.production_id.id),
                    ("state", "!=", "cancelled"),
                    ("id", "!=", req.id),
                ]
            )
            if dupes:
                raise ValidationError(
                    req.env._(
                        "Manufacturing order %(mo)s already has an effective component request. "
                        "Cancel it before creating a new one.",
                        mo=req.production_id.display_name,
                    )
                )

    def _update_production_qty(self, new_qty, production_id):
        prod = self.env["ps.mfg.production"].browse(production_id)
        if prod and prod.product_qty != new_qty:
            prod.product_qty = new_qty

    def action_create_proposal(self):
        self.ensure_one()
        if not self.has_remaining and not self.legacy_transfer:
            raise UserError(
                self.env._("All components have already been proposed or transferred.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Create Proposal"),
            "res_model": "ps.mfg.proposal",
            "view_mode": "form",
            "target": "current",
            "context": {"default_component_request_ids": [Command.set([self.id])]},
        }

    def action_open_pick_lines(self):
        """Mở danh sách dòng NVL group theo kho nguồn để chọn lấy NVL theo từng kho."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Pick Components - %s", self.code),
            "res_model": "ps.mfg.component.request.line",
            "view_mode": "list",
            "views": [
                (
                    self.env.ref(
                        "ps_mfg.ps_mfg_component_request_line_view_list_pick"
                    ).id,
                    "list",
                )
            ],
            "search_view_id": [
                self.env.ref("ps_mfg.ps_mfg_component_request_line_view_search_pick").id
            ],
            "domain": [("request_id", "=", self.id)],
            "context": {
                "search_default_remaining": 1,
                "search_default_group_location": 1,
                # Cho nút "In phiếu lấy NVL" biết YCCP khi không chọn dòng nào
                "pick_request_id": self.id,
            },
            "target": "current",
        }

    def action_view_proposals(self):
        self.ensure_one()
        if self.proposal_count == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "ps.mfg.proposal",
                "view_mode": "form",
                "res_id": self.proposal_ids.id,
                "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Proposals"),
            "res_model": "ps.mfg.proposal",
            "view_mode": "list,form",
            "domain": [("id", "in", self.proposal_ids.ids)],
            "target": "current",
        }

    def action_view_pickings(self):
        self.ensure_one()
        pickings = self.picking_ids
        if len(pickings) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "stock.picking",
                "view_mode": "form",
                "res_id": pickings.id,
                "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Transfers"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("id", "in", pickings.ids)],
            "target": "current",
        }


class PsMfgComponentRequestLine(models.Model):
    _name = "ps.mfg.component.request.line"
    _description = "MFG Component Request Line"
    _check_company_auto = True

    request_id = fields.Many2one(
        "ps.mfg.component.request",
        string="Component Request",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="request_id.company_id",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        domain="[('type', '=', 'consu')]",
        required=True,
    )
    sequence = fields.Integer()
    qty_planned = fields.Float(string="Planned Quantity", required=True, default=1.0)
    qty_bom = fields.Float(string="BOM Quantity", required=True, default=1.0)
    is_from_bom = fields.Boolean(
        string="From BoM",
        readonly=True,
        help="Line generated from the BoM of the Manufacturing Order.",
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        required=True,
        compute="_compute_product_uom",
        store=True,
        readonly=False,
    )
    workorder_id = fields.Many2one(
        "ps.mfg.workorder", string="Work Order", required=False
    )
    workcenter_id = fields.Many2one(
        "ps.mfg.work.center",
        string="Work Center",
        related="request_id.workcenter_id",
        store=True,
        readonly=True,
    )

    # Source location for this specific line (defaults from header request_id.location_id)
    location_id = fields.Many2one(
        "stock.location",
        string="Source Location",
        compute="_compute_location_id",
        store=True,
        readonly=False,
        precompute=True,
        required=True,
        domain="[('usage', '=', 'internal')]",
    )

    destination_location_id = fields.Many2one(
        "stock.location",
        string="Destination",
        related="request_id.workcenter_id.location_id",
        store=True,
        readonly=True,
    )

    # Multi-transfer tracking fields
    move_ids = fields.One2many(
        "stock.move", "component_request_line_id", string="Stock Moves"
    )
    proposal_line_ids = fields.One2many(
        "ps.mfg.proposal.line", "request_line_id", string="Proposal Lines"
    )

    qty_transferred = fields.Float(
        string="Transferred Quantity",
        compute="_compute_quantities",
        store=True,
        help="Actual quantity received at workshop (moves in done state minus returns).",
    )
    qty_open = fields.Float(
        string="Open Proposal Quantity",
        compute="_compute_quantities",
        store=True,
        help="Quantity currently reserved in pending proposals or in-transit pickings.",
    )
    qty_to_propose = fields.Float(
        string="Remaining to Propose",
        compute="_compute_quantities",
        store=True,
        help="Planned quantity minus transferred minus open proposals.",
    )
    qty_to_pick = fields.Float(
        string="Quantity to Pick",
        compute="_compute_qty_to_pick",
        store=True,
        readonly=False,
        help="Quantity to pick from the source location in the next transfer. "
        "Defaults to the remaining quantity.",
    )

    def _check_request_not_locked(self, requests):
        locked = requests.filtered(lambda r: r.state in LOCKED_STATES)
        if locked:
            raise UserError(
                self.env._(
                    "Component lines of request %s cannot be modified once it is approved, done or cancelled.",
                    ", ".join(locked.mapped("code")),
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        request_ids = {
            vals["request_id"] for vals in vals_list if vals.get("request_id")
        }
        self._check_request_not_locked(
            self.env["ps.mfg.component.request"].browse(request_ids)
        )
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) - LINE_LOCK_ALLOWED_FIELDS:
            self._check_request_not_locked(self.request_id)
        if vals.get("request_id"):
            self._check_request_not_locked(
                self.env["ps.mfg.component.request"].browse(vals["request_id"])
            )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_locked_request(self):
        self._check_request_not_locked(self.request_id)

    @api.depends("product_id")
    def _compute_product_uom(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id

    @api.constrains("location_id")
    def _check_source_diff_dest_location(self):
        for line in self:
            dest = line.destination_location_id
            if line.location_id and dest and line.location_id == dest:
                raise ValidationError(
                    line.env._(
                        "Line %(prod)s: Source location and workshop destination location cannot be the same.",
                        prod=line.product_id.display_name,
                    )
                )

    @api.depends("request_id.location_id")
    def _compute_location_id(self):
        for line in self:
            origin = getattr(line, "_origin", line)
            header_loc = line.request_id.location_id
            header_loc_changed = (
                origin.id
                and line.request_id
                and origin.request_id
                and header_loc != origin.request_id.location_id
            )
            if not line.location_id or header_loc_changed:
                line.location_id = header_loc

    @api.depends(
        "qty_planned",
        "product_uom_id",
        "request_id.legacy_transfer",
        "move_ids.state",
        "move_ids.quantity",
        "move_ids.product_uom",
        "move_ids.product_uom_qty",
        "move_ids.origin_returned_move_id",
        "proposal_line_ids.proposal_id.state",
        "proposal_line_ids.qty_to_transfer",
    )
    def _compute_quantities(self):
        """Tính toán bảo toàn số lượng:
        qty_planned = qty_transferred + qty_open + qty_to_propose
        - qty_transferred: Tổng move 'done' (trừ move trả hàng) quy đổi theo đơn vị của dòng.
        - qty_open: Lượng đang chờ chuyển = move xuất chưa done/cancel
          + proposal cũ còn ở trạng thái pending (chưa sinh move).
        - qty_to_propose: Lượng còn thiếu có thể tiếp tục lấy ở đợt mới.
        """
        for line in self:
            if line.request_id.legacy_transfer:
                line.qty_transferred = 0.0
                line.qty_open = 0.0
                line.qty_to_propose = 0.0
                continue

            transferred = 0.0
            for move in line.move_ids.filtered(lambda m: m.state == "done"):
                qty = move.product_uom._compute_quantity(  # pylint: disable=protected-access
                    move.quantity, line.product_uom_id
                )
                if move.origin_returned_move_id:
                    # Move trả hàng từ xưởng về kho làm giảm số lượng đã nhận
                    transferred -= qty
                else:
                    transferred += qty

            line.qty_transferred = max(0.0, transferred)
            pending_moves = line.move_ids.filtered(
                lambda m: (
                    m.state not in ("done", "cancel") and not m.origin_returned_move_id
                )
            )
            pending = sum(
                m.product_uom._compute_quantity(  # pylint: disable=protected-access
                    m.product_uom_qty, line.product_uom_id
                )
                for m in pending_moves
            )
            # Proposal đã gửi duyệt nhưng chưa duyệt: giữ chỗ toàn bộ SL đề xuất
            awaiting_approval = sum(
                line.proposal_line_ids.filtered(
                    lambda p: p.proposal_id.state == "pending"
                ).mapped("qty_to_transfer")
            )
            line.qty_open = pending + awaiting_approval
            line.qty_to_propose = max(
                0.0, line.qty_planned - line.qty_transferred - line.qty_open
            )

    @api.depends("qty_to_propose")
    def _compute_qty_to_pick(self):
        for line in self:
            line.qty_to_pick = line.qty_to_propose

    def _get_internal_picking_type(self, location):
        """Loại phiếu chuyển nội bộ của kho chứa `location`, fallback theo công ty."""
        picking_type = location.warehouse_id.int_type_id
        if not picking_type:
            picking_type = self.env["stock.picking.type"].search(
                [
                    ("code", "=", "internal"),
                    ("company_id", "in", (location.company_id.id, False)),
                ],
                limit=1,
            )
        if not picking_type:
            raise UserError(self.env._("No internal operation type found."))
        return picking_type

    def _check_pickable(self):
        for line in self:
            req = line.request_id
            if req.state != "approved" or req.legacy_transfer:
                raise UserError(
                    self.env._(
                        "Components can only be picked for approved component requests (%s).",
                        req.code,
                    )
                )
            if line.qty_to_pick > line.qty_to_propose + 1e-4:
                raise UserError(
                    self.env._(
                        "Quantity to pick (%(qty)s) cannot exceed the remaining quantity (%(max_qty)s) "
                        "for component %(comp)s in request %(req)s.",
                        qty=line.qty_to_pick,
                        max_qty=round(line.qty_to_propose, 4),
                        comp=line.product_id.display_name,
                        req=req.code,
                    )
                )
            if not line.destination_location_id:
                raise UserError(
                    self.env._(
                        "Component %(comp)s from request %(req)s has no destination location.",
                        comp=line.product_id.display_name,
                        req=req.code,
                    )
                )

    def _get_pick_report_action(self, pickings):
        # Mẫu phiếu không dùng external layout → bỏ qua wizard cấu hình layout công ty
        return (
            self.env.ref("ps_mfg.action_report_component_pick")
            .with_context(discard_logo_check=True)
            .report_action(pickings)
        )

    def action_print_pick_request(self):
        """In lại Phiếu yêu cầu lấy NVL: phiếu của các dòng được chọn,
        hoặc toàn bộ phiếu của YCCP khi không chọn dòng nào.
        """
        lines = self
        if not lines and self.env.context.get("pick_request_id"):
            lines = (
                self.env["ps.mfg.component.request"]
                .browse(self.env.context["pick_request_id"])
                .component_line_ids
            )
        pickings = lines.move_ids.picking_id.filtered(lambda p: p.state != "cancel")
        if not pickings:
            raise UserError(
                self.env._("No component pick transfers to print yet.")
            )
        if len(pickings) == 1:
            return self._get_pick_report_action(pickings)
        # Nhiều phiếu: mở danh sách phiếu để người dùng chọn phiếu cần in
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Select Transfers to Print"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "views": [
                (
                    self.env.ref("ps_mfg.stock_picking_view_list_component_pick").id,
                    "list",
                ),
                (False, "form"),
            ],
            "domain": [("id", "in", pickings.ids)],
            "context": {"create": False},
            "target": "current",
        }

    def action_create_pick_transfer(self):
        """Tạo phiếu chuyển kho nội bộ cho các dòng NVL được chọn (mỗi kho nguồn 1 phiếu)
        và in Phiếu yêu cầu lấy NVL.
        """
        lines = self.filtered(lambda rec: rec.qty_to_pick > 1e-4)
        if not lines:
            raise UserError(
                self.env._("Select at least one component with a quantity to pick.")
            )
        lines._check_pickable()  # pylint: disable=protected-access

        groups = {}
        for line in lines:
            key = (line.request_id, line.location_id)
            groups[key] = groups.get(key, self.browse()) | line

        pickings = self.env["stock.picking"]
        for (request, location), group_lines in groups.items():
            dest = request.destination_location_id
            picking = self.env["stock.picking"].create(
                {
                    "picking_type_id": self._get_internal_picking_type(location).id,
                    "location_id": location.id,
                    "location_dest_id": dest.id,
                    "origin": request.code,
                    "company_id": request.company_id.id,
                    "move_ids": [
                        Command.create(
                            {
                                "description_picking": line.product_id.display_name,
                                "product_id": line.product_id.id,
                                "product_uom_qty": line.qty_to_pick,
                                "product_uom": line.product_uom_id.id,
                                "location_id": location.id,
                                "location_dest_id": dest.id,
                                "company_id": request.company_id.id,
                                "component_request_line_id": line.id,
                            }
                        )
                        for line in group_lines
                    ],
                }
            )
            pickings |= picking
            request.message_post(
                body=self.env._(
                    "Transfer %(picking)s created to pick components from %(loc)s.",
                    picking=picking.name,
                    loc=location.display_name,
                )
            )
        pickings.action_confirm()
        return self._get_pick_report_action(pickings)
