from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class QualityEquipment(models.Model):
    _name = "ps.quality.equipment"
    _description = "Quality Measurement Equipment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "next_calibration_date, name"

    name = fields.Char(required=True, tracking=True, index=True)
    code = fields.Char(required=True, default="/", readonly=True, copy=False, index=True)
    manufacturer = fields.Char(tracking=True)
    model_number = fields.Char(string="Model", tracking=True)
    serial_number = fields.Char(tracking=True, index=True)
    technical_details = fields.Text()
    calibration_interval_days = fields.Integer(required=True, default=365, tracking=True)
    last_calibration_date = fields.Date(tracking=True)
    next_calibration_date = fields.Date(
        compute="_compute_next_calibration_date", store=True, index=True
    )
    calibration_state = fields.Selection(
        [
            ("not_calibrated", "Not Calibrated"),
            ("valid", "Valid"),
            ("due", "Due Soon"),
            ("overdue", "Overdue"),
            ("out_of_service", "Out of Service"),
        ],
        compute="_compute_calibration_state",
        store=True,
        index=True,
    )
    warning_days = fields.Integer(default=30)
    out_of_service = fields.Boolean(default=False, tracking=True)
    responsible_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, tracking=True
    )
    maintenance_ref = fields.Reference(
        selection="_selection_maintenance_equipment", string="Maintenance equipment"
    )
    calibration_ids = fields.One2many("ps.quality.calibration", "equipment_id")
    calibration_count = fields.Integer(compute="_compute_calibration_count")
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    description = fields.Html()

    _equipment_code_unique = models.Constraint(
        "unique(code, company_id)", "Measurement equipment codes must be unique per company."
    )

    @api.model
    def _selection_maintenance_equipment(self):
        if "maintenance.equipment" in self.env.registry.models:
            return [("maintenance.equipment", _("Maintenance equipment"))]
        return []

    @api.depends(
        "last_calibration_date", "calibration_interval_days", "calibration_ids.state",
        "calibration_ids.calibration_date", "calibration_ids.next_due_date",
    )
    def _compute_next_calibration_date(self):
        for equipment in self:
            latest = equipment.calibration_ids.filtered(
                lambda calibration: calibration.state == "confirmed"
            ).sorted("calibration_date", reverse=True)[:1]
            if latest and latest.next_due_date:
                equipment.next_calibration_date = latest.next_due_date
            else:
                equipment.next_calibration_date = (
                    equipment.last_calibration_date + timedelta(days=equipment.calibration_interval_days)
                    if equipment.last_calibration_date and equipment.calibration_interval_days > 0
                    else False
                )

    @api.depends("next_calibration_date", "warning_days", "out_of_service", "active")
    def _compute_calibration_state(self):
        today = fields.Date.context_today(self)
        for equipment in self:
            if equipment.out_of_service or not equipment.active:
                equipment.calibration_state = "out_of_service"
            elif not equipment.last_calibration_date or not equipment.next_calibration_date:
                equipment.calibration_state = "not_calibrated"
            elif equipment.next_calibration_date < today:
                equipment.calibration_state = "overdue"
            elif equipment.next_calibration_date <= today + timedelta(days=equipment.warning_days):
                equipment.calibration_state = "due"
            else:
                equipment.calibration_state = "valid"

    @api.depends("calibration_ids")
    def _compute_calibration_count(self):
        counts = dict(
            self.env["ps.quality.calibration"]._read_group(
                [("equipment_id", "in", self.ids)], ["equipment_id"], ["__count"]
            )
        )
        for equipment in self:
            equipment.calibration_count = counts.get(equipment, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") or vals["code"] == "/":
                vals["code"] = self.env["ir.sequence"].next_by_code("ps.quality.equipment") or "/"
        return super().create(vals_list)

    @api.constrains("calibration_interval_days", "warning_days", "responsible_id", "company_id")
    def _check_equipment_values(self):
        for equipment in self:
            if equipment.calibration_interval_days <= 0 or equipment.warning_days < 0:
                raise ValidationError(_("Calibration interval must be positive and warning days cannot be negative."))
            if equipment.responsible_id.company_id and equipment.responsible_id.company_id != equipment.company_id:
                raise ValidationError(_("The responsible user must belong to the equipment company."))

    def write(self, vals):
        if "out_of_service" in vals and not self.env.user.has_group("ps_quality.group_quality_manager"):
            raise AccessError(_("Only a Quality Manager can change equipment service status."))
        if "last_calibration_date" in vals and not self.env.user.has_group("ps_quality.group_quality_manager"):
            raise AccessError(_("Only a Quality Manager can change the last calibration date."))
        return super().write(vals)

    def action_schedule_calibration(self):
        self.ensure_one()
        if not self.env.user.has_group("ps_quality.group_quality_inspector"):
            raise AccessError(_("Only a Quality Inspector can schedule calibration."))
        calibration = self.env["ps.quality.calibration"].create(
            {
                "equipment_id": self.id,
                "company_id": self.company_id.id,
                "calibration_date": fields.Date.context_today(self),
                "calibrated_by_id": self.env.user.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": calibration.name,
            "res_model": calibration._name,
            "res_id": calibration.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_calibrations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Calibration history"),
            "res_model": "ps.quality.calibration",
            "view_mode": "list,form",
            "domain": [("equipment_id", "=", self.id)],
            "context": {"default_equipment_id": self.id, "default_company_id": self.company_id.id},
        }

    def action_open_maintenance(self):
        self.ensure_one()
        if not self.maintenance_ref:
            raise UserError(_("No Maintenance equipment is linked."))
        return {
            "type": "ir.actions.act_window",
            "name": self.maintenance_ref.display_name,
            "res_model": self.maintenance_ref._name,
            "res_id": self.maintenance_ref.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def _cron_calibration_due(self):
        today = fields.Date.context_today(self)
        equipment_records = self.sudo().search(
            [
                ("active", "=", True),
                ("out_of_service", "=", False),
                ("next_calibration_date", "!=", False),
            ]
        )
        summary = _("Measurement equipment calibration due")
        for equipment in equipment_records:
            if equipment.next_calibration_date > today + timedelta(days=equipment.warning_days):
                continue
            pending = self.env["mail.activity"].sudo().search_count(
                [
                    ("res_model", "=", equipment._name),
                    ("res_id", "=", equipment.id),
                    ("summary", "=", summary),
                    ("date_done", "=", False),
                ]
            )
            if not pending:
                equipment.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=equipment.responsible_id.id,
                    date_deadline=equipment.next_calibration_date,
                    summary=summary,
                    note=_("Calibrate %(equipment)s by %(date)s.")
                    % {"equipment": equipment.display_name, "date": equipment.next_calibration_date},
                )


class QualityCalibration(models.Model):
    _name = "ps.quality.calibration"
    _description = "Quality Equipment Calibration"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "calibration_date desc, id desc"

    name = fields.Char(required=True, default="/", copy=False, index=True, tracking=True)
    equipment_id = fields.Many2one(
        "ps.quality.equipment", required=True, ondelete="restrict", tracking=True, index=True
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    calibration_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    next_due_date = fields.Date(tracking=True)
    result = fields.Selection(
        [("pass", "Passed"), ("fail", "Failed")], tracking=True, index=True
    )
    calibrated_by_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, tracking=True
    )
    provider = fields.Char(string="Calibration provider")
    certificate_reference = fields.Char(string="Certificate reference")
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        required=True,
        default="draft",
        tracking=True,
        index=True,
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "ps_quality_calibration_attachment_rel",
        "calibration_id",
        "attachment_id",
        string="Certificates / evidence",
        copy=False,
    )
    notes = fields.Html()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("ps.quality.calibration") or "/"
            if vals.get("equipment_id"):
                equipment = self.env["ps.quality.equipment"].browse(vals["equipment_id"])
                vals.setdefault("company_id", equipment.company_id.id)
                calibration_date = fields.Date.to_date(
                    vals.get("calibration_date") or fields.Date.context_today(self)
                )
                vals.setdefault(
                    "next_due_date",
                    calibration_date + timedelta(days=equipment.calibration_interval_days),
                )
        return super().create(vals_list)

    @api.constrains("equipment_id", "company_id", "calibration_date", "next_due_date")
    def _check_calibration_values(self):
        for calibration in self:
            if calibration.equipment_id.company_id != calibration.company_id:
                raise ValidationError(_("Calibration and equipment must belong to the same company."))
            if calibration.next_due_date and calibration.next_due_date <= calibration.calibration_date:
                raise ValidationError(_("The next calibration date must be after the calibration date."))
            if (
                calibration.equipment_id.last_calibration_date
                and calibration.calibration_date < calibration.equipment_id.last_calibration_date
            ):
                raise ValidationError(_("A calibration cannot predate the equipment's latest calibration."))

    def write(self, vals):
        if any(calibration.state != "draft" for calibration in self):
            raise UserError(_("Confirmed or cancelled calibration records are read-only."))
        if "state" in vals:
            for calibration in self:
                if vals["state"] == "confirmed":
                    if calibration.state != "draft" or not self.env.user.has_group("ps_quality.group_quality_inspector"):
                        raise AccessError(_("Only a Quality Inspector can confirm a draft calibration."))
                    if calibration.result not in ("pass", "fail"):
                        raise UserError(_("Record a calibration result before confirmation."))
                    if not calibration.next_due_date:
                        vals["next_due_date"] = calibration.calibration_date + timedelta(
                            days=calibration.equipment_id.calibration_interval_days
                        )
                elif vals["state"] == "cancelled":
                    if calibration.state != "draft" or not self.env.user.has_group("ps_quality.group_quality_manager"):
                        raise AccessError(_("Only a Quality Manager can cancel a draft calibration."))
                else:
                    raise AccessError(_("Invalid calibration status transition."))
        result = super().write(vals)
        if vals.get("state") == "confirmed":
            for calibration in self.filtered(lambda record: record.state == "confirmed"):
                equipment = calibration.equipment_id
                super(QualityEquipment, equipment.sudo()).write(
                {
                    "last_calibration_date": calibration.calibration_date,
                    "out_of_service": calibration.result == "fail",
                }
            )
                calibration.message_post(body=_("Calibration result confirmed: %s") % calibration.result)
        return result

    def action_confirm(self):
        for calibration in self:
            calibration.write({"state": "confirmed"})
        return True

    def action_cancel(self):
        for calibration in self:
            calibration.write({"state": "cancelled"})
        return True
