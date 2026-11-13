import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class Reading(models.Model):
    _inherit = "ps.eam.reading"

    @api.model_create_multi
    def create(self, vals_list):
        readings = super().create(vals_list)
        for meter in readings.meter_id.filtered(lambda item: item.kind == "counter"):
            for plan in self.env["ps.eam.plan"].sudo().with_company(meter.company_id).search([
                ("meter_id", "=", meter.id), ("trigger", "=", "usage"), ("active", "=", True),
                ("next_value", "<=", meter.current_value),
            ]):
                try:
                    with self.env.cr.savepoint():
                        plan.action_generate()
                except (UserError, ValidationError):
                    _logger.exception("EAM usage plan %s could not generate", plan.id)
        return readings


class Equipment(models.Model):
    _inherit = "maintenance.equipment"

    eam_is_tool = fields.Boolean("Công cụ bảo trì", index=True)
    eam_customer_warranty_terms = fields.Html("Điều khoản bảo hành khách hàng")

    @api.model
    def _cron_warranty_alert(self):
        super()._cron_warranty_alert()
        today = fields.Date.today()
        summary = _("Bảo hành khách hàng sắp hết hạn")
        for equipment in self.search([
            ("customer_warranty_end", ">=", today),
            ("customer_warranty_end", "<=", today + timedelta(days=30)),
        ]):
            if not equipment.activity_ids.filtered(lambda activity: activity.summary == summary):
                equipment.activity_schedule(
                    "mail.mail_activity_data_todo", summary=summary,
                    date_deadline=equipment.customer_warranty_end,
                    user_id=equipment.technician_user_id.id or self.env.uid,
                )


class Breakdown(models.Model):
    _name = "ps.eam.breakdown"
    _description = "Báo sự cố từ bộ phận vận hành"
    _order = "id desc"
    _check_company_auto = True

    name = fields.Char("Tiêu đề sự cố", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    equipment_id = fields.Many2one(
        "maintenance.equipment", "Thiết bị", required=True, check_company=True, ondelete="restrict",
    )
    description = fields.Text("Mô tả sự cố", required=True)
    urgent = fields.Boolean("Máy hỏng, cần dừng sản xuất")
    request_id = fields.Many2one("maintenance.request", "Lệnh khắc phục", readonly=True, copy=False,
                                check_company=True, ondelete="restrict", groups="ps_enterprise_asset.group_eam_user")
    state = fields.Selection(related="request_id.eam_state", string="Trạng thái xử lý",
                             groups=False, compute_sudo=True)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if "request_id" in values or "state" in values or self.env.context.get("default_request_id"):
                raise AccessError(_("Lệnh khắc phục được hệ thống tạo khi báo sự cố."))
        reports = super().create(vals_list)
        for report in reports:
            equipment = report.equipment_id
            equipment.check_access("read")
            if equipment.company_id != report.company_id or not equipment.active or equipment.eam_status == "retired":
                raise ValidationError(_("Chọn thiết bị đang sử dụng và thuộc công ty của báo cáo."))
            if not equipment.maintenance_team_id:
                raise UserError(_("Thiết bị chưa được gán đội bảo trì."))
            center = equipment.sudo().eam_workcenter_id
            if report.urgent and center:
                self.env.cr.execute("SELECT id FROM resource_resource WHERE id = %s FOR UPDATE",
                                    [center.resource_id.id])
            order = self.env["maintenance.request"].sudo().with_context({}).with_company(report.company_id).create({
                "name": report.name,
                "company_id": report.company_id.id,
                "equipment_id": equipment.id,
                "maintenance_team_id": equipment.maintenance_team_id.id,
                "eam_managed": True,
                "maintenance_type": "corrective",
                "description": report.description,
                "priority": "3" if report.urgent else "1",
                "eam_breakdown_stop": report.urgent,
            })
            report.sudo().request_id = order
        return reports


class Request(models.Model):
    _inherit = "maintenance.request"

    eam_breakdown_stop = fields.Boolean("Sự cố yêu cầu dừng máy", copy=False, readonly=True, index=True)
    eam_tool_ids = fields.One2many("ps.eam.tool.loan", "request_id", string="Công cụ dụng cụ")

    @api.depends(
        "equipment_id.warranty_start", "equipment_id.warranty_date",
        "equipment_id.customer_warranty_start", "equipment_id.customer_warranty_end", "request_date",
    )
    def _compute_warranty_notice(self):
        super()._compute_warranty_notice()
        for order in self:
            equipment = order.equipment_id
            date = order.request_date or fields.Date.today()
            if equipment.customer_warranty_end and date <= equipment.customer_warranty_end and (
                not equipment.customer_warranty_start or date >= equipment.customer_warranty_start
            ):
                notice = _("Còn bảo hành khách hàng tại ngày yêu cầu.")
                order.warranty_notice = " ".join(filter(None, (order.warranty_notice, notice)))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(values.get("eam_breakdown_stop", self.env.context.get("default_eam_breakdown_stop"))
                                   for values in vals_list):
            raise AccessError(_("Tạo báo sự cố từ màn hình dành cho bộ phận vận hành."))
        return super().create(vals_list)

    def write(self, vals):
        if "eam_breakdown_stop" in vals and not self.env.su:
            raise AccessError(_("Trạng thái dừng máy của báo sự cố được quản lý theo lệnh khắc phục."))
        if vals.get("eam_state") in ("done", "cancelled") and self:
            self.check_access("write")
            self.env.cr.execute("SELECT id FROM maintenance_request WHERE id IN %s ORDER BY id FOR UPDATE",
                                [tuple(self.ids)])
            self.invalidate_recordset(["eam_tool_ids", "eam_state"])
            if self.mapped("eam_tool_ids").filtered(lambda loan: loan.state == "issued"):
                raise UserError(_("Thu hồi tất cả công cụ đã cấp trước khi đóng lệnh."))
        return super().write(vals)

    def action_eam_stock_workflow(self):
        self.ensure_one()
        self.check_access("read")
        if not self.eam_managed or not self.env.user.has_group("stock.group_stock_user"):
            raise AccessError(_("Cần quyền Kho để mở luồng cấp phát phụ tùng."))
        return {
            "type": "ir.actions.act_window", "res_model": self._name,
            "res_id": self.id, "views": [(self.env.ref("ps_enterprise_asset.request_form").id, "form")],
            "context": dict(self.env.context, eam_stock_workflow=True),
        }


class ToolLoan(models.Model):
    _name = "ps.eam.tool.loan"
    _description = "Cấp phát và thu hồi công cụ bảo trì"
    _inherit = "ps.eam.order.line.mixin"
    _check_company_auto = True

    request_id = fields.Many2one("maintenance.request", required=True, check_company=True, ondelete="cascade")
    company_id = fields.Many2one(related="request_id.company_id", store=True)
    tool_id = fields.Many2one(
        "maintenance.equipment", "Công cụ", required=True, check_company=True, ondelete="restrict",
        domain="[('eam_is_tool', '=', True), ('eam_status', '!=', 'retired')]",
    )
    state = fields.Selection(
        [("planned", "Dự kiến"), ("issued", "Đã cấp"), ("returned", "Đã thu hồi")],
        string="Trạng thái", required=True, default="planned", readonly=True, index=True,
    )
    issued_at = fields.Datetime("Thời điểm cấp", readonly=True, copy=False)
    issued_by_id = fields.Many2one("res.users", string="Người cấp", readonly=True, copy=False)
    returned_at = fields.Datetime("Thời điểm thu hồi", readonly=True, copy=False)
    returned_by_id = fields.Many2one("res.users", string="Người thu hồi", readonly=True, copy=False)
    note = fields.Char("Ghi chú")
    _one_tool_per_order = models.Constraint("unique(request_id, tool_id)", "Công cụ đã có trên lệnh này.")
    _one_active_loan = models.UniqueIndex("(tool_id) WHERE state = 'issued'")

    @api.constrains("request_id", "tool_id")
    def _check_tool(self):
        for loan in self:
            if not loan.request_id.eam_managed or not loan.tool_id.eam_is_tool or (
                loan.tool_id.company_id != loan.company_id
            ):
                raise ValidationError(_("Chọn công cụ bảo trì cùng công ty với lệnh EAM."))

    @api.model_create_multi
    def create(self, vals_list):
        protected = {"issued_at", "issued_by_id", "returned_at", "returned_by_id"}
        if any(values.get("state", self.env.context.get("default_state", "planned")) != "planned"
               or protected.intersection(values) for values in vals_list) or any(
            self.env.context.get("default_" + key) for key in protected
        ):
            raise AccessError(_("Công cụ mới phải ở trạng thái dự kiến."))
        return super().create(vals_list)

    def write(self, vals):
        if {"state", "issued_at", "issued_by_id", "returned_at", "returned_by_id"} & vals.keys():
            raise AccessError(_("Dùng nút Cấp phát hoặc Thu hồi để ghi nhận bàn giao."))
        if {"request_id", "tool_id"} & vals.keys() and self.filtered(lambda loan: loan.state != "planned"):
            raise UserError(_("Công cụ đã cấp không được đổi."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda loan: loan.state != "planned"):
            raise UserError(_("Phải lưu lịch sử công cụ đã cấp."))
        return super().unlink()

    def _lock_loan(self):
        self.ensure_one()
        self.check_access("write")
        self.env.cr.execute("SELECT id FROM maintenance_request WHERE id = %s FOR UPDATE", [self.request_id.id])
        self.request_id.invalidate_recordset()
        self.env.cr.execute("SELECT id FROM maintenance_equipment WHERE id = %s FOR UPDATE", [self.tool_id.id])
        self.invalidate_recordset()

    def action_issue(self):
        self._lock_loan()
        if self.state != "planned" or self.request_id.eam_state not in ("approved", "progress"):
            raise UserError(_("Chỉ cấp công cụ dự kiến cho lệnh đã duyệt hoặc đang thực hiện."))
        if not self.tool_id.active or not self.tool_id.eam_is_tool or self.tool_id.eam_status == "retired":
            raise UserError(_("Công cụ hiện không còn sẵn sàng để cấp."))
        if self.sudo().search_count([("tool_id", "=", self.tool_id.id), ("state", "=", "issued")]):
            raise UserError(_("Công cụ đang được cấp cho một lệnh khác."))
        return super().write({"state": "issued", "issued_at": fields.Datetime.now(), "issued_by_id": self.env.uid})

    def action_return(self):
        self._lock_loan()
        if self.state != "issued":
            raise UserError(_("Chỉ thu hồi công cụ đã cấp."))
        return super().write({"state": "returned", "returned_at": fields.Datetime.now(),
                              "returned_by_id": self.env.uid})
