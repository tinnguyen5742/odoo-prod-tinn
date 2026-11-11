from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PsMfgWorkOrder(models.Model):
    _name = "ps.mfg.workorder"
    _description = "Manufacturing Work Order"
    _order = "sequence, id"
    _check_company_auto = True
    _inherit = ["mail.thread"]

    production_id = fields.Many2one(
        "ps.mfg.production",
        "Production",
        required=True,
        tracking=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company", "Company", related="production_id.company_id", store=True
    )
    code = fields.Char("Code", required=True, tracking=True)
    name = fields.Char("Name", required=True, tracking=True)
    sequence = fields.Integer("Sequence", default=1)
    routing_id = fields.Many2one(
        "ps.mfg.routing", "Source Operation", readonly=True, tracking=True
    )
    operation_id = fields.Many2one(
        "ps.mfg.operation",
        "Operation",
        related="routing_id.operation_id",
        store=True,
        index=True,
    )
    workcenter_id = fields.Many2one(
        "ps.mfg.work.center", "Work Center", readonly=True, tracking=True
    )
    description = fields.Text("Description")
    currency_id = fields.Many2one(
        "res.currency",
        "Currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    move_ids = fields.One2many(
        "ps.mfg.workorder.move", "to_workorder_id", "Moves", readonly=True
    )
    resource_ids = fields.One2many(
        "ps.mfg.workorder.resource",
        "workorder_id",
        string="Resources",
    )
    total_qty = fields.Float(
        "Total Quantity",
        compute="_compute_totals",
        store=True,
        help="SoLuong công đoạn = sum move_qty các ca đã approved.",
    )
    material_amount = fields.Monetary(
        "Material Amount",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        help="ThanhTien NVL công đoạn = sum amount_total các ca đã approved.",
    )
    resource_amount = fields.Monetary(
        "Resource Amount",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        help="ThanhTien tài nguyên công đoạn = sum chi phí tài nguyên thực tế "
        "nhập trên các ca đã approved. Tab Resources của công đoạn chỉ là định mức.",
    )
    total_amount = fields.Monetary(
        "Total Amount",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        help="Chi phí riêng của công đoạn = material_amount + resource_amount.",
    )
    stage_unit_cost = fields.Monetary(
        "Operation Unit Cost",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        help="Chi phí riêng của công đoạn / SL công đoạn.",
    )
    transferred_in_cost = fields.Monetary(
        "Transferred-in Cost",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        help="Giá trị bán thành phẩm nhận từ công đoạn trước.",
    )
    total_cost = fields.Monetary(
        "Total Cost",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        help="Giá thành cộng dồn = transferred_in_cost + total_amount.",
    )
    unit_cost = fields.Monetary(
        "Unit Cost",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        help="Giá thành đơn vị cộng dồn của SL đầu ra công đoạn.",
    )
    consumed_lot_ids = fields.Many2many(
        "stock.lot",
        string="Consumed Lots / Serials",
        compute="_compute_consumed_lot_ids",
        help="Lots/serials consumed by approved shift moves into this work order.",
    )

    _work_order_code_unique = models.Constraint(
        "UNIQUE(production_id, code)",
        _(
            "The code of the work order must be unique within the same production order."
        ),
    )

    @api.depends(
        "move_ids.state",
        "move_ids.move_qty",
        "move_ids.amount_total",
        "move_ids.resource_amount",
        "move_ids.transferred_in_cost",
    )
    def _compute_totals(self):
        for wo in self:
            moves = wo.move_ids.filtered(lambda m: m.state == "approved")
            qty = sum(moves.mapped("move_qty"))
            wo.total_qty = qty
            wo.material_amount = sum(moves.mapped("amount_total"))
            wo.resource_amount = sum(moves.mapped("resource_amount"))
            wo.total_amount = wo.material_amount + wo.resource_amount
            wo.transferred_in_cost = sum(moves.mapped("transferred_in_cost"))
            wo.total_cost = wo.transferred_in_cost + wo.total_amount
            wo.stage_unit_cost = wo.total_amount / qty if qty else 0.0
            wo.unit_cost = wo.total_cost / qty if qty else 0.0

    @api.depends("move_ids.state", "move_ids.lot_line_ids.lot_id")
    def _compute_consumed_lot_ids(self):
        for wo in self:
            moves = wo.move_ids.filtered(lambda m: m.state == "approved")
            wo.consumed_lot_ids = moves.lot_line_ids.lot_id

    @api.onchange("routing_id")
    def _onchange_routing_id(self):
        for wo in self:
            if wo.routing_id and not wo.resource_ids:
                wo.resource_ids = [
                    fields.Command.create(
                        {
                            "resource_id": r.resource_id.id,
                            "planned_cost": r.resource_cost or 0.0,
                            "actual_cost": r.resource_cost or 0.0,
                        }
                    )
                    for r in wo.routing_id.resource_ids
                ]

    def action_create_workorder_move(self):
        """Mở form chuyển công đoạn, điền sẵn xưởng / lệnh SX / đến công đoạn."""
        self.ensure_one()
        if not self._origin.id:
            raise UserError(_("Please save the order before moving work orders."))
        wo = self._origin
        return {
            "name": _("Work Order Move"),
            "type": "ir.actions.act_window",
            "res_model": "ps.mfg.workorder.move",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
            "context": {
                "default_workcenter_id": wo.production_id.workcenter_id.id,
                "default_production_id": wo.production_id.id,
                "default_to_workorder_id": wo.id,
                "default_from_workorder_id": wo._get_previous_workorder().id,
                "ps_mfg_mo_show_product_name": 1,
            },
        }

    def _get_previous_workorder(self):
        """Công đoạn liền trước trong lệnh SX (rỗng nếu là công đoạn đầu)."""
        self.ensure_one()
        previous = self.search(
            [
                ("production_id", "=", self.production_id.id),
                "|",
                ("sequence", "<", self.sequence),
                "&",
                ("sequence", "=", self.sequence),
                ("id", "<", self.id),
            ],
            order="sequence desc, id desc",
            limit=1,
        )
        return previous

    def action_open_workorder(self):
        self.ensure_one()
        if not self._origin.id:
            raise UserError(
                _("Please save the order before opening work order details.")
            )
        view_id = self.env.ref("ps_mfg.ps_mfg_workorder_view_form").id
        return {
            "name": _("Work Order %s", self.code or self.name),
            "type": "ir.actions.act_window",
            "res_model": "ps.mfg.workorder",
            "res_id": self._origin.id,
            "view_mode": "form",
            "views": [(view_id, "form")],
            "target": "new",
            "context": {"create": False, "edit": False, "delete": False},
        }


class PsMfgWorkOrderResource(models.Model):
    _name = "ps.mfg.workorder.resource"
    _description = "Manufacturing Work Order Resource"
    _order = "sequence, id"
    _check_company_auto = True

    workorder_id = fields.Many2one(
        "ps.mfg.workorder",
        string="Work Order",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="workorder_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="workorder_id.currency_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer("Sequence", default=1)
    resource_id = fields.Many2one(
        "ps.mfg.resource", string="Resource", required=True, check_company=True
    )
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
    planned_cost = fields.Monetary(
        string="Planned Cost",
        currency_field="currency_id",
        default=0.0,
        help="Chi phí định mức snapshot từ Routing Resource khi tạo Work Order.",
    )
    actual_cost = fields.Monetary(
        string="Actual Cost",
        currency_field="currency_id",
        default=0.0,
        help="Chi phí thực tế của tài nguyên tại công đoạn này.",
    )
    unit_cost = fields.Monetary(
        string="Unit Cost",
        currency_field="currency_id",
        compute="_compute_unit_cost",
        store=True,
        readonly=False,
        help="Chi phí định mức trên mỗi đơn vị thành phẩm = "
        "chi phí nguồn lực BoM / SL thành phẩm BoM. "
        "Chốt khi tạo, không đổi theo BoM về sau.",
    )

    @api.depends("planned_cost")
    def _compute_unit_cost(self):
        for rec in self:
            bom_qty = rec.workorder_id.production_id.bom_id.product_qty or 1.0
            rec.unit_cost = (rec.planned_cost or 0.0) / bom_qty

    @api.onchange("resource_id")
    def _onchange_resource_id(self):
        for rec in self:
            if rec.resource_id and rec.workorder_id and rec.workorder_id.routing_id:
                routing_res = rec.workorder_id.routing_id.resource_ids.filtered(
                    lambda r: r.resource_id == rec.resource_id
                )[:1]
                if routing_res:
                    if not rec.planned_cost:
                        rec.planned_cost = routing_res.resource_cost or 0.0
                    if not rec.actual_cost:
                        rec.actual_cost = routing_res.resource_cost or 0.0
