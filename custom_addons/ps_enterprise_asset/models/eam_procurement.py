from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.addons.stock.models.stock_rule import ProcurementException


class PurchaseRequisition(models.Model):
    _name = "ps.eam.purchase.requisition"
    _description = "Yêu cầu mua phụ tùng bảo trì"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _check_company_auto = True

    name = fields.Char("Số yêu cầu", readonly=True, required=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, readonly=True)
    orderpoint_id = fields.Many2one("stock.warehouse.orderpoint", "Định mức", required=True, readonly=True,
                                    check_company=True, ondelete="restrict")
    product_id = fields.Many2one("product.product", "Phụ tùng", required=True, readonly=True, check_company=True)
    quantity = fields.Float("Số lượng cần mua", required=True, readonly=True, digits="Product Unit")
    uom_id = fields.Many2one("uom.uom", "Đơn vị", required=True, readonly=True)
    state = fields.Selection(
        [("submitted", "Chờ mua hàng"), ("approved", "Đã tạo RFQ"),
         ("cancelled", "Đã hủy"), ("satisfied", "Đã đủ nhu cầu")],
        string="Trạng thái", default="submitted", required=True, tracking=True, readonly=True, copy=False,
    )
    purchase_ids = fields.One2many("purchase.order", "eam_requisition_id", string="Yêu cầu báo giá")
    _one_pending_requisition = models.UniqueIndex("(orderpoint_id) WHERE state = 'submitted'")

    @api.model
    def _submit_from_orderpoint(self, procurement):
        point = procurement.values["orderpoint_id"]
        self.env.cr.execute("SELECT id FROM stock_warehouse_orderpoint WHERE id = %s FOR UPDATE", [point.id])
        requisitions = self.sudo().with_company(procurement.company_id)
        existing = requisitions.search([("orderpoint_id", "=", point.id), ("state", "=", "submitted")], limit=1)
        if existing:
            if procurement.product_uom.compare(existing.quantity, procurement.product_qty):
                existing.quantity = procurement.product_qty
            return existing
        requisition = requisitions.create({
            "name": self.env["ir.sequence"].sudo().with_company(procurement.company_id).next_by_code(
                "ps.eam.purchase.requisition"),
            "company_id": procurement.company_id.id,
            "orderpoint_id": point.id,
            "product_id": procurement.product_id.id,
            "quantity": procurement.product_qty,
            "uom_id": procurement.product_uom.id,
        })
        reviewer = procurement.company_id.sudo().eam_purchase_reviewer_id
        if not reviewer or not reviewer.active or procurement.company_id not in reviewer.company_ids:
            managers = self.env.ref("purchase.group_purchase_manager").sudo().all_user_ids
            reviewer = managers.filtered(lambda user: user.active and procurement.company_id in user.company_ids)[:1]
        if reviewer:
            requisition.activity_schedule(
                "mail.mail_activity_data_todo", user_id=reviewer.id,
                summary=_("Duyệt yêu cầu mua phụ tùng EAM"),
            )
        return requisition

    def _lock_for_decision(self):
        self.ensure_one()
        self.check_access("read")
        if not self.env.user.has_group("purchase.group_purchase_manager"):
            raise AccessError(_("Chỉ quản lý mua hàng được duyệt hoặc hủy yêu cầu."))
        self.env.cr.execute("SELECT id FROM stock_warehouse_orderpoint WHERE id = %s FOR UPDATE",
                            [self.orderpoint_id.id])
        self.invalidate_recordset(["state"])
        if self.state != "submitted":
            raise UserError(_("Yêu cầu mua hàng này đã được xử lý."))
        return self.sudo().with_company(self.company_id)

    def action_approve(self):
        requisition = self._lock_for_decision()
        point = requisition.orderpoint_id
        point.invalidate_recordset()
        if not point.active or point.product_id != requisition.product_id or point.trigger != "auto":
            raise UserError(_("Định mức đã thay đổi. Hủy yêu cầu và chạy lại bổ sung tồn kho."))
        quantity = point.qty_to_order
        if point.product_uom.compare(quantity, 0) <= 0:
            requisition.state = "satisfied"
        else:
            rules = self.env["stock.rule"].sudo().with_context({}, from_orderpoint=True).with_company(point.company_id)
            values = point._prepare_procurement_values(date=point._get_orderpoint_procurement_date())
            rule = rules._get_rule(point.product_id, point.location_id, values)
            if not rule or rule.action != "buy":
                raise UserError(_("Định mức cần dùng tuyến Mua trước khi duyệt."))
            values["eam_requisition_id"] = requisition.id
            procurement = rules.Procurement(
                point.product_id, quantity, point.product_uom, point.location_id, requisition.name,
                requisition.name, point.company_id, values,
            )
            try:
                with self.env.cr.savepoint():
                    rules._run_eam_approved_buy(procurement, rule)
            except ProcurementException as error:
                raise UserError("\n".join(message for _, message in error.procurement_exceptions)) from error
            requisition.write({"state": "approved", "quantity": quantity, "uom_id": point.product_uom.id})
        requisition.activity_ids.action_feedback()

    def action_cancel(self):
        requisition = self._lock_for_decision()
        requisition.state = "cancelled"
        requisition.activity_ids.action_feedback()


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    eam_requisition_id = fields.Many2one(
        "ps.eam.purchase.requisition", "Yêu cầu mua EAM", readonly=True, copy=False,
        check_company=True, ondelete="restrict", index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(
            values.get("eam_requisition_id", self.env.context.get("default_eam_requisition_id")) for values in vals_list
        ):
            raise AccessError(_("Tạo RFQ liên kết bằng nút Duyệt trên yêu cầu mua EAM."))
        return super().create(vals_list)

    def write(self, vals):
        if "eam_requisition_id" in vals:
            raise AccessError(_("Liên kết yêu cầu mua EAM được ghi khi tạo RFQ."))
        return super().write(vals)


class StockRule(models.Model):
    _inherit = "stock.rule"

    @api.model
    def _run_buy(self, procurements):
        standard = []
        for procurement, rule in procurements:
            point = procurement.values.get("orderpoint_id")
            if point and point.trigger == "auto" and procurement.product_id.eam_mro and (
                procurement.product_uom.compare(procurement.product_qty, 0) > 0
            ):
                self.env["ps.eam.purchase.requisition"]._submit_from_orderpoint(procurement)
            else:
                standard.append((procurement, rule))
        return super()._run_buy(standard)

    @api.model
    def _run_eam_approved_buy(self, procurement, rule):
        return super()._run_buy([(procurement, rule)])

    def _make_po_get_domain(self, company_id, values, partner):
        domain = super()._make_po_get_domain(company_id, values, partner)
        return domain + (("eam_requisition_id", "=", values.get("eam_requisition_id", False)),)

    def _prepare_purchase_order(self, company_id, origins, values):
        order = super()._prepare_purchase_order(company_id, origins, values)
        order["eam_requisition_id"] = values[0].get("eam_requisition_id", False)
        return order


class Company(models.Model):
    _inherit = "res.company"

    eam_purchase_reviewer_id = fields.Many2one("res.users", "Người duyệt yêu cầu mua EAM")
