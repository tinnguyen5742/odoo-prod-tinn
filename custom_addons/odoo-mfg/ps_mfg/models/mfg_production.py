from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class PsMfgProduction(models.Model):
    _name = "ps.mfg.production"
    _description = "Manufacturing Production"
    _rec_name = "code"
    _order = "id desc"
    _check_company_auto = True
    _inherit = ["mail.thread"]

    code = fields.Char("Reference", default="New", copy=False, readonly=True)
    company_id = fields.Many2one(
        "res.company", "Company", required=True, default=lambda self: self.env.company
    )
    product_id = fields.Many2one(
        "product.product",
        "Product",
        check_company=True,
        required=True,
        index=True,
        tracking=True,
        compute="_compute_product_id",
        store=True,
        copy=True,
        precompute=True,
        readonly=False,
    )
    product_tmpl_id = fields.Many2one(
        "product.template",
        "Product Template",
        related="product_id.product_tmpl_id",
        store=True,
    )
    product_qty = fields.Float(
        "Quantity To Produce", required=True, default=1.0, tracking=True
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        "Unit",
        required=True,
        compute="_compute_product_uom_id",
        store=True,
        copy=True,
        precompute=True,
        readonly=False,
    )
    qty_produced = fields.Float(
        "Quantity Produced", default=0.0, copy=False, tracking=True
    )
    bom_id = fields.Many2one(
        "ps.mfg.bom",
        "Bill of Materials",
        check_company=True,
        index=True,
        tracking=True,
        domain="""[
        '&',
            '|',
                ('company_id', '=', False),
                ('company_id', '=', company_id),
            '&',
                ('enabled', '=', True),
                '|',
                    ('product_id', '=', product_id),
                    '&',
                        ('product_tmpl_id.product_variant_ids', '=', product_id),
                        ('product_id', '=', False)]""",
        compute="_compute_bom_id",
        store=True,
        copy=True,
        precompute=True,
        readonly=False,
    )
    workcenter_id = fields.Many2one(
        "ps.mfg.work.center",
        "Work Center",
        required=True,
        check_company=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("in_progress", "In Progress"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        required=True,
        copy=False,
        index=True,
        tracking=True,
    )
    outdated_bom = fields.Boolean(
        "Outdated BoM", compute="_compute_outdated_bom", store=True
    )
    enabled = fields.Boolean("Enabled", default=True)
    date_planned = fields.Datetime("Planned Date", tracking=True)
    deadline_date = fields.Date("Delivery Deadline", tracking=True)
    order_date = fields.Date("Order Date")
    date_finished = fields.Datetime("Finished Date", copy=False)
    user_id = fields.Many2one(
        "res.users", "Responsible", default=lambda self: self.env.user, tracking=True
    )
    component_ids = fields.One2many(
        "ps.mfg.production.component",
        "production_id",
        "Components",
        copy=False,
        compute="_compute_component_ids",
        store=True,
        precompute=True,
    )
    workorder_ids = fields.One2many(
        "ps.mfg.workorder",
        "production_id",
        "Work Orders",
        copy=False,
        compute="_compute_workorder_ids",
        store=True,
        precompute=True,
    )
    component_request_ids = fields.One2many(
        "ps.mfg.component.request", "production_id", "Component Requests", copy=False
    )
    has_component_request = fields.Boolean(
        "Has Component Request",
        compute="_compute_component_request_stats",
        help="True when an effective (not cancelled) component request exists.",
    )
    component_request_count = fields.Integer(
        "Component Request Count",
        compute="_compute_component_request_stats",
        help="Number of effective (not cancelled) component requests.",
    )
    workorder_count = fields.Integer(
        "Work Order Count",
        compute="_compute_workorder_count",
        help="Number of work orders.",
    )
    all_workorders_done = fields.Boolean(
        "All Work Orders Done", compute="_compute_all_workorders_done", store=True
    )

    # Tolerance (ps_mrp parity: ± % with allowed min/max)
    tolerance_plus = fields.Float("Dung sai + (%)", digits=(16, 2), default=0.0)
    tolerance_minus = fields.Float("Dung sai - (%)", digits=(16, 2), default=0.0)
    qty_tolerance_min = fields.Float(
        "Min Allowed Qty",
        digits="Product Unit",
        compute="_compute_qty_tolerance_bounds",
        store=True,
    )
    qty_tolerance_max = fields.Float(
        "Max Allowed Qty",
        digits="Product Unit",
        compute="_compute_qty_tolerance_bounds",
        store=True,
    )

    sale_order_id = fields.Many2one("sale.order", "Sale Order", check_company=True)
    # Non-stored. The form uses them only to domain product and BoM.
    sale_product_ids = fields.Many2many(
        "product.product", string="SO Products", compute="_compute_sale_product_ids"
    )
    sale_product_tmpl_ids = fields.Many2many(
        "product.template",
        string="SO Product Templates",
        compute="_compute_sale_product_ids",
    )

    packaging_guideline_ids = fields.One2many(
        "ps.mfg.production.packaging.guideline",
        "production_id",
        "Packaging Guidelines",
        copy=True,
        auto_join=True,
        order="sequence, id",
    )

    ref_mo_group = fields.Char("Reference MO Group")
    customer_name = fields.Char("Customer")
    pokh_number = fields.Char("POKH Number")
    delivery_place = fields.Char("Delivery Place")
    caution = fields.Char("Caution")
    remark = fields.Char("Remark")
    tech_note = fields.Char("Technical Note")
    note = fields.Text("Note")

    @api.constrains("tolerance_plus", "tolerance_minus")
    def _check_tolerance_values(self):
        for mo in self:
            if mo.tolerance_plus < 0.0:
                raise ValidationError(_("The + tolerance (%) cannot be negative."))
            if mo.tolerance_minus < 0.0:
                raise ValidationError(_("The - tolerance (%) cannot be negative."))
            if mo.tolerance_minus > 100.0:
                raise ValidationError(
                    _("The - tolerance (%) cannot be greater than 100.")
                )

    @api.depends("code", "product_id.display_name")
    def _compute_display_name(self):
        show_product = self.env.context.get("ps_mfg_mo_show_product_name")
        for rec in self:
            if show_product and rec.code and rec.product_id:
                rec.display_name = f"[{rec.code}] {rec.product_id.display_name}"
            else:
                rec.display_name = rec.code or "New"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", "New") in (False, "New"):
                sequence = False
                if vals.get("workcenter_id"):
                    workcenter = self.env["ps.mfg.work.center"].browse(
                        vals["workcenter_id"]
                    )
                    if workcenter.mo_sequence_id:
                        sequence = workcenter.mo_sequence_id.next_by_id()
                vals["code"] = (
                    sequence
                    or self.env["ir.sequence"].next_by_code("ps.mfg.production")
                    or "New"
                )
            if "product_id" in vals and "product_uom_id" not in vals:
                vals["product_uom_id"] = (
                    self.env["product.product"].browse(vals["product_id"]).uom_id.id
                )
        recs = super().create(vals_list)
        # NOTE: component_ids/workorder_ids là stored compute + precompute nên
        # đã được tạo cùng lúc với MO (code thật đã có trong vals trước super).
        # KHÔNG gọi _rebuild_from_bom() ở đây: ghi đè compute-stored ngay sau
        # create gây clear/recompute vòng lặp làm mất dòng sau khi lưu.
        return recs

    def _latest_bom(self, product):
        if not product:
            return False
        return (
            self.env["ps.mfg.bom"]
            ._bom_find(
                product,
                company_id=self.company_id.id if self.company_id else False,
            )
            .get(product, False)
        )

    @api.depends("bom_id")
    def _compute_product_id(self):
        for mo in self:
            bom = mo.bom_id
            if bom and (
                not mo.product_id
                or bom.product_tmpl_id != mo.product_id.product_tmpl_id
                or (bom.product_id and bom.product_id != mo.product_id)
            ):
                mo.product_id = bom.product_id or bom.product_tmpl_id.product_variant_id

    @api.depends("product_id", "company_id")
    def _compute_bom_id(self):
        mo_by_company_id = defaultdict(lambda: self.env["ps.mfg.production"])
        for mo in self:
            if not mo.product_id and not mo.bom_id:
                mo.bom_id = False
                continue
            mo_by_company_id[mo.company_id.id] |= mo
        for company_id, productions in mo_by_company_id.items():
            boms_by_product = self.env["ps.mfg.bom"]._bom_find(
                productions.product_id, company_id=company_id
            )
            for mo in productions:
                if (
                    not mo.bom_id
                    or mo.bom_id.product_tmpl_id != mo.product_tmpl_id
                    or (mo.bom_id.product_id and mo.bom_id.product_id != mo.product_id)
                ):
                    bom = boms_by_product[mo.product_id]
                    mo.bom_id = bom.id or False
                    self.env.add_to_compute(mo._fields["product_uom_id"], mo)

    @api.depends("bom_id", "product_id")
    def _compute_product_uom_id(self):
        for mo in self:
            if mo.state != "draft":
                continue
            if mo.bom_id and mo._origin.bom_id != mo.bom_id:
                mo.product_uom_id = mo.bom_id.product_uom_id
            elif mo.product_id:
                mo.product_uom_id = mo.product_id.uom_id
            else:
                mo.product_uom_id = False

    def _sale_order_lines(self):
        """Order lines that can be manufactured: real products, not services."""
        self.ensure_one()
        order = self.sale_order_id
        if not order:
            return self.env["sale.order.line"]
        return order.order_line.filtered(
            lambda line: (
                line.product_id
                and not line.display_type
                and not line.is_downpayment
                and line.product_id.type != "service"
            )
        )

    def _sale_order_products(self):
        self.ensure_one()
        return self._sale_order_lines().product_id

    def _sale_order_qty(self, product):
        """Sum SO qty of ``product``, converted into the MO UoM."""
        self.ensure_one()
        lines = self._sale_order_lines().filtered(
            lambda line: line.product_id == product
        )
        target_uom = self.product_uom_id or product.uom_id
        qty = 0.0
        for line in lines:
            if line.product_uom_id and target_uom:
                qty += line.product_uom_id._compute_quantity(
                    line.product_uom_qty, target_uom
                )
            else:
                qty += line.product_uom_qty
        return qty

    def _recompute_bom_for_sale_product(self):
        # Assigning a field on a NewId protects dependent computes, so an
        # onchange that sets product_id would otherwise keep the old BoM.
        self.env.add_to_compute(self._fields["bom_id"], self)
        self.env.add_to_compute(self._fields["product_uom_id"], self)
        self.product_uom_id

    @api.depends(
        "sale_order_id",
        "sale_order_id.order_line.product_id",
        "sale_order_id.order_line.display_type",
        "sale_order_id.order_line.is_downpayment",
        "sale_order_id.order_line.product_id.type",
    )
    def _compute_sale_product_ids(self):
        empty_products = self.env["product.product"]
        for mo in self:
            products = mo._sale_order_products() if mo.sale_order_id else empty_products
            mo.sale_product_ids = products
            mo.sale_product_tmpl_ids = products.product_tmpl_id

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        if not self.sale_order_id:
            return
        self.customer_name = self.sale_order_id.partner_id.name
        products = self._sale_order_products()
        if len(products) == 1:
            product = products
        elif self.product_id in products:
            product = self.product_id
        else:
            product = self.env["product.product"]
        if product:
            self.product_id = product
            self._recompute_bom_for_sale_product()
            self.product_qty = self._sale_order_qty(self.product_id)
        elif self.product_id:
            self.product_id = False
            self._recompute_bom_for_sale_product()
            self.product_qty = 1.0

    @api.onchange("product_id")
    def _onchange_product_id_sale_qty(self):
        if not self.sale_order_id or not self.product_id:
            return
        if self.product_id not in self._sale_order_products():
            return
        self._recompute_bom_for_sale_product()
        self.product_qty = self._sale_order_qty(self.product_id)

    # NOTE: không cần onchange product_qty — _compute_component_ids đã
    # depends product_qty nên qty_planned tự cập nhật.

    @api.onchange("qty_produced", "qty_tolerance_max")
    def _onchange_qty_produced_tolerance(self):
        if (
            self.product_uom_id
            and self.qty_produced
            and self.product_uom_id.compare(self.qty_produced, self.qty_tolerance_max)
            > 0
        ):
            return {
                "warning": {
                    "title": _("Quantity exceeds tolerance"),
                    "message": _(
                        "Produced quantity is above the allowed maximum of %(max_qty)s "
                        "(planned %(planned)s with +%(plus)s%% tolerance).",
                        max_qty=self.qty_tolerance_max,
                        planned=self.product_qty,
                        plus=self.tolerance_plus,
                    ),
                }
            }

    def _get_direct_component_vals(self, product_qty):
        """Single-level BoM lines -> component vals (MO design: 1 tầng trực tiếp).

        Bán thành phẩm có BoM riêng vẫn là 1 dòng component, KHÔNG bung.
        Thin wrapper over ``ps.mfg.bom._compute_scaled_components``.
        workorder_id is resolved by PsMfgProductionComponent._compute_workorder_id.
        """
        self.ensure_one()
        if not self.bom_id or not self.product_id:
            return []
        return self.bom_id._compute_scaled_components(
            self.product_id, product_qty, self.product_uom_id
        )

    def _get_workorder_vals(self):
        """BoM operations -> workorder vals. Code = {MO}-{routing.seq:03d}.

        Trên form new record MO code='New' nên code tạm 'New-010'; sau
        create() có code thật, compute (depends code) ghi đè lại code chuẩn.
        Sequence copy nguyên routing.sequence. Trùng -> suffix '-2'.
        """
        self.ensure_one()
        if not self.bom_id:
            return []
        vals_list = []
        used_codes = set()
        for op in self.bom_id.operation_ids.sorted("sequence"):
            base_code = f"{self.code or 'New'}-{op.sequence or 0:03d}"
            code = base_code
            suffix = 2
            while code in used_codes:
                code = f"{base_code}-{suffix}"
                suffix += 1
            used_codes.add(code)
            resource_commands = [
                fields.Command.create(
                    {
                        "resource_id": r.resource_id.id,
                        "planned_cost": r.resource_cost or 0.0,
                        "actual_cost": r.resource_cost or 0.0,
                    }
                )
                for r in op.resource_ids
            ]
            vals_list.append(
                {
                    "code": code,
                    "routing_id": op.id,
                    "name": op.name,
                    "sequence": op.sequence,
                    "resource_ids": resource_commands,
                }
            )
        return vals_list

    def _rebuild_from_bom(self):
        for mo in self:
            if mo.state != "draft":
                continue
            if not mo.bom_id:
                mo.workorder_ids = [fields.Command.clear()]
                mo.component_ids = [fields.Command.clear()]
                continue
            mo.workorder_ids = [fields.Command.clear()] + [
                fields.Command.create(vals) for vals in mo._get_workorder_vals()
            ]
            # NOTE (single-level by design): MO chỉ lấy tầng trực tiếp của BoM.
            # Không dùng bom.explode() ở đây vì explode() luôn bung sub-BoM
            # (xem ps.mfg.bom.explode) — không phù hợp MO.
            # workorder_id của component do component tự compute từ operation_id
            # nên ở đây chỉ tạo component, không link WO thủ công.
            # Components reference workorders via workorder_id (SET NULL on
            # delete), so clearing them alongside workorders is FK-safe.
            mo.component_ids = [fields.Command.clear()]
            mo.component_ids = [
                fields.Command.create(vals)
                for vals in mo._get_direct_component_vals(mo.product_qty)
            ]

    @api.depends("state", "bom_id", "bom_id.operation_ids", "code")
    def _compute_workorder_ids(self):
        for mo in self:
            if mo.state != "draft":
                continue
            if not mo.bom_id:
                mo.workorder_ids = [fields.Command.clear()]
                continue
            mo.workorder_ids = [fields.Command.clear()] + [
                fields.Command.create(vals) for vals in mo._get_workorder_vals()
            ]

    @api.depends(
        "company_id",
        "product_id",
        "bom_id",
        "bom_id.bom_line_ids",
        "product_qty",
        "product_uom_id",
    )
    def _compute_component_ids(self):
        for mo in self:
            if mo.state not in ("draft", "confirmed"):
                continue
            if not mo.bom_id or not mo.product_id:
                mo.component_ids = [fields.Command.clear()]
                continue
            mo.component_ids = [fields.Command.clear()] + [
                fields.Command.create(vals)
                for vals in mo._get_direct_component_vals(mo.product_qty)
            ]
            # NOTE (future use — multi-level, GIỮ LẠI KHÔNG XÓA):
            # Đoạn explode() dưới đây bung toàn bộ sub-BoM thành leaf
            # (mọi BTP có BoM riêng đều bị flatten). Hữu ích sau này cho:
            #  - Báo cáo Nhu cầu vật tư tổng (gộp nhiều tầng),
            #  - Giá thành lăn (rolled-up cost).
            # MO single-level KHÔNG dùng — chỉ tính 1 tầng trực tiếp ở trên.
            # _boms_done, lines_done = mo.bom_id.explode(mo.product_id, mo.product_qty or 1.0)
            # for bom_line, line_data in lines_done:
            #     components.append(fields.Command.create({
            #         'product_id': bom_line.product_id.id,
            #         'product_uom_id': bom_line.product_uom_id.id,
            #         'qty_planned': line_data['qty'],
            #         'sequence': bom_line.sequence,
            #     }))

    @api.depends("product_id", "bom_id")
    def _compute_outdated_bom(self):
        for mo in self:
            if not mo.product_id:
                mo.outdated_bom = False
                continue
            latest = (
                self.env["ps.mfg.bom"]
                ._bom_find(mo.product_id)
                .get(mo.product_id, False)
            )
            mo.outdated_bom = bool(latest and mo.bom_id and latest.id != mo.bom_id.id)

    @api.depends("product_qty", "tolerance_plus", "tolerance_minus")
    def _compute_qty_tolerance_bounds(self):
        for mo in self:
            qty = mo.product_qty or 0.0
            mo.qty_tolerance_min = max(
                qty * (1.0 - (mo.tolerance_minus or 0.0) / 100.0), 0.0
            )
            mo.qty_tolerance_max = qty * (1.0 + (mo.tolerance_plus or 0.0) / 100.0)

    @api.depends("component_request_ids.state")
    def _compute_component_request_stats(self):
        for mo in self:
            effective = mo.component_request_ids.filtered(
                lambda r: r.state != "cancelled"
            )
            mo.has_component_request = bool(effective)
            mo.component_request_count = len(effective)

    @api.depends("workorder_ids")
    def _compute_workorder_count(self):
        for mo in self:
            mo.workorder_count = len(mo.workorder_ids)

    # NOTE: "Hoàn tất hết công đoạn" = mọi transition (YCCP→WO1, WO[i]→WO[i+1])
    # đều drain hết remaining: sum(move_qty approved của cặp from→to) == available,
    # với available theo đúng semantics của ps.mfg.workorder.move._get_available_qty.
    @api.depends(
        "state",
        "workorder_ids.sequence",
        "workorder_ids.move_ids.state",
        "workorder_ids.move_ids.move_qty",
        "workorder_ids.move_ids.from_workorder_id",
        "workorder_ids.move_ids.to_workorder_id",
        "component_request_ids.product_qty",
    )
    def _compute_all_workorders_done(self):
        for mo in self:
            wos = mo.workorder_ids.sorted("sequence")
            if mo.state != "in_progress" or not wos:
                mo.all_workorders_done = False
                continue
            qty_in = defaultdict(float)  # wo id -> tổng approved vào wo
            qty_pair = defaultdict(
                float
            )  # (from id | 0, to id) -> tổng approved của cặp
            for move in mo.workorder_ids.move_ids:
                if move.state != "approved":
                    continue
                qty_in[move.to_workorder_id.id] += move.move_qty
                qty_pair[(move.from_workorder_id.id or 0, move.to_workorder_id.id)] += (
                    move.move_qty
                )
            cmp_request = self.env["ps.mfg.component.request"].search(
                [("production_id", "=", mo.id), ("state", "!=", "cancelled")], limit=1
            )
            target = cmp_request.product_qty or 0.0
            if not target:
                mo.all_workorders_done = False
                continue
            done = True
            prev = self.env["ps.mfg.workorder"]
            for wo in wos:
                available = target if not prev else qty_in.get(prev.id, 0.0)
                moved = qty_pair.get((prev.id or 0, wo.id), 0.0)
                if float_compare(moved, available, precision_digits=6) < 0:
                    done = False
                    break
                prev = wo
            mo.all_workorders_done = done

    def _check_qty_produced_tolerance(self):
        for mo in self:
            if not mo.qty_produced or mo.product_uom_id.is_zero(mo.qty_produced):
                continue
            if mo.product_uom_id.compare(mo.qty_produced, mo.qty_tolerance_max) > 0:
                raise UserError(
                    _(
                        "Produced quantity %(qty)s exceeds the allowed maximum %(max_qty)s "
                        "(planned %(planned)s with +%(plus)s%% tolerance).",
                        qty=mo.qty_produced,
                        max_qty=mo.qty_tolerance_max,
                        planned=mo.product_qty,
                        plus=mo.tolerance_plus,
                    )
                )

    def action_confirm(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only draft manufacturing orders can be confirmed."))
        if not self.bom_id:
            raise UserError(_("Set a Bill of Materials before confirming."))
        self.state = "confirmed"

    def action_start(self):
        self.ensure_one()
        self.filtered(lambda m: m.state == "confirmed").write({"state": "in_progress"})

    def action_done(self):
        self.ensure_one()
        mo = self
        if mo.state not in ("confirmed", "in_progress"):
            raise UserError(
                _(
                    "Only confirmed or in-progress manufacturing orders can be marked as done."
                )
            )
        if not mo.qty_produced:
            mo.qty_produced = mo.product_qty
        mo._check_qty_produced_tolerance()
        mo.write({"state": "done", "date_finished": fields.Datetime.now()})

    def action_cancel(self):
        self.ensure_one()
        self.filtered(lambda m: m.state not in ("done",)).write({"state": "cancel"})

    def action_draft(self):
        self.ensure_one()
        self.filtered(lambda m: m.state == "cancel").write({"state": "draft"})

    def action_print_production_order(self):
        self.ensure_one()
        return self.env.ref("ps_mfg.action_report_ps_mfg_production").report_action(
            self
        )

    def action_create_component_request(self):
        """Mở form YCCP mới pre-fill từ MO (user soát/sửa rồi Save).

        Quan hệ 1-1 với YCCP hiệu lực: MO đã có request chưa cancel
        thì không tạo thêm. YCCP bị cancel vẫn được tạo mới.
        """
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(
                _(
                    "Component request can only be created from a confirmed manufacturing order."
                )
            )
        existing = self.component_request_ids.filtered(
            lambda r: r.state != "cancelled"
        )[:1]
        if existing:
            raise UserError(
                _(
                    "A component request (%(code)s) already exists for this manufacturing order.",
                    code=existing.code,
                )
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Component Request"),
            "res_model": "ps.mfg.component.request",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_production_id": self.id,
                "default_product_qty": self.product_qty,
            },
        }

    def action_view_component_requests(self):
        """Smart button: nhảy sang YCCP hiệu lực của MO.

        1-1 hiệu lực nên thực tế luôn mở thẳng form; nhánh list chỉ defensive.
        """
        self.ensure_one()
        effective = self.component_request_ids.filtered(
            lambda r: r.state != "cancelled"
        )
        if len(effective) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "ps.mfg.component.request",
                "view_mode": "form",
                "res_id": effective.id,
                "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Component Requests"),
            "res_model": "ps.mfg.component.request",
            "view_mode": "list,form",
            "domain": [("id", "in", effective.ids)],
            "target": "current",
        }

    def action_view_workorders(self):
        """Smart button: xem danh sách hoặc chi tiết Work Orders của MO."""
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": _("Work Orders"),
            "res_model": "ps.mfg.workorder",
            "target": "current",
        }
        if len(self.workorder_ids) == 1:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": self.workorder_ids.id,
                }
            )
        else:
            action.update(
                {
                    "view_mode": "list,form",
                    "domain": [("production_id", "=", self.id)],
                    "context": {"default_production_id": self.id},
                }
            )
        return action


class PsMfgProductionComponent(models.Model):
    _name = "ps.mfg.production.component"
    _description = "Manufacturing Production Component"
    _order = "sequence, id"
    _check_company_auto = True

    production_id = fields.Many2one(
        "ps.mfg.production", "Production", required=True, index=True, ondelete="cascade"
    )
    company_id = fields.Many2one(
        "res.company", "Company", related="production_id.company_id", store=True
    )
    product_id = fields.Many2one(
        "product.product", "Component", required=True, check_company=True
    )
    product_tmpl_id = fields.Many2one(
        "product.template", related="product_id.product_tmpl_id", store=True
    )
    product_uom_id = fields.Many2one("uom.uom", "Unit", required=True)
    qty_planned = fields.Float("Planned Qty", required=True, default=1.0)
    qty_bom = fields.Float("BOM Qty", required=True, default=1.0)
    operation_id = fields.Many2one(
        "ps.mfg.routing",
        "Operation",
        help="Công đoạn BoM mà nguyên liệu này thuộc về. Có ngay trên form; dùng để tìm Work Order tương ứng sau khi lưu.",
    )
    workorder_id = fields.Many2one(
        "ps.mfg.workorder",
        "Consumed in Work Order",
        compute="_compute_workorder_id",
        store=True,
        readonly=False,
        ondelete="set null",
        domain="[('production_id', '=', parent.id)]",
    )
    sequence = fields.Integer("Sequence", default=1)

    @api.depends("operation_id", "production_id.workorder_ids.routing_id")
    def _compute_workorder_id(self):
        """Link WO theo operation: parent cố link sibling NewId ở thời điểm
        precompute là bất khả thi (WO chưa có id thật) nên giá trị False bị
        persist vĩnh viễn. Compute đặt trên chính component thì Odoo tự
        recompute khi WO có id thật sau save."""
        for comp in self:
            if not comp.operation_id or not comp.production_id:
                comp.workorder_id = False
                continue
            wo = comp.production_id.workorder_ids.filtered(
                lambda w: w.routing_id.id == comp.operation_id.id
            )[:1]
            comp.workorder_id = wo.id if wo else False


class PsMfgProductionPackagingGuideline(models.Model):
    _name = "ps.mfg.production.packaging.guideline"
    _description = "Production Packaging Guideline"
    _order = "sequence, id"

    sequence = fields.Integer("Sequence", default=1)
    line_number = fields.Integer("Line Number", compute="_compute_line_number")
    production_id = fields.Many2one(
        "ps.mfg.production", "Manufacture Order", required=True
    )
    name = fields.Text("Guideline Name", required=True)
    guideline_content = fields.Text("Guideline Content", required=True)

    @api.depends(
        "production_id.packaging_guideline_ids",
        "production_id.packaging_guideline_ids.sequence",
    )
    def _compute_line_number(self):
        lines_by_production = defaultdict(
            lambda: self.env["ps.mfg.production.packaging.guideline"]
        )
        for line in self:
            if line.production_id:
                lines_by_production[line.production_id] |= line
            else:
                line.line_number = 1
        for production, lines in lines_by_production.items():
            sorted_lines = production.packaging_guideline_ids.sorted("sequence, id")
            index_by_id = {
                line.id: idx for idx, line in enumerate(sorted_lines, start=1)
            }
            for line in lines:
                line.line_number = index_by_id.get(line.id, 1)
