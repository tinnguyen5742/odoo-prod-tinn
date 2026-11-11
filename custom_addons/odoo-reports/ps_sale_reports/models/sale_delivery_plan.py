from odoo import api, fields, models
from odoo.exceptions import ValidationError


# PHẦN 15 - Kế hoạch giao hàng: dữ liệu đợt giao, quyền và xuất thực tế.
class SaleDeliveryPlan(models.Model):
    _name = "ps.sale.delivery.plan"
    _description = "Kế hoạch giao hàng"
    _order = "planned_datetime, order_id, sale_line_id, id"
    _check_company_auto = True

    sale_line_id = fields.Many2one("sale.order.line", string="Dòng SO", required=True, ondelete="restrict", check_company=True)
    order_id = fields.Many2one(related="sale_line_id.order_id", store=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True)
    product_id = fields.Many2one(related="sale_line_id.product_id", string="Sản phẩm")
    uom_id = fields.Many2one(related="sale_line_id.product_uom_id", string="ĐVT")
    planned_datetime = fields.Datetime("Dự kiến giao", required=True)
    planned_qty = fields.Float("SL dự kiến", required=True, digits="Product Unit")
    workshop = fields.Char("Phân xưởng")
    route = fields.Char("Tuyến đường")
    vehicle = fields.Char("Phương tiện vận chuyển")
    address = fields.Text("Địa chỉ giao", compute="_compute_address", store=True, readonly=False)
    note = fields.Text("Ghi chú")
    state = fields.Selection([("draft", "Dự kiến"), ("confirmed", "Đã xác nhận"), ("cancel", "Hủy")], default="draft", required=True)
    move_ids = fields.One2many("stock.move", "ps_delivery_plan_id", string="Dòng kho liên kết")

    @api.depends("order_id.partner_shipping_id")
    def _compute_address(self):
        for plan in self:
            plan.address = plan.order_id.partner_shipping_id._display_address(without_company=True)

    @api.depends("order_id.name", "product_id", "planned_datetime")
    def _compute_display_name(self):
        for plan in self:
            local = fields.Datetime.context_timestamp(plan, plan.planned_datetime) if plan.planned_datetime else None
            plan.display_name = "%s / %s / %s" % (plan.order_id.name or "", plan.product_id.display_name or "", local.strftime("%d/%m/%Y %H:%M") if local else "")

    @api.constrains("sale_line_id", "planned_qty", "state")
    def _check_plan(self):
        for plan in self:
            if plan.planned_qty <= 0:
                raise ValidationError("Số lượng dự kiến phải lớn hơn 0, theo ĐVT của dòng SO.")
            if plan.sale_line_id.display_type or plan.product_id.type != "consu" or plan.order_id.state != "sale":
                raise ValidationError("Chọn dòng hàng hóa của đơn bán đã xác nhận.")
            if plan.state == "cancel" and plan.move_ids.filtered(lambda m: m.state != "cancel"):
                raise ValidationError("Gỡ liên kết hoặc hủy các dòng kho trước khi hủy kế hoạch.")

    @api.model_create_multi
    def create(self, vals_list):
        lines = self.env["sale.order.line"].browse([v.get("sale_line_id") for v in vals_list if v.get("sale_line_id")])
        lines.order_id.check_access("write")
        return super().create(vals_list)

    def write(self, vals):
        self.order_id.check_access("write")
        if "sale_line_id" in vals:
            self.env["sale.order.line"].browse(vals["sale_line_id"]).order_id.check_access("write")
            if any(p.move_ids and p.sale_line_id.id != vals["sale_line_id"] for p in self):
                raise ValidationError("Không đổi dòng SO khi kế hoạch đã liên kết dòng kho.")
        return super().write(vals)

    def unlink(self):
        self.order_id.check_access("write")
        if self.move_ids:
            raise ValidationError("Gỡ liên kết dòng kho trước khi xóa kế hoạch.")
        return super().unlink()

    def _actual_quantity(self, cutoff):
        self.ensure_one()
        line = self.sale_line_id
        moves = self.move_ids.filtered(lambda m: m.state == "done" and fields.Datetime.context_timestamp(self, m.date).date() <= cutoff)
        direct = moves.filtered(lambda m: m.product_id == line.product_id)
        quantity = sum(m.product_uom._compute_quantity(m.quantity, line.product_uom_id, round=False) for m in direct)
        kits = moves.filtered(lambda m: m.product_id != line.product_id)
        boms = kits.bom_line_id.bom_id.filtered(lambda b: b.type == "phantom" and
            (b.product_id == line.product_id or (not b.product_id and b.product_tmpl_id == line.product_id.product_tmpl_id)))
        if kits and not boms:
            boms = self.env["mrp.bom"]._bom_find(line.product_id, company_id=self.company_id.id, bom_type="phantom")[line.product_id]
        for bom in boms:
            kit_qty = line.product_uom_id._compute_quantity(self.planned_qty, bom.product_uom_id)
            qty = kits._compute_kit_quantities(line.product_id, kit_qty, bom, {"incoming_moves": lambda m: True, "outgoing_moves": lambda m: False})
            quantity += bom.product_uom_id._compute_quantity(qty, line.product_uom_id)
        return quantity


    # PHẦN 17 - Vận chuyển (gộp từ models/sale_transport.py).
    # Thông tin vận chuyển dùng chung model kế hoạch; giữ nguyên tên trường,
    # công thức tính cước và ràng buộc để không thay đổi dữ liệu hiện có.
    transport_owner_id = fields.Many2one("res.partner", string="Chủ xe / Đơn vị vận chuyển", check_company=True)
    transport_reference = fields.Char("Số phiếu vận chuyển", copy=False,
        help="Bỏ trống để dùng số phiếu kho đã liên kết với đợt giao.")
    transport_receiving_name = fields.Char("Kho nhận", compute="_compute_transport_receiving", store=True, readonly=False)
    transport_weight = fields.Float("Trọng lượng (kg)", digits=(16, 3))
    transport_packages = fields.Float("Thùng / Bao / Kiện", digits=(16, 2))
    transport_charge_basis = fields.Selection([
        ("weight", "Theo kg"), ("quantity", "Theo số lượng dự kiến (ĐVT SO)"),
        ("packages", "Theo số kiện"), ("manual", "Số lượng / ĐVT khác"),
    ], string="Cách tính cước", required=True, default="weight")
    transport_manual_quantity = fields.Float("Lượng tính cước khác", digits=(16, 3))
    transport_manual_unit = fields.Char("ĐVT tính cước khác")
    transport_charge_quantity = fields.Float("Lượng tính cước", compute="_compute_transport_charge", digits=(16, 3))
    transport_charge_unit = fields.Char("ĐVT tính cước", compute="_compute_transport_charge")
    transport_currency_id = fields.Many2one(related="company_id.currency_id", string="Tiền cước")
    transport_unit_price = fields.Monetary("Đơn giá vận chuyển", currency_field="transport_currency_id")
    transport_transfer_fee = fields.Monetary("Trung chuyển", currency_field="transport_currency_id")
    transport_other_fee = fields.Monetary("Phí khác", currency_field="transport_currency_id")
    transport_amount = fields.Monetary("Thành tiền vận chuyển", compute="_compute_transport_charge", currency_field="transport_currency_id")

    @api.depends("order_id.partner_shipping_id")
    def _compute_transport_receiving(self):
        for plan in self:
            plan.transport_receiving_name = plan.order_id.partner_shipping_id.name

    @api.depends("transport_charge_basis", "planned_qty", "uom_id", "transport_weight", "transport_packages",
                 "transport_manual_quantity", "transport_manual_unit", "transport_unit_price",
                 "transport_transfer_fee", "transport_other_fee", "transport_currency_id")
    def _compute_transport_charge(self):
        for plan in self:
            quantity, unit = {
                "weight": (plan.transport_weight, "Kg"),
                "quantity": (plan.planned_qty, plan.uom_id.name),
                "packages": (plan.transport_packages, "Kiện"),
                "manual": (plan.transport_manual_quantity, plan.transport_manual_unit),
            }[plan.transport_charge_basis or "weight"]
            plan.transport_charge_quantity = quantity
            plan.transport_charge_unit = unit
            value = quantity * plan.transport_unit_price + plan.transport_transfer_fee + plan.transport_other_fee
            plan.transport_amount = plan.transport_currency_id.round(value) if plan.transport_currency_id else value

    @api.constrains("transport_weight", "transport_packages", "transport_manual_quantity", "transport_manual_unit",
                    "transport_charge_basis", "transport_unit_price", "transport_transfer_fee", "transport_other_fee")
    def _check_transport_values(self):
        for plan in self:
            if any(plan[f] < 0 for f in ("transport_weight", "transport_packages", "transport_manual_quantity",
                    "transport_unit_price", "transport_transfer_fee", "transport_other_fee")):
                raise ValidationError("Trọng lượng, số kiện, lượng tính cước và chi phí vận chuyển không được âm.")
            if plan.transport_charge_basis == "manual" and not (plan.transport_manual_unit or "").strip():
                raise ValidationError("Hãy nhập ĐVT tính cước khác.")


# LIÊN KẾT SO - Danh sách các đợt giao trên đơn bán.
class SaleOrder(models.Model):
    _inherit = "sale.order"

    ps_delivery_plan_ids = fields.One2many("ps.sale.delivery.plan", "order_id", string="Kế hoạch giao hàng", copy=False)


# LIÊN KẾT KHO - Phân bổ dòng xuất vào đợt giao, sao chép và kiểm tra.
class StockMove(models.Model):
    _inherit = "stock.move"

    ps_delivery_plan_id = fields.Many2one("ps.sale.delivery.plan", string="Đợt giao dự kiến", check_company=True, ondelete="restrict", copy=True, index=True)

    @api.constrains("ps_delivery_plan_id", "sale_line_id", "location_id", "location_dest_id", "origin_returned_move_id", "company_id")
    def _check_delivery_plan(self):
        for move in self.filtered("ps_delivery_plan_id"):
            plan = move.ps_delivery_plan_id
            if plan.state == "cancel" or move.sale_line_id != plan.sale_line_id or move.company_id != plan.company_id:
                raise ValidationError("Đợt giao phải cùng dòng SO, công ty và chưa hủy.")
            if move.location_dest_id.usage != "customer" or move.location_id.usage == "customer" or move.origin_returned_move_id:
                raise ValidationError("Chỉ liên kết kế hoạch với dòng xuất giao khách hàng, không phải phiếu trả.")

    def _prepare_merge_moves_distinct_fields(self):
        return super()._prepare_merge_moves_distinct_fields() + ["ps_delivery_plan_id"]

    def copy_data(self, default=None):
        values = super().copy_data(default=default)
        # Backorders keep the plan; customer returns must not inherit a
        # delivery allocation from the original outgoing stock move.
        for vals in values:
            if vals.get("origin_returned_move_id"):
                vals["ps_delivery_plan_id"] = False
        return values
