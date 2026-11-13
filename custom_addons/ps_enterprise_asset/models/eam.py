from datetime import timedelta
import math

from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


def open_records(model, domain, context=None):
    return {"type": "ir.actions.act_window", "res_model": model,
            "view_mode": "list,form", "domain": domain, "context": context or {}}


class Equipment(models.Model):
    _inherit = "maintenance.equipment"

    eam_code = fields.Char("Mã thiết bị", copy=False, index=True)
    parent_id = fields.Many2one("maintenance.equipment", "Thiết bị / cấp cha",
                                ondelete="restrict", check_company=True, index=True)
    child_ids = fields.One2many("maintenance.equipment", "parent_id", string="Thiết bị con")
    eam_level = fields.Selection([("plant", "Nhà máy"), ("line", "Dây chuyền"),
        ("assembly", "Cụm máy"), ("equipment", "Thiết bị"), ("component", "Linh kiện")],
        default="equipment", string="Cấp tài sản")
    eam_location = fields.Char("Vị trí lắp đặt")
    eam_status = fields.Selection([("operating", "Vận hành"), ("standby", "Dự phòng"),
        ("maintenance", "Đang bảo trì"), ("retired", "Ngừng sử dụng")],
        default="operating", required=True, tracking=True, string="Tình trạng")
    customer_id = fields.Many2one("res.partner", "Khách hàng sử dụng", check_company=True)
    warranty_start = fields.Date("Bắt đầu bảo hành nhà cung cấp")
    customer_warranty_start = fields.Date("Bắt đầu bảo hành khách hàng")
    customer_warranty_end = fields.Date("Hết bảo hành khách hàng")
    warranty_terms = fields.Html("Điều khoản bảo hành")
    currency_id = fields.Many2one(related="company_id.currency_id", string="Tiền tệ")
    depreciation_recorded = fields.Monetary("Khấu hao đã ghi nhận (tham chiếu)")
    asset_reference = fields.Char("Tham chiếu tài sản kế toán")
    plan_ids = fields.One2many("ps.eam.plan", "equipment_id", string="Kế hoạch bảo trì")
    meter_ids = fields.One2many("ps.eam.meter", "equipment_id", string="Đồng hồ / cảm biến")
    claim_ids = fields.One2many("ps.eam.claim", "equipment_id", string="Hồ sơ bảo hành")
    operation_ids = fields.One2many("ps.eam.operation", "equipment_id", string="Nhật ký vận hành")
    eam_maintenance_cost = fields.Monetary("Chi phí bảo trì đã đóng", compute="_compute_eam_kpi")
    eam_tco = fields.Monetary("Tổng chi phí sở hữu ghi nhận (TCO)", compute="_compute_eam_kpi")
    eam_mtbf_hours = fields.Float("Thời gian trung bình giữa sự cố (MTBF, giờ)", compute="_compute_eam_kpi")
    eam_mttr_hours = fields.Float("Thời gian sửa chữa trung bình (MTTR, giờ)", compute="_compute_eam_kpi")
    _eam_code_unique = models.Constraint("unique(company_id, eam_code)", "Mã thiết bị phải duy nhất trong công ty.")

    @api.constrains("parent_id")
    def _check_eam_parent(self):
        if self._has_cycle():
            raise ValidationError(_("Cây thiết bị không được tạo vòng lặp."))

    @api.constrains("warranty_start", "warranty_date", "customer_warranty_start", "customer_warranty_end",
                    "cost", "depreciation_recorded")
    def _check_eam_dates(self):
        for rec in self:
            for start, end in [(rec.warranty_start, rec.warranty_date),
                               (rec.customer_warranty_start, rec.customer_warranty_end)]:
                if start and end and start > end:
                    raise ValidationError(_("Ngày hết bảo hành phải sau ngày bắt đầu."))
            if rec.cost < 0 or rec.depreciation_recorded < 0:
                raise ValidationError(_("Chi phí và khấu hao không được âm."))

    @api.depends("cost", "maintenance_ids.eam_state", "maintenance_ids.eam_total_cost",
                 "maintenance_ids.eam_repair_hours", "maintenance_ids.eam_managed", "maintenance_ids.maintenance_type",
                 "operation_ids.running_hours")
    def _compute_eam_kpi(self):
        for rec in self:
            done = rec.maintenance_ids.filtered(lambda r: r.eam_managed and r.eam_state == "done")
            failures = done.filtered(lambda r: r.maintenance_type == "corrective")
            rec.eam_maintenance_cost = sum(done.mapped("eam_total_cost"))
            rec.eam_tco = rec.cost + rec.eam_maintenance_cost
            rec.eam_mtbf_hours = sum(rec.operation_ids.mapped("running_hours")) / len(failures) if failures else 0
            rec.eam_mttr_hours = sum(failures.mapped("eam_repair_hours")) / len(failures) if failures else 0

    def action_eam_orders(self):
        self.ensure_one()
        return open_records("maintenance.request", [("equipment_id", "=", self.id), ("eam_managed", "=", True)],
                            {"default_equipment_id": self.id, "default_eam_managed": True})

    @api.model
    def _cron_warranty_alert(self):
        today = fields.Date.today()
        for rec in self.search([("warranty_date", ">=", today),
                                ("warranty_date", "<=", today + timedelta(days=30))]):
            summary = _("Bảo hành nhà cung cấp sắp hết hạn")
            if not rec.activity_ids.filtered(lambda a: a.summary == summary):
                rec.activity_schedule("mail.mail_activity_data_todo", date_deadline=rec.warranty_date,
                    summary=summary, user_id=rec.technician_user_id.id or self.env.uid)


class Plan(models.Model):
    _name = "ps.eam.plan"
    _description = "Kế hoạch bảo trì"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True

    name = fields.Char("Tên kế hoạch", required=True)
    active = fields.Boolean("Đang áp dụng", default=True)
    company_id = fields.Many2one("res.company", string="Công ty", required=True, default=lambda s: s.env.company)
    equipment_id = fields.Many2one("maintenance.equipment", "Thiết bị", required=True,
                                  check_company=True, ondelete="restrict")
    trigger = fields.Selection([("time", "Theo thời gian"), ("usage", "Theo mức sử dụng")],
                               default="time", required=True, string="Điều kiện")
    interval = fields.Integer("Chu kỳ", default=1, required=True)
    unit = fields.Selection([("day", "Ngày"), ("week", "Tuần"), ("month", "Tháng"), ("quarter", "Quý"), ("year", "Năm")],
                            default="month", required=True, string="Đơn vị")
    next_date = fields.Date("Kỳ tiếp theo", default=fields.Date.context_today)
    meter_id = fields.Many2one("ps.eam.meter", "Đồng hồ", check_company=True,
                              domain="[('equipment_id', '=', equipment_id), ('kind', '=', 'counter')]")
    usage_interval = fields.Float("Chu kỳ chỉ số", default=100)
    next_value = fields.Float("Ngưỡng tiếp theo", default=100)
    checklist = fields.Text("Danh sách kiểm tra (mỗi dòng một bước)")
    instruction = fields.Html("Hướng dẫn kỹ thuật")
    request_ids = fields.One2many("maintenance.request", "eam_plan_id", string="Lệnh bảo trì")
    estimated_hours = fields.Float("Giờ dự kiến", default=1)
    budget = fields.Monetary("Ngân sách mỗi lệnh")
    currency_id = fields.Many2one(related="company_id.currency_id", string="Tiền tệ")

    @api.constrains("trigger", "interval", "usage_interval", "meter_id", "equipment_id",
                    "next_date", "estimated_hours", "budget", "next_value")
    def _check_plan(self):
        for rec in self:
            if rec.interval < 1 or rec.usage_interval <= 0 or rec.estimated_hours <= 0 or rec.budget < 0 or rec.next_value < 0:
                raise ValidationError(_("Chu kỳ, thời lượng phải dương; ngân sách và ngưỡng không âm."))
            if rec.trigger == "time" and not rec.next_date:
                raise ValidationError(_("Kế hoạch theo thời gian cần ngày tiếp theo."))
            if rec.trigger == "usage" and (not rec.meter_id or rec.meter_id.kind != "counter" or
                                           rec.meter_id.equipment_id != rec.equipment_id):
                raise ValidationError(_("Chọn đồng hồ tích lũy thuộc đúng thiết bị."))

    def action_generate(self):
        orders = self.env["maintenance.request"]
        for plan in self:
            plan.check_access("write")
            self.env.cr.execute("SELECT id FROM ps_eam_plan WHERE id = %s FOR UPDATE", [plan.id])
            plan.invalidate_recordset()
            if not plan.active or not plan.equipment_id.active or plan.equipment_id.eam_status == "retired":
                continue
            if plan.request_ids.filtered(lambda r: r.eam_state not in ("done", "cancelled")):
                continue
            if plan.trigger == "time":
                due = plan.next_date <= fields.Date.today()
            else:
                latest = plan.meter_id._latest_reading()
                due = latest and latest.value >= plan.next_value
            if not due:
                continue
            if not plan.equipment_id.maintenance_team_id:
                raise UserError(_("Thiết bị cần được gán đội bảo trì trước khi sinh lệnh."))
            date = plan.next_date if plan.trigger == "time" else fields.Date.today()
            order = orders.create({
                "name": plan.name, "equipment_id": plan.equipment_id.id,
                "company_id": plan.company_id.id, "eam_managed": True,
                "eam_plan_id": plan.id, "maintenance_type": "preventive",
                "schedule_date": fields.Datetime.to_datetime(date),
                "schedule_end": fields.Datetime.to_datetime(date) + timedelta(hours=plan.estimated_hours),
                "instruction_text": plan.instruction, "eam_budget": plan.budget,
                "recurring_maintenance": False,
                "eam_check_ids": [(0, 0, {"name": line.strip()}) for line in (plan.checklist or "").splitlines() if line.strip()],
            })
            orders |= order
        return open_records("maintenance.request", [("id", "in", orders.ids)])

    def _advance(self):
        for plan in self:
            if plan.trigger == "time":
                next_date = plan.next_date
                while next_date <= fields.Date.today():
                    next_date += relativedelta(**({"months": plan.interval * 3} if plan.unit == "quarter" else {plan.unit + "s": plan.interval}))
                plan.next_date = next_date
            else:
                plan.next_value = plan.meter_id.current_value + plan.usage_interval

    @api.model
    def _cron_generate(self):
        for plan in self.search([("active", "=", True)]):
            # A bad configuration must not roll back other plans; report it to the scheduler log.
            try:
                with self.env.cr.savepoint():
                    plan.action_generate()
            except (UserError, ValidationError):
                import logging
                logging.getLogger(__name__).exception("EAM plan %s could not generate", plan.id)


class Meter(models.Model):
    _name = "ps.eam.meter"
    _description = "Đồng hồ / cảm biến"
    _check_company_auto = True

    name = fields.Char("Tên chỉ số", required=True)
    company_id = fields.Many2one("res.company", string="Công ty", required=True, default=lambda s: s.env.company)
    equipment_id = fields.Many2one("maintenance.equipment", required=True, check_company=True, ondelete="restrict", string="Thiết bị")
    kind = fields.Selection([("counter", "Tích lũy"), ("condition", "Tình trạng")], required=True, default="counter", string="Loại")
    unit = fields.Char("Đơn vị đo", required=True, default="giờ")
    lower_limit = fields.Float("Ngưỡng dưới")
    upper_limit = fields.Float("Ngưỡng trên", default=100)
    auto_request = fields.Boolean("Tạo lệnh khi vượt ngưỡng", default=True)
    reading_ids = fields.One2many("ps.eam.reading", "meter_id", string="Lịch sử đo")
    current_value = fields.Float("Chỉ số hiện tại", compute="_compute_current")
    alert_request_id = fields.Many2one("maintenance.request", "Lệnh cảnh báo", compute="_compute_alert")
    alert_request_ids = fields.One2many("maintenance.request", "eam_meter_id")

    @api.depends("alert_request_ids.eam_state")
    def _compute_alert(self):
        for rec in self:
            rec.alert_request_id = self.env["maintenance.request"].search(
                [("eam_meter_id", "=", rec.id), ("eam_state", "not in", ("done", "cancelled"))],
                order="id desc", limit=1)

    @api.depends("reading_ids.value", "reading_ids.measured_at")
    def _compute_current(self):
        for rec in self:
            rec.current_value = rec._latest_reading().value

    def _latest_reading(self):
        self.ensure_one()
        return self.env["ps.eam.reading"].search([("meter_id", "=", self.id)], limit=1)

    @api.constrains("lower_limit", "upper_limit")
    def _check_limits(self):
        for rec in self:
            if rec.lower_limit >= rec.upper_limit:
                raise ValidationError(_("Ngưỡng dưới phải nhỏ hơn ngưỡng trên."))


class Reading(models.Model):
    _name = "ps.eam.reading"
    _description = "Số đo thiết bị"
    _order = "measured_at desc, id desc"
    _check_company_auto = True

    meter_id = fields.Many2one("ps.eam.meter", "Đồng hồ", required=True, ondelete="restrict", check_company=True)
    company_id = fields.Many2one(related="meter_id.company_id", string="Công ty", store=True)
    equipment_id = fields.Many2one(related="meter_id.equipment_id", store=True)
    measured_at = fields.Datetime("Thời điểm đo", default=fields.Datetime.now, required=True)
    value = fields.Float("Giá trị đo", required=True)
    source = fields.Char("Nguồn / mã sự kiện IoT", help="Dùng mã sự kiện duy nhất cho mỗi đồng hồ để chống gửi trùng.")
    abnormal = fields.Boolean("Vượt ngưỡng", compute="_compute_abnormal", store=True)
    _event_unique = models.Constraint("unique(meter_id, source)", "Sự kiện này đã được ghi nhận.")
    _latest_measurement = models.Index("(meter_id, measured_at DESC, id DESC)")

    @api.depends("value", "meter_id.kind", "meter_id.lower_limit", "meter_id.upper_limit")
    def _compute_abnormal(self):
        for rec in self:
            rec.abnormal = rec.meter_id.kind == "condition" and not (
                rec.meter_id.lower_limit <= rec.value <= rec.meter_id.upper_limit)

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for vals in vals_list:
            meter = self.env["ps.eam.meter"].browse(vals["meter_id"])
            meter.check_access("read")
            self.env.cr.execute("SELECT id FROM ps_eam_meter WHERE id = %s FOR UPDATE", [meter.id])
            meter.invalidate_recordset()
            value = vals.get("value", 0)
            measured = fields.Datetime.to_datetime(vals.get("measured_at")) or fields.Datetime.now()
            latest = meter._latest_reading()
            if not math.isfinite(value) or measured > fields.Datetime.now():
                raise ValidationError(_("Giá trị phải hữu hạn và thời điểm đo không ở tương lai."))
            if meter.kind == "counter" and (value < 0 or (latest and (
                    value < latest.value or measured < latest.measured_at))):
                raise ValidationError(_("Đồng hồ tích lũy phải tăng dần theo thời gian; không được giảm chỉ số."))
            rec = super().create([vals])
            records |= rec
            if rec.abnormal and meter.auto_request and (not latest or measured >= latest.measured_at):
                old = meter.alert_request_id
                if not old or old.eam_state in ("done", "cancelled"):
                    if not meter.equipment_id.maintenance_team_id:
                        raise UserError(_("Cần gán đội bảo trì cho thiết bị để tạo cảnh báo."))
                    self.env["maintenance.request"].create({
                        "eam_meter_id": meter.id,
                        "name": _("Vượt ngưỡng: %s", meter.name), "company_id": meter.company_id.id,
                        "equipment_id": meter.equipment_id.id, "eam_managed": True,
                        "maintenance_type": "corrective", "priority": "3",
                        "description": _("%(value)s %(unit)s; giới hạn %(low)s - %(high)s",
                            value=value, unit=meter.unit, low=meter.lower_limit, high=meter.upper_limit),
                    })
        return records

    def write(self, vals):
        raise UserError(_("Số đo là nhật ký bất biến; hãy tạo số đo mới."))

    @api.ondelete(at_uninstall=False)
    def _prevent_delete(self):
        raise UserError(_("Không được xóa lịch sử đo."))


class Request(models.Model):
    _inherit = "maintenance.request"

    eam_managed = fields.Boolean("Lệnh EAM", default=False, copy=True, index=True)
    eam_number = fields.Char("Số lệnh", readonly=True, copy=False, default="/")
    eam_state = fields.Selection([("draft", "Nháp"), ("approved", "Đã duyệt"),
        ("progress", "Đang thực hiện"), ("done", "Đã nghiệm thu"), ("cancelled", "Hủy")],
        default="draft", required=True, tracking=True, copy=False, string="Trạng thái EAM")
    eam_meter_id = fields.Many2one("ps.eam.meter", "Cảm biến nguồn", check_company=True, copy=False, ondelete="restrict")
    eam_plan_id = fields.Many2one("ps.eam.plan", "Kế hoạch", check_company=True, copy=False, ondelete="restrict")
    eam_check_ids = fields.One2many("ps.eam.check", "request_id", string="Danh sách kiểm tra", copy=True)
    cost_ids = fields.One2many("ps.eam.cost", "request_id", string="Chi phí dịch vụ")
    part_ids = fields.One2many("ps.eam.part", "request_id", string="Vật tư dự kiến")
    picking_ids = fields.One2many("stock.picking", "eam_request_id", string="Phiếu vật tư")
    eam_move_ids = fields.One2many("stock.move", "eam_request_id")
    actual_hours = fields.Float("Giờ công thực tế")
    hourly_rate = fields.Monetary("Đơn giá giờ công")
    currency_id = fields.Many2one(related="company_id.currency_id", string="Tiền tệ")
    eam_budget = fields.Monetary("Ngân sách dự toán")
    eam_parts_cost = fields.Monetary("Vật tư thực xuất (giá chụp)", compute="_compute_eam_cost", store=True)
    eam_total_cost = fields.Monetary("Tổng chi phí", compute="_compute_eam_cost", store=True)
    eam_variance = fields.Monetary("Vượt / tiết kiệm ngân sách", compute="_compute_eam_cost", store=True)
    root_cause = fields.Text("Nguyên nhân gốc")
    resolution = fields.Text("Biện pháp xử lý")
    acceptance_user_id = fields.Many2one("res.users", "Người nghiệm thu", readonly=True, copy=False)
    acceptance_date = fields.Datetime("Thời điểm nghiệm thu", readonly=True, copy=False)
    acceptance_signature = fields.Binary("Chữ ký bộ phận vận hành", copy=False, attachment=True)
    work_started = fields.Datetime("Bắt đầu thực tế", readonly=True, copy=False)
    work_finished = fields.Datetime("Kết thúc thực tế", readonly=True, copy=False)
    warranty_notice = fields.Char("Thông tin bảo hành", compute="_compute_warranty_notice")

    @api.depends("equipment_id.warranty_start", "equipment_id.warranty_date", "request_date")
    def _compute_warranty_notice(self):
        for rec in self:
            date = rec.request_date or fields.Date.today()
            start = rec.equipment_id.warranty_start
            end = rec.equipment_id.warranty_date
            rec.warranty_notice = _("Còn bảo hành nhà cung cấp tại ngày yêu cầu — kiểm tra điều khoản trước khi sửa.") if (
                end and date <= end and (not start or date >= start)) else False

    @api.depends("actual_hours", "hourly_rate", "cost_ids.amount", "eam_budget",
                 "eam_move_ids.state", "eam_move_ids.quantity", "eam_move_ids.eam_unit_cost",
                 "eam_move_ids.location_id.usage", "eam_move_ids.location_dest_id.usage")
    def _compute_eam_cost(self):
        for rec in self:
            total = 0
            for move in rec.eam_move_ids.filtered(lambda m: m.state == "done"):
                sign = int(move.location_id.usage == "internal") - int(move.location_dest_id.usage == "internal")
                total += sign * move.quantity * move.eam_unit_cost
            rec.eam_parts_cost = total
            rec.eam_total_cost = total + rec.actual_hours * rec.hourly_rate + sum(rec.cost_ids.mapped("amount"))
            rec.eam_variance = rec.eam_total_cost - rec.eam_budget

    @api.constrains("actual_hours", "hourly_rate", "eam_budget", "equipment_id", "eam_managed", "eam_plan_id")
    def _check_eam_request(self):
        for rec in self:
            if min(rec.actual_hours, rec.hourly_rate, rec.eam_budget) < 0:
                raise ValidationError(_("Giờ công, đơn giá và ngân sách không được âm."))
            if rec.eam_managed and (not rec.equipment_id or not rec.equipment_id.company_id):
                raise ValidationError(_("Lệnh EAM cần thiết bị thuộc một công ty cụ thể."))
            if rec.eam_plan_id and rec.eam_plan_id.equipment_id != rec.equipment_id:
                raise ValidationError(_("Kế hoạch và lệnh phải thuộc cùng thiết bị."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("eam_state", "draft") != "draft" or vals.get("acceptance_user_id") or vals.get("acceptance_date"):
                raise UserError(_("Lệnh mới phải ở trạng thái nháp."))
            if vals.get("eam_managed", self.env.context.get("default_eam_managed")):
                if not self.env.su and not self.env.user.has_group("ps_enterprise_asset.group_eam_user"):
                    raise AccessError(_("Cần quyền EAM để lập lệnh."))
                if vals.get("stage_id") and self.env["maintenance.stage"].browse(vals["stage_id"]).done:
                    raise UserError(_("Lệnh mới phải ở giai đoạn chưa hoàn tất."))
                vals["eam_number"] = self.env["ir.sequence"].next_by_code("ps.eam.order") or "/"
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("eam_managed") and self.filtered(lambda r: not r.eam_managed):
            raise UserError(_("Cờ EAM phải được xác định khi tạo lệnh."))
        manager = self.env.su or self.env.user.has_group("ps_enterprise_asset.group_eam_manager")
        for rec in self.filtered("eam_managed"):
            if not self.env.su and not self.env.user.has_group("ps_enterprise_asset.group_eam_user"):
                raise AccessError(_("Cần quyền EAM để cập nhật lệnh."))
            if rec.eam_state in ("done", "cancelled") and set(vals) & {
                "eam_state", "equipment_id", "eam_managed", "actual_hours", "hourly_rate", "eam_budget",
                "eam_plan_id", "stage_id", "work_started", "work_finished", "root_cause", "resolution", "acceptance_signature", "eam_check_ids", "part_ids", "cost_ids"}:
                raise UserError(_("Lệnh đã đóng không được sửa nội dung nghiệp vụ."))
            if "eam_managed" in vals and vals["eam_managed"] != rec.eam_managed:
                raise UserError(_("Không được bỏ cờ EAM để vượt quy trình."))
            target = vals.get("eam_state")
            if target and target != rec.eam_state:
                allowed = {"draft": ("approved", "cancelled"), "approved": ("progress", "cancelled"),
                           "progress": ("done", "cancelled")}
                if target not in allowed.get(rec.eam_state, ()):
                    raise UserError(_("Chuyển trạng thái không hợp lệ."))
                if target in ("approved", "done", "cancelled") and not manager:
                    raise AccessError(_("Chỉ quản lý EAM được duyệt, nghiệm thu hoặc hủy lệnh."))
                if target == "progress" and rec.equipment_id.eam_status == "retired":
                    raise UserError(_("Không thể bảo trì thiết bị đã ngừng sử dụng."))
                if target == "done":
                    if rec.eam_check_ids.filtered(lambda c: c.required and not c.checked):
                        raise UserError(_("Hoàn thành tất cả bước kiểm tra bắt buộc."))
                    if not rec.resolution or not rec.acceptance_signature:
                        raise UserError(_("Cần biện pháp xử lý và chữ ký nghiệm thu."))
                    if rec.maintenance_type == "corrective" and not rec.root_cause:
                        raise UserError(_("Lệnh khắc phục cần nguyên nhân gốc."))
                if target in ("done", "cancelled") and rec.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")):
                    raise UserError(_("Hoàn tất hoặc hủy các phiếu vật tư đang mở trước khi đóng lệnh."))
            if "stage_id" in vals and self.env["maintenance.stage"].browse(vals["stage_id"]).done and (
                    vals.get("eam_state", rec.eam_state) != "done"):
                raise UserError(_("Hãy nghiệm thu bằng quy trình EAM trước khi đóng giai đoạn."))
            if {"acceptance_user_id", "acceptance_date"} & set(vals) and target != "done":
                raise UserError(_("Thông tin nghiệm thu được hệ thống ghi nhận khi đóng lệnh."))
        if vals.get("eam_state") == "done":
            vals = dict(vals, acceptance_user_id=self.env.uid, acceptance_date=fields.Datetime.now(),
                        work_finished=fields.Datetime.now(), stage_id=self.env.ref("maintenance.stage_3").id)
        if vals.get("eam_state") == "progress":
            vals = dict(vals, work_started=fields.Datetime.now(), stage_id=self.env.ref("maintenance.stage_1").id)
        result = super().write(vals)
        if vals.get("eam_state") == "done":
            self.mapped("eam_plan_id")._advance()
        if vals.get("eam_state") in ("progress", "done", "cancelled"):
            for equipment in self.mapped("equipment_id"):
                if equipment.eam_status != "retired":
                    equipment.eam_status = "maintenance" if self.search_count([
                        ("equipment_id", "=", equipment.id), ("eam_managed", "=", True),
                        ("eam_state", "=", "progress")]) else "operating"
        return result

    @api.ondelete(at_uninstall=False)
    def _prevent_eam_delete(self):
        if self.filtered("eam_managed"):
            raise UserError(_("Lệnh EAM được lưu vết; hãy hủy thay vì xóa."))

    def action_approve(self):
        self.write({"eam_state": "approved"})

    def action_start(self):
        self.write({"eam_state": "progress"})

    def action_done(self):
        self.write({"eam_state": "done"})

    def action_cancel(self):
        self.write({"eam_state": "cancelled", "archive": True})

    def action_pickings(self):
        self.ensure_one()
        return open_records("stock.picking", [("eam_request_id", "=", self.id)])

    def action_create_picking(self):
        self.ensure_one()
        if self.eam_state not in ("approved", "progress"):
            raise UserError(_("Duyệt lệnh trước khi cấp phát vật tư."))
        self.check_access("write")
        self.env.cr.execute("SELECT id FROM maintenance_request WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["picking_ids"])
        if self.picking_ids.filtered(lambda p: p.state != "cancel"):
            return self.action_pickings()
        if not self.part_ids:
            raise UserError(_("Nhập danh sách phụ tùng trước."))
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company_id.id)], limit=1)
        if not warehouse:
            raise UserError(_("Chưa có kho cho công ty này."))
        location = self.env["stock.location"].search([
            ("company_id", "=", self.company_id.id), ("eam_consumption", "=", True)], limit=1)
        if not location:
            raise UserError(_("Quản lý kho cần tạo vị trí tiêu hao EAM (loại Inventory Loss, cờ Tiêu hao EAM)."))
        picking = self.env["stock.picking"].create({
            "picking_type_id": warehouse.int_type_id.id, "company_id": self.company_id.id,
            "location_id": warehouse.lot_stock_id.id, "location_dest_id": location.id,
            "origin": self.eam_number, "eam_request_id": self.id,
            "move_ids": [(0, 0, {
                "product_id": part.product_id.id,
                "product_uom_qty": part.quantity, "product_uom": part.product_id.uom_id.id,
                "company_id": self.company_id.id, "location_id": warehouse.lot_stock_id.id,
                "location_dest_id": location.id,
                "eam_unit_cost": part.product_id.with_company(self.company_id).standard_price,
            }) for part in self.part_ids],
        })
        picking.action_confirm()
        return dict(open_records("stock.picking", []), view_mode="form", res_id=picking.id)


class OrderLineMixin(models.AbstractModel):
    _name = "ps.eam.order.line.mixin"
    _description = "Bảo vệ dòng lệnh EAM"

    def _check_open_parent(self, requests):
        requests.check_access("write")
        if requests.filtered(lambda r: r.eam_state in ("done", "cancelled")):
            raise UserError(_("Không được sửa các dòng của lệnh đã đóng."))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_open_parent(self.env["maintenance.request"].browse([v["request_id"] for v in vals_list]))
        return super().create(vals_list)

    def write(self, vals):
        if self._name == "ps.eam.check" and {"name", "required", "request_id"} & set(vals):
            if not self.env.user.has_group("ps_enterprise_asset.group_eam_manager") and self.mapped("request_id").filtered(lambda r: r.eam_state != "draft"):
                raise AccessError(_("Kỹ thuật viên chỉ được ghi kết quả, không đổi quy trình thao tác chuẩn đã duyệt."))
        parents = self.mapped("request_id")
        if vals.get("request_id"):
            parents |= self.env["maintenance.request"].browse(vals["request_id"])
        self._check_open_parent(parents)
        return super().write(vals)

    def unlink(self):
        if self._name == "ps.eam.check" and not self.env.user.has_group("ps_enterprise_asset.group_eam_manager"):
            if self.mapped("request_id").filtered(lambda r: r.eam_state != "draft"):
                raise AccessError(_("Không được xóa quy trình thao tác chuẩn đã duyệt."))
        self._check_open_parent(self.mapped("request_id"))
        return super().unlink()


class Check(models.Model):
    _name = "ps.eam.check"
    _inherit = "ps.eam.order.line.mixin"
    _description = "Danh sách kiểm tra lệnh bảo trì"
    _check_company_auto = True

    request_id = fields.Many2one("maintenance.request", required=True, ondelete="cascade", check_company=True)
    company_id = fields.Many2one(related="request_id.company_id", string="Công ty", store=True)
    name = fields.Char("Bước kiểm tra", required=True)
    required = fields.Boolean("Bắt buộc", default=True)
    checked = fields.Boolean("Đã kiểm tra")
    result = fields.Char("Kết quả / ghi chú")


class Cost(models.Model):
    _name = "ps.eam.cost"
    _inherit = "ps.eam.order.line.mixin"
    _description = "Chi phí dịch vụ bảo trì"
    _check_company_auto = True

    request_id = fields.Many2one("maintenance.request", required=True, ondelete="cascade", check_company=True)
    company_id = fields.Many2one(related="request_id.company_id", string="Công ty", store=True)
    currency_id = fields.Many2one(related="company_id.currency_id", string="Tiền tệ")
    name = fields.Char("Nội dung dịch vụ", required=True)
    amount = fields.Monetary("Số tiền công ty")
    bill_id = fields.Many2one("account.move", "Hóa đơn tham chiếu", check_company=True,
                             domain="[('move_type', '=', 'in_invoice')]")

    @api.constrains("amount")
    def _check_amount(self):
        if any(r.amount < 0 for r in self):
            raise ValidationError(_("Chi phí không được âm."))


class Part(models.Model):
    _name = "ps.eam.part"
    _inherit = "ps.eam.order.line.mixin"
    _description = "Phụ tùng dự kiến"
    _check_company_auto = True

    request_id = fields.Many2one("maintenance.request", required=True, ondelete="cascade", check_company=True)
    company_id = fields.Many2one(related="request_id.company_id", string="Công ty", store=True)
    product_id = fields.Many2one("product.product", "Phụ tùng", required=True, check_company=True, domain="[('type', '=', 'consu')]")
    quantity = fields.Float("Số lượng dự kiến", default=1, required=True)
    uom_id = fields.Many2one(related="product_id.uom_id", string="Đơn vị")
    vendor_id = fields.Many2one("res.partner", "Nhà cung cấp", check_company=True)
    purchase_id = fields.Many2one("purchase.order", "Yêu cầu báo giá đã tạo", readonly=True, check_company=True, copy=False)

    @api.constrains("quantity", "product_id")
    def _check_quantity(self):
        if any(r.quantity <= 0 or r.product_id.type != "consu" for r in self):
            raise ValidationError(_("Chọn hàng hóa và số lượng dương."))

    def action_rfq(self):
        self.ensure_one()
        self._check_open_parent(self.request_id)
        self.env.cr.execute("SELECT id FROM ps_eam_part WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["purchase_id"])
        if not self.purchase_id:
            if not self.vendor_id:
                raise UserError(_("Chọn nhà cung cấp trước khi tạo yêu cầu báo giá."))
            self.purchase_id = self.env["purchase.order"].create({
                "partner_id": self.vendor_id.id, "company_id": self.company_id.id,
                "origin": self.request_id.eam_number,
                "order_line": [(0, 0, {"product_id": self.product_id.id,
                    "name": self.product_id.display_name, "product_qty": self.quantity,
                    "product_uom_id": self.product_id.uom_id.id,
                    "date_planned": fields.Datetime.now(),
                    "price_unit": self.product_id.with_company(self.company_id).standard_price})],
            })
        return {"type": "ir.actions.act_window", "res_model": "purchase.order",
                "res_id": self.purchase_id.id, "view_mode": "form"}


class Picking(models.Model):
    _inherit = "stock.picking"

    eam_request_id = fields.Many2one("maintenance.request", "Lệnh EAM", check_company=True, ondelete="restrict", index=True)

    def button_validate(self):
        for picking in self.filtered("eam_request_id"):
            if picking.eam_request_id.eam_state not in ("approved", "progress"):
                raise UserError(_("Chỉ xuất vật tư cho lệnh EAM đang được duyệt hoặc thực hiện."))
        return super().button_validate()


class Move(models.Model):
    _inherit = "stock.move"

    eam_request_id = fields.Many2one(related="picking_id.eam_request_id", store=True, index=True)
    eam_unit_cost = fields.Float("Giá tham chiếu khi cấp vật tư", copy=True)


class Location(models.Model):
    _inherit = "stock.location"
    eam_consumption = fields.Boolean("Tiêu hao EAM")

    @api.constrains("eam_consumption", "usage", "company_id")
    def _check_eam_location(self):
        if any(r.eam_consumption and (r.usage != "inventory" or not r.company_id) for r in self):
            raise ValidationError(_("Vị trí tiêu hao EAM cần công ty và loại Inventory Loss."))


class Claim(models.Model):
    _name = "ps.eam.claim"
    _description = "Hồ sơ yêu cầu bảo hành"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True

    name = fields.Char("Số hồ sơ", default="/", readonly=True, copy=False)
    company_id = fields.Many2one("res.company", string="Công ty", required=True, default=lambda s: s.env.company)
    equipment_id = fields.Many2one("maintenance.equipment", "Thiết bị", required=True, check_company=True, ondelete="restrict")
    request_id = fields.Many2one("maintenance.request", "Lệnh liên quan", check_company=True, ondelete="restrict")
    direction = fields.Selection([("vendor", "Yêu cầu nhà cung cấp"), ("customer", "Tiếp nhận khách hàng")], default="vendor", required=True, string="Loại")
    partner_id = fields.Many2one("res.partner", "Đối tác bảo hành", required=True, check_company=True)
    claim_date = fields.Date("Ngày yêu cầu", required=True, default=fields.Date.context_today)
    covered = fields.Boolean("Trong thời hạn bảo hành", compute="_compute_covered")
    description = fields.Html("Mô tả sự cố / điều khoản")
    resolution = fields.Text("Kết quả xử lý")
    state = fields.Selection([("draft", "Nháp"), ("submitted", "Đã gửi"),
        ("accepted", "Chấp nhận"), ("rejected", "Từ chối"), ("closed", "Đã đóng")],
        default="draft", required=True, tracking=True, string="Trạng thái")
    currency_id = fields.Many2one(related="company_id.currency_id", string="Tiền tệ")
    requested_amount = fields.Monetary("Số tiền yêu cầu")
    recovered_amount = fields.Monetary("Bồi hoàn ghi nhận")

    @api.depends("direction", "claim_date", "equipment_id.warranty_start", "equipment_id.warranty_date",
                 "equipment_id.customer_warranty_start", "equipment_id.customer_warranty_end")
    def _compute_covered(self):
        for rec in self:
            eq = rec.equipment_id
            start, end = (eq.warranty_start, eq.warranty_date) if rec.direction == "vendor" else (
                eq.customer_warranty_start, eq.customer_warranty_end)
            rec.covered = bool(end and rec.claim_date <= end and (not start or rec.claim_date >= start))

    @api.constrains("requested_amount", "recovered_amount", "request_id", "equipment_id")
    def _check_claim(self):
        for rec in self:
            if rec.requested_amount < 0 or rec.recovered_amount < 0:
                raise ValidationError(_("Giá trị bảo hành không được âm."))
            if rec.request_id and rec.request_id.equipment_id != rec.equipment_id:
                raise ValidationError(_("Lệnh liên quan phải thuộc đúng thiết bị."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals["name"] = self.env["ir.sequence"].next_by_code("ps.eam.claim") or "/"
        return super().create(vals_list)

    def write(self, vals):
        if "state" in vals and not self.env.su and not self.env.user.has_group("ps_enterprise_asset.group_eam_manager"):
            raise AccessError(_("Chỉ quản lý EAM được cập nhật tiến độ hồ sơ bảo hành."))
        return super().write(vals)


class Operation(models.Model):
    _name = "ps.eam.operation"
    _description = "Nhật ký vận hành và hiệu quả thiết bị"
    _check_company_auto = True
    _order = "date desc, id desc"

    equipment_id = fields.Many2one("maintenance.equipment", "Thiết bị", required=True, check_company=True, ondelete="restrict")
    company_id = fields.Many2one("res.company", string="Công ty", required=True, default=lambda s: s.env.company)
    date = fields.Date("Ngày vận hành", default=fields.Date.context_today, required=True)
    planned_hours = fields.Float("Giờ kế hoạch", required=True)
    running_hours = fields.Float("Giờ chạy thực tế", required=True)
    downtime_hours = fields.Float("Giờ dừng", compute="_compute_oee", store=True)
    ideal_cycle_seconds = fields.Float("Chu kỳ chuẩn (giây / sản phẩm)")
    total_qty = fields.Float("Tổng sản phẩm")
    good_qty = fields.Float("Sản phẩm đạt")
    availability = fields.Float("Khả dụng (%)", compute="_compute_oee", store=True, aggregator="avg")
    performance = fields.Float("Hiệu suất (%)", compute="_compute_oee", store=True, aggregator="avg")
    quality = fields.Float("Chất lượng (%)", compute="_compute_oee", store=True, aggregator="avg")
    oee = fields.Float("Hiệu quả thiết bị (OEE, %)", compute="_compute_oee", store=True, aggregator="avg")
    _day_unique = models.Constraint("unique(equipment_id, date)", "Mỗi thiết bị chỉ có một nhật ký tổng hợp mỗi ngày.")

    @api.constrains("planned_hours", "running_hours", "total_qty", "good_qty", "ideal_cycle_seconds",
                    "equipment_id", "date")
    def _check_operation(self):
        for rec in self:
            if (rec.planned_hours <= 0 or rec.planned_hours > 24 or
                rec.running_hours < 0 or rec.running_hours > rec.planned_hours or
                rec.good_qty < 0 or rec.total_qty < rec.good_qty or rec.ideal_cycle_seconds < 0 or
                (rec.total_qty > 0 and (rec.running_hours <= 0 or rec.ideal_cycle_seconds <= 0))):
                raise ValidationError(_("Kiểm tra giờ kế hoạch (0–24), giờ chạy, chu kỳ chuẩn và số lượng sản phẩm."))
            if rec.date < rec.equipment_id.effective_date:
                raise ValidationError(_("Nhật ký không được trước ngày đưa thiết bị vào sử dụng."))

    @api.depends("planned_hours", "running_hours", "total_qty", "good_qty", "ideal_cycle_seconds")
    def _compute_oee(self):
        for rec in self:
            a = rec.running_hours / rec.planned_hours if rec.planned_hours else 0
            p = min(1, rec.ideal_cycle_seconds * rec.total_qty / (rec.running_hours * 3600)) if rec.running_hours else 0
            q = rec.good_qty / rec.total_qty if rec.total_qty else 0
            rec.downtime_hours = rec.planned_hours - rec.running_hours
            rec.availability, rec.performance, rec.quality = a * 100, p * 100, q * 100
            rec.oee = a * p * q * 100
