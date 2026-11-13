import math
from datetime import datetime, timezone

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class Meter(models.Model):
    _inherit = "ps.eam.meter"

    eam_mqtt_topic = fields.Char("Topic MQTT", copy=False, index=True)
    _mqtt_topic_unique = models.Constraint("unique(eam_mqtt_topic)", "Topic MQTT đã được gán cho đồng hồ khác.")

    @api.constrains("eam_mqtt_topic")
    def _check_mqtt_topic(self):
        for meter in self.filtered("eam_mqtt_topic"):
            topic = meter.eam_mqtt_topic
            if topic != topic.strip() or len(topic.encode("utf-8")) > 65535 or any(
                token in topic for token in ("#", "+", "\0")
            ):
                raise ValidationError(_("Nhập topic MQTT cụ thể, không dùng ký tự đại diện."))

    @api.model
    def eam_ingest_mqtt(self, topic, event_id, value, measured_at):
        if not self.env.user.has_group("ps_enterprise_asset.group_eam_mqtt"):
            raise AccessError(_("Chỉ tài khoản cầu nối MQTT của EAM được gửi số đo qua phương thức này."))
        if not isinstance(topic, str) or not topic or not isinstance(event_id, str) or not (
            0 < len(event_id) <= 120 and event_id == event_id.strip() and "\0" not in event_id
        ) or "\0" in topic:
            raise ValidationError(_("Cần topic và mã sự kiện MQTT hợp lệ."))
        try:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError
        except (ValueError, OverflowError) as error:
            raise ValidationError(_("Giá trị đo MQTT phải là số hữu hạn.")) from error
        try:
            timestamp = datetime.fromisoformat(measured_at)
            if not timestamp.tzinfo:
                raise ValueError
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError(_("Thời điểm MQTT phải ở định dạng ISO 8601 có múi giờ.")) from error
        meter = self.sudo().with_context({}).search([
            ("eam_mqtt_topic", "=", topic), ("company_id", "in", self.env.user.company_ids.ids),
            ("equipment_id.active", "=", True), ("equipment_id.eam_status", "!=", "retired"),
        ], limit=1)
        if not meter:
            raise UserError(_("Topic MQTT chưa được gán cho thiết bị đang sử dụng trong công ty."))
        self.env.cr.execute("SELECT id FROM ps_eam_meter WHERE id = %s FOR UPDATE", [meter.id])
        readings = self.env["ps.eam.reading"].sudo().with_context({}).with_company(meter.company_id)
        source = "mqtt:" + event_id
        existing = readings.search([("meter_id", "=", meter.id), ("source", "=", source)], limit=1)
        if existing:
            if existing.value != value or existing.measured_at != timestamp:
                raise ValidationError(_("Mã sự kiện MQTT đã dùng với số đo khác."))
            return {"id": existing.id, "duplicate": True}
        reading = readings.create({
            "meter_id": meter.id, "source": source, "value": value, "measured_at": timestamp,
        })
        return {"id": reading.id, "duplicate": False}
