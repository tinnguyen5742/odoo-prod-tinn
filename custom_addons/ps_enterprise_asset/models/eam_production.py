from odoo import _, fields, models
from odoo.exceptions import UserError


class Request(models.Model):
    _inherit = "maintenance.request"

    def _eam_replan_conflicting_workorders(self, center):
        self.ensure_one()
        workorders = self.env["mrp.workorder"].sudo().search([
            ("workcenter_id", "=", center.id), ("state", "not in", ("done", "cancel")),
            "|", ("state", "=", "progress"), "&",
            ("date_start", "<", self.schedule_end), ("date_finished", ">", self.schedule_date),
        ])
        if workorders.filtered(lambda order: order.state == "progress"):
            raise UserError(_("Trung tâm đang chạy công đoạn. Dừng công đoạn trước khi duyệt lịch dừng máy."))
        for production in workorders.production_id.sorted("id"):
            production._plan_workorders(replan=True)
        conflicts = self.env["mrp.workorder"].sudo().search_count([
            ("workcenter_id", "=", center.id), ("state", "not in", ("done", "cancel")),
            ("date_start", "<", self.schedule_end), ("date_finished", ">", self.schedule_date),
        ])
        if conflicts:
            raise UserError(_("Không tìm được lịch mới cho tất cả công đoạn trùng lịch dừng máy."))


class Workcenter(models.Model):
    _inherit = "mrp.workcenter"

    eam_availability_state = fields.Selection(
        [("available", "Không có chặn EAM"), ("maintenance", "Dừng bảo trì"), ("breakdown", "Dừng do sự cố")],
        compute="_compute_eam_availability_state", string="Tình trạng EAM",
    )

    def _eam_blocking_requests(self):
        now = fields.Datetime.now()
        return self.env["maintenance.request"].sudo().search([
            ("equipment_id.eam_workcenter_id", "in", self.ids), ("eam_managed", "=", True),
            "|", ("eam_state", "=", "progress"),
            "|", "&", ("eam_breakdown_stop", "=", True), ("eam_state", "not in", ("done", "cancelled")),
            "&", ("eam_state", "=", "approved"), "&",
            ("schedule_date", "<=", now), ("schedule_end", ">", now),
        ])

    def _compute_eam_availability_state(self):
        self.check_access("read")
        requests_by_center = self._eam_blocking_requests().grouped("eam_workcenter_id")
        for center in self:
            requests = requests_by_center.get(center.sudo())
            if not requests:
                center.eam_availability_state = "available"
            elif any(requests.mapped("eam_breakdown_stop")):
                center.eam_availability_state = "breakdown"
            else:
                center.eam_availability_state = "maintenance"
