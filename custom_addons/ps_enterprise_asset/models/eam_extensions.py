from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class Equipment(models.Model):
    _inherit = "maintenance.equipment"

    eam_workcenter_id = fields.Many2one("mrp.workcenter", "Trung tâm sản xuất", check_company=True)
    eam_book_value = fields.Monetary("Giá trị còn lại tham chiếu", compute="_compute_eam_summary")
    eam_oee = fields.Float("Hiệu quả thiết bị tổng hợp (OEE, %)", compute="_compute_eam_summary")
    eam_availability = fields.Float("Khả dụng tổng hợp (%)", compute="_compute_eam_summary")
    eam_performance = fields.Float("Hiệu suất tổng hợp (%)", compute="_compute_eam_summary")
    eam_quality = fields.Float("Chất lượng tổng hợp (%)", compute="_compute_eam_summary")

    @api.depends("cost", "depreciation_recorded", "operation_ids.planned_hours",
                 "operation_ids.running_hours", "operation_ids.total_qty",
                 "operation_ids.good_qty", "operation_ids.ideal_cycle_seconds")
    def _compute_eam_summary(self):
        for rec in self:
            logs = rec.operation_ids
            planned = sum(logs.mapped("planned_hours"))
            running = sum(logs.mapped("running_hours"))
            total = sum(logs.mapped("total_qty"))
            good = sum(logs.mapped("good_qty"))
            ideal = sum(log.ideal_cycle_seconds * log.total_qty for log in logs)
            a = running / planned if planned else 0
            p = min(1, ideal / (running * 3600)) if running else 0
            q = good / total if total else 0
            rec.eam_availability, rec.eam_performance, rec.eam_quality = a * 100, p * 100, q * 100
            rec.eam_oee = a * p * q * 100
            rec.eam_book_value = max(0, rec.cost - rec.depreciation_recorded)

    def write(self, vals):
        if {"eam_workcenter_id", "company_id"} & vals.keys():
            # Old reservations must remain attached to the equipment until its orders close.
            if self.env["maintenance.request"].sudo().search_count([
                ("equipment_id", "in", self.ids), ("eam_managed", "=", True),
                ("eam_state", "in", ["approved", "progress"])]):
                raise UserError(_("Đóng hoặc hủy lệnh đang duyệt/thực hiện trước khi đổi công ty hoặc trung tâm sản xuất."))
        return super().write(vals)


class Request(models.Model):
    _inherit = "maintenance.request"

    eam_repair_hours = fields.Float("Thời gian sửa thực tế (giờ)", compute="_compute_repair_hours", store=True)
    eam_claim_ids = fields.One2many("ps.eam.claim", "request_id", string="Hồ sơ bảo hành")
    eam_workcenter_id = fields.Many2one(related="equipment_id.eam_workcenter_id", string="Trung tâm sản xuất")

    @api.depends("work_started", "work_finished")
    def _compute_repair_hours(self):
        for rec in self:
            rec.eam_repair_hours = max(0, (rec.work_finished - rec.work_started).total_seconds() / 3600) if (
                rec.work_started and rec.work_finished) else 0

    @api.constrains("schedule_date", "schedule_end", "eam_managed")
    def _check_eam_schedule(self):
        for rec in self.filtered("eam_managed"):
            if rec.schedule_date and rec.schedule_end and rec.schedule_end <= rec.schedule_date:
                raise ValidationError(_("Kết thúc dự kiến phải sau thời điểm bắt đầu."))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(v.get("work_started") or v.get("work_finished") for v in vals_list):
            raise UserError(_("Thời gian sửa được ghi tự động qua quy trình bắt đầu/nghiệm thu."))
        return super().create(vals_list)

    def write(self, vals):
        managed = self.filtered("eam_managed")
        if managed and not self.env.su and {"work_started", "work_finished"} & vals.keys():
            raise UserError(_("Thời gian sửa được ghi tự động qua quy trình bắt đầu/nghiệm thu."))
        if managed.filtered(lambda r: r.eam_state in ("approved", "progress")) and {"equipment_id", "company_id"} & vals.keys():
            raise UserError(_("Không đổi thiết bị/công ty sau khi duyệt lệnh."))
        if managed.filtered(lambda r: r.eam_state in ("done", "cancelled")) and {
            "schedule_date", "schedule_end", "maintenance_type", "eam_meter_id",
            "instruction_text", "description", "acceptance_user_id", "acceptance_date"} & vals.keys():
            raise UserError(_("Lệnh đã đóng không được sửa nội dung nghiệp vụ."))
        result = super().write(vals)
        if {"eam_state", "schedule_date", "schedule_end", "name"} & vals.keys():
            managed._sync_eam_calendar()
        return result

    def _sync_eam_calendar(self):
        # Escalation is restricted to reservations owned by these access-checked EAM orders.
        # Technicians do not receive general calendar or manufacturing write permissions.
        self.check_access("write")
        centers = self.mapped("eam_workcenter_id")
        if centers:
            self.env.cr.execute("SELECT id FROM resource_resource WHERE id IN %s ORDER BY id FOR UPDATE",
                                [tuple(centers.mapped("resource_id").ids)])
        Leaves = self.env["resource.calendar.leaves"].sudo()
        for rec in self:
            leave = Leaves.search([("eam_request_id", "=", rec.id)])
            center = rec.eam_workcenter_id
            if not center or rec.eam_state not in ("approved", "progress"):
                leave.unlink()
                continue
            if not rec.schedule_date or not rec.schedule_end:
                raise UserError(_("Nhập giờ bắt đầu/kết thúc dự kiến để đặt lịch dừng máy sản xuất."))
            if center.company_id != rec.company_id:
                raise ValidationError(_("Trung tâm sản xuất phải cùng công ty với lệnh EAM."))
            if not center.resource_calendar_id:
                raise UserError(_("Trung tâm sản xuất chưa có lịch làm việc."))
            values = {"name": "%s - %s" % (rec.eam_number, rec.name),
                      "calendar_id": center.resource_calendar_id.id, "resource_id": center.resource_id.id,
                      "date_from": rec.schedule_date, "date_to": rec.schedule_end,
                      "time_type": "leave", "eam_request_id": rec.id}
            if leave:
                leave.write(values)
            else:
                Leaves.create(values)
            rec._eam_replan_conflicting_workorders(center)

    def action_eam_claim(self):
        self.ensure_one()
        self.check_access("read")
        if not self.eam_managed:
            raise UserError(_("Chỉ tạo hồ sơ từ lệnh EAM."))
        return {"type": "ir.actions.act_window", "name": _("Hồ sơ bảo hành"),
                "res_model": "ps.eam.claim", "view_mode": "list,form",
                "domain": [("request_id", "=", self.id)],
                "context": {"default_request_id": self.id, "default_equipment_id": self.equipment_id.id,
                            "default_company_id": self.company_id.id, "default_direction": "vendor",
                            "default_partner_id": self.equipment_id.partner_id.id}}


class CalendarLeave(models.Model):
    _inherit = "resource.calendar.leaves"

    eam_request_id = fields.Many2one("maintenance.request", "Lệnh EAM", ondelete="cascade", index=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(v.get("eam_request_id") for v in vals_list):
            raise AccessError(_("Đặt lịch dừng máy qua quy trình duyệt lệnh EAM."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and (self.filtered("eam_request_id") or vals.get("eam_request_id")):
            raise AccessError(_("Đổi lịch dừng máy qua lệnh EAM liên quan."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su and self.filtered("eam_request_id"):
            raise AccessError(_("Hủy lịch dừng máy qua lệnh EAM liên quan."))
        return super().unlink()


class Workorder(models.Model):
    _inherit = "mrp.workorder"

    def button_start(self, raise_on_invalid_state=False):
        self.check_access("write")
        centers = self.mapped("workcenter_id")
        if centers:
            self.env.cr.execute("SELECT id FROM resource_resource WHERE id IN %s ORDER BY id FOR UPDATE",
                                [tuple(centers.mapped("resource_id").ids)])
        if centers._eam_blocking_requests():
            raise UserError(_("Trung tâm đang bảo trì hoặc có báo sự cố yêu cầu dừng máy."))
        return super().button_start(raise_on_invalid_state=raise_on_invalid_state)


class Claim(models.Model):
    _inherit = "ps.eam.claim"

    partner_reference = fields.Char("Mã hồ sơ / RMA của đối tác", tracking=True)
    expected_date = fields.Date("Ngày dự kiến xử lý", tracking=True)
    return_picking_id = fields.Many2one("stock.picking", "Phiếu đổi trả", check_company=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self.env.user.has_group("ps_enterprise_asset.group_eam_manager") and any(
                v.get("state", "draft") != "draft" for v in vals_list):
            raise AccessError(_("Kỹ thuật viên chỉ được lập hồ sơ bảo hành nháp."))
        return super().create(vals_list)


class Cost(models.Model):
    _inherit = "ps.eam.cost"

    vendor_id = fields.Many2one("res.partner", "Nhà cung cấp dịch vụ", check_company=True)

    def action_vendor_bill(self):
        self.ensure_one()
        self._check_open_parent(self.request_id)
        self.check_access("write")
        self.env["account.move"].check_access("create")
        self.env.cr.execute("SELECT id FROM ps_eam_cost WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["bill_id"])
        if not self.bill_id:
            if not self.vendor_id or self.amount <= 0:
                raise UserError(_("Nhập nhà cung cấp và chi phí dịch vụ lớn hơn 0."))
            self.bill_id = self.env["account.move"].with_company(self.company_id).create({
                "move_type": "in_invoice", "partner_id": self.vendor_id.id,
                "company_id": self.company_id.id, "currency_id": self.company_id.currency_id.id,
                "invoice_origin": self.request_id.eam_number,
                "invoice_line_ids": [(0, 0, {"name": self.name, "quantity": 1,
                                           "price_unit": self.amount, "tax_ids": [(5, 0, 0)]})]})
        return {"type": "ir.actions.act_window", "res_model": "account.move",
                "res_id": self.bill_id.id, "view_mode": "form"}


class ProductTemplate(models.Model):
    _inherit = "product.template"

    eam_mro = fields.Boolean("Phụ tùng bảo trì (MRO)", index=True,
                            help="Đưa hàng hóa vào danh mục phụ tùng và định mức bổ sung của EAM.")

    @api.constrains("eam_mro", "type")
    def _check_eam_mro_type(self):
        if self.filtered(lambda product: product.eam_mro and product.type != "consu"):
            raise ValidationError(_("Phụ tùng MRO phải là hàng hóa."))
