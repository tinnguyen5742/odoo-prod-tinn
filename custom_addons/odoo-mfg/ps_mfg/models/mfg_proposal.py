from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command


class PsMfgProposal(models.Model):
    _name = "ps.mfg.proposal"
    _description = "MFG Proposal"
    _rec_name = "code"
    _check_company_auto = True
    _inherit = ["mail.thread"]

    code = fields.Char("Reference", default="New", copy=False, readonly=True)
    name = fields.Char(string="Proposal Name", required=True, tracking=True)
    description = fields.Html()
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
    proposal_date = fields.Date(
        required=True,
        tracking=True,
        default=fields.Date.context_today,
    )
    component_request_ids = fields.Many2many(
        "ps.mfg.component.request",
        "ps_mfg_proposal_request_rel",
        "proposal_id",
        "request_id",
        string="Component Requests",
        tracking=True,
        domain="[('state', 'in', ('pending', 'approved')), '|', ('has_remaining', '=', True), ('legacy_transfer', '=', True)]",
    )
    company_id = fields.Many2one(
        "res.company",
        compute="_compute_company_id",
        store=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        "ps.mfg.proposal.line",
        "proposal_id",
        string="Proposal Lines",
        copy=True,
    )
    component_line_ids = fields.Many2many(
        "ps.mfg.component.request.line",
        compute="_compute_component_line_ids",
        string="Components",
        readonly=True,
    )
    source_location_id = fields.Many2one(
        "stock.location", string="Component Storage", required=True, tracking=True
    )
    picking_ids = fields.Many2many(
        "stock.picking",
        "ps_mfg_proposal_picking_rel",
        "proposal_id",
        "picking_id",
        string="Internal Transfers",
        readonly=True,
        copy=False,
    )
    picking_count = fields.Integer(
        string="Transfer Count", compute="_compute_picking_count"
    )
    transfer_state = fields.Selection(
        [
            ("none", "No Transfer"),
            ("waiting", "Waiting Transfer"),
            ("in_transit", "In Transit"),
            ("done", "Transferred"),
            ("cancelled", "Cancelled"),
        ],
        string="Transfer Status",
        compute="_compute_transfer_state",
        store=True,
        tracking=True,
    )

    @api.depends("component_request_ids.company_id")
    def _compute_company_id(self):
        for rec in self:
            rec.company_id = (
                rec.component_request_ids[:1].company_id or self.env.company
            )

    @api.depends("line_ids.request_line_id")
    def _compute_component_line_ids(self):
        """Giữ tương thích ngược với các view/báo cáo truy xuất component_line_ids."""
        for rec in self:
            rec.component_line_ids = rec.line_ids.request_line_id

    @api.depends("picking_ids")
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    @api.depends("picking_ids.state")
    def _compute_transfer_state(self):
        for rec in self:
            pickings = rec.picking_ids
            if not pickings:
                rec.transfer_state = "none"
            elif all(p.state == "done" for p in pickings):
                rec.transfer_state = "done"
            elif all(p.state == "cancel" for p in pickings):
                rec.transfer_state = "cancelled"
            elif any(p.state == "done" for p in pickings):
                rec.transfer_state = "in_transit"
            else:
                rec.transfer_state = "waiting"

    @api.constrains("component_request_ids")
    def _check_requests_company(self):
        for rec in self:
            companies = rec.component_request_ids.company_id
            if len(companies) > 1:
                raise ValidationError(
                    self.env._(
                        "All component requests must belong to the same company."
                    )
                )

    @staticmethod
    def _first_request_id_from_vals(vals):
        commands = vals.get("component_request_ids")
        if not commands:
            return False
        ids = []
        for cmd in commands:
            if not cmd:
                continue
            opcode = cmd[0]
            if opcode in (Command.SET, 6) and cmd[2]:
                ids.extend(cmd[2])
            elif opcode in (Command.LINK, 4):
                ids.append(cmd[1])
        return ids[0] if ids else False

    def _sync_lines_from_requests(self):
        """Tự động đồng bộ các dòng vật tư cần cấp phát (line_ids) từ danh sách YCCP.
        - Loại bỏ các dòng của YCCP không còn được chọn.
        - Giữ nguyên số lượng qty_to_transfer người dùng đã nhập trên các dòng hiện tại.
        - Thêm mới các dòng còn thiếu (qty_to_propose > 0) với qty_to_transfer mặc định = qty_to_propose.
        """
        for proposal in self:
            requests = proposal.component_request_ids
            kept_lines = proposal.line_ids.filtered(
                lambda line, selected=requests: (
                    line.request_line_id.request_id in selected
                )
            )
            current_req_lines = kept_lines.mapped("request_line_id")
            new_cmds = (
                [Command.set(kept_lines.ids)] if kept_lines else [Command.clear()]
            )

            for req in proposal.component_request_ids:
                for req_line in req.component_line_ids:
                    if req_line not in current_req_lines:
                        # Với phiếu legacy lấy toàn bộ qty_planned, với phiếu mới lấy qty_to_propose
                        qty = (
                            req_line.qty_planned
                            if req.legacy_transfer
                            else req_line.qty_to_propose
                        )
                        if qty > 1e-4:
                            new_cmds.append(
                                Command.create(
                                    {
                                        "request_line_id": req_line.id,
                                        "qty_to_transfer": qty,
                                    }
                                )
                            )
            proposal.line_ids = new_cmds

    @api.onchange("component_request_ids")
    def _onchange_component_request_ids(self):
        self._sync_lines_from_requests()

    def action_load_remaining_lines(self):
        """Nút trên giao diện cho phép tải lại các dòng còn thiếu nếu có thay đổi từ kho."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(self.env._("Lines can only be refreshed in draft state."))
        self._sync_lines_from_requests()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", "New") == "New":
                sequence = False
                request_id = self._first_request_id_from_vals(vals)
                if request_id:
                    request = self.env["ps.mfg.component.request"].browse(request_id)
                    workcenter = request.production_id.workcenter_id
                    if workcenter and workcenter.receipt_request_sequence_id:
                        sequence = workcenter.receipt_request_sequence_id.next_by_id()
                vals["code"] = (
                    sequence
                    or self.env["ir.sequence"].next_by_code("ps.mfg.proposal")
                    or "New"
                )
        records = super().create(vals_list)
        # Nếu tạo proposal bằng code/test mà chỉ truyền component_request_ids (chưa có line_ids),
        # tự động tạo các dòng proposal_line để đảm bảo dữ liệu luôn đầy đủ.
        for rec in records:
            if not rec.line_ids and rec.component_request_ids:
                rec._sync_lines_from_requests()  # pylint: disable=protected-access
        return records

    def _require_requests(self):
        self.ensure_one()
        if not self.component_request_ids:
            raise UserError(self.env._("Select at least one component request."))

    def action_submit_approval(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(
                self.env._("Only draft proposals can be submitted for approval.")
            )
        self._require_requests()
        if not self.line_ids:
            self._sync_lines_from_requests()
        if not self.line_ids:
            raise UserError(self.env._("No component lines to transfer."))
        self.line_ids._check_qty_to_transfer()  # pylint: disable=protected-access
        self.state = "pending"

    def action_reject(self):
        self.ensure_one()
        if self.state not in ("draft", "pending"):
            raise UserError(
                self.env._("Only draft or pending proposals can be rejected.")
            )
        self.state = "rejected"

    def _group_lines_by_dest(self):
        """Gom nhóm các dòng đề xuất theo kho xưởng đích (destination_location_id).
        Mỗi kho xưởng đích sẽ sinh ra một phiếu chuyển kho (stock.picking) riêng.
        """
        self.ensure_one()
        groups = {}
        for line in self.line_ids:
            dest = line.destination_location_id
            if not dest:
                raise UserError(
                    self.env._(
                        "Component %(comp)s from request %(req)s has no destination location.",
                        comp=line.product_id.display_name,
                        req=line.request_id.display_name,
                    )
                )
            groups.setdefault(dest.id, self.env["ps.mfg.proposal.line"])
            groups[dest.id] |= line
        return groups

    def _mark_approved(self):
        self.ensure_one()
        self.state = "approved"
        for request in self.component_request_ids:
            if request.state in ("draft", "pending"):
                request.state = "approved"

    def action_approve(self):
        self.ensure_one()
        if self.state not in ("draft", "pending"):
            raise UserError(
                self.env._("Only draft or pending proposals can be approved.")
            )
        self._require_requests()

        if not self.line_ids:
            self._sync_lines_from_requests()
        if not self.line_ids:
            raise UserError(self.env._("No component lines to transfer."))
        if any(line.qty_to_transfer <= 0 for line in self.line_ids):
            raise UserError(
                self.env._("All component quantities must be strictly positive.")
            )
        if not self.source_location_id:
            raise UserError(self.env._("Source location is required."))

        # Kiểm tra chặt chẽ số lượng đề xuất không được vượt quá lượng còn thiếu tại thời điểm duyệt
        self.line_ids._check_qty_to_transfer()  # pylint: disable=protected-access

        if self.picking_ids:
            self._mark_approved()
            return

        groups = self._group_lines_by_dest()
        picking_type = self.env["stock.picking.type"].search(
            [
                ("code", "=", "internal"),
                ("company_id", "in", (self.company_id.id, False)),
            ],
            limit=1,
        )
        if not picking_type:
            raise UserError(self.env._("No internal operation type found."))

        pickings = self.env["stock.picking"]
        for dest_id, lines in groups.items():
            dest = self.env["stock.location"].browse(dest_id)
            if self.source_location_id == dest:
                raise UserError(
                    self.env._("Source and destination locations must be different.")
                )
            pickings |= self.env["stock.picking"].create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": self.source_location_id.id,
                    "location_dest_id": dest.id,
                    "origin": self.code,
                    "company_id": self.company_id.id,
                    "move_ids": [
                        Command.create(
                            {
                                "description_picking": line.product_id.display_name,
                                "product_id": line.product_id.id,
                                "product_uom_qty": line.qty_to_transfer,
                                "product_uom": line.product_uom_id.id,
                                "location_id": self.source_location_id.id,
                                "location_dest_id": dest.id,
                                "company_id": self.company_id.id,
                                # Nối trực tiếp stock.move với dòng YCCP và dòng Proposal
                                "component_request_line_id": line.request_line_id.id,
                                "proposal_line_id": line.id,
                            }
                        )
                        for line in lines
                    ],
                }
            )
        self.picking_ids = pickings
        self._mark_approved()

    def action_view_picking(self):
        self.ensure_one()
        count = len(self.picking_ids)
        if not count:
            return None
        action = {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form" if count == 1 else "list,form",
            "target": "current",
        }
        if count == 1:
            action["res_id"] = self.picking_ids.id
        else:
            action["name"] = self.env._("Transfers")
            action["domain"] = [("id", "in", self.picking_ids.ids)]
        return action


class PsMfgProposalLine(models.Model):
    _name = "ps.mfg.proposal.line"
    _description = "MFG Proposal Line"
    _rec_name = "product_id"

    proposal_id = fields.Many2one(
        "ps.mfg.proposal",
        required=True,
        ondelete="cascade",
        index=True,
    )
    request_line_id = fields.Many2one(
        "ps.mfg.component.request.line",
        string="Component Request Line",
        required=True,
        ondelete="restrict",
        index=True,
    )

    request_id = fields.Many2one(
        "ps.mfg.component.request",
        string="Component Request",
        related="request_line_id.request_id",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        related="request_line_id.product_id",
        store=True,
        readonly=True,
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        related="request_line_id.product_uom_id",
        store=True,
        readonly=True,
    )
    destination_location_id = fields.Many2one(
        "stock.location",
        string="Destination",
        related="request_line_id.destination_location_id",
        store=True,
        readonly=True,
    )
    workorder_id = fields.Many2one(
        "ps.mfg.workorder",
        string="Work Order",
        related="request_line_id.workorder_id",
        store=True,
        readonly=True,
    )
    workcenter_id = fields.Many2one(
        "ps.mfg.work.center",
        string="Work Center",
        related="request_line_id.workcenter_id",
        store=True,
        readonly=True,
    )

    # Các trường tham chiếu tiến độ cấp phát từ YCCP
    qty_planned = fields.Float(
        related="request_line_id.qty_planned", string="Planned Qty", readonly=True
    )
    qty_transferred = fields.Float(
        related="request_line_id.qty_transferred",
        string="Already Transferred",
        readonly=True,
    )
    qty_to_propose = fields.Float(
        related="request_line_id.qty_to_propose",
        string="Available to Propose",
        readonly=True,
    )

    # Số lượng thực tế xuất ở đợt chuyển này (người dùng có thể chỉnh sửa trong trạng thái draft)
    qty_to_transfer = fields.Float(string="Proposal Qty", required=True)

    move_ids = fields.One2many("stock.move", "proposal_line_id", string="Stock Moves")
    qty_done = fields.Float(
        string="Delivered Qty", compute="_compute_quantities", store=True
    )
    qty_open = fields.Float(
        string="Open Qty", compute="_compute_quantities", store=True
    )

    _sql_constraints = [
        (
            "unique_proposal_request_line",
            "UNIQUE(proposal_id, request_line_id)",
            "A component request line can only be added once per proposal!",
        ),
    ]

    @api.depends(
        "proposal_id.state",
        "qty_to_transfer",
        "product_uom_id",
        "move_ids.state",
        "move_ids.quantity",
        "move_ids.product_uom_qty",
        "move_ids.product_uom",
    )
    def _compute_quantities(self):
        """Tính toán trạng thái số lượng của dòng Proposal:
        - qty_done: Lượng đã thực chuyển xong từ các stock.move ở state='done'.
        - qty_open: Lượng đang 'giữ chỗ' hoặc đang vận chuyển:
          + Proposal ở pending (chờ duyệt): Toàn bộ qty_to_transfer.
          + Proposal ở approved: Tổng product_uom_qty của các move chưa done và chưa cancel
            (bao gồm cả backorder move nếu có).
          + Proposal ở draft/rejected: 0.0 (chưa giữ chỗ).
        """
        for line in self:
            state = line.proposal_id.state
            done_qty = sum(
                m.product_uom._compute_quantity(  # pylint: disable=protected-access
                    m.quantity, line.product_uom_id
                )
                for m in line.move_ids.filtered(lambda m: m.state == "done")
            )
            line.qty_done = done_qty

            if state == "pending":
                line.qty_open = line.qty_to_transfer
            elif state == "approved":
                pending_qty = sum(
                    m.product_uom._compute_quantity(  # pylint: disable=protected-access
                        m.product_uom_qty, line.product_uom_id
                    )
                    for m in line.move_ids.filtered(
                        lambda m: m.state not in ("done", "cancel")
                    )
                )
                line.qty_open = pending_qty
            else:
                line.qty_open = 0.0

    @api.constrains("qty_to_transfer", "proposal_id", "request_line_id")
    def _check_qty_to_transfer(self):
        for line in self:
            if line.qty_to_transfer <= 0:
                raise ValidationError(
                    self.env._("Proposal quantity must be strictly positive.")
                )
            req = line.request_id
            if req.legacy_transfer:
                continue

            # Tính lượng còn thiếu tối đa được phép đề xuất:
            # max_allowed = planned - transferred - (tổng open của các proposal line KHÁC)
            other_open = sum(
                other.qty_open
                for other in line.request_line_id.proposal_line_ids
                if other.id != line.id
            )
            max_allowed = max(
                0.0,
                line.request_line_id.qty_planned
                - line.request_line_id.qty_transferred
                - other_open,
            )
            if line.qty_to_transfer > max_allowed + 1e-4:
                raise ValidationError(
                    self.env._(
                        "Proposal quantity (%(qty)s) cannot exceed available remaining quantity (%(max_qty)s) "
                        "for component %(comp)s in request %(req)s.",
                        qty=line.qty_to_transfer,
                        max_qty=round(max_allowed, 4),
                        comp=line.product_id.display_name,
                        req=req.code,
                    )
                )
