from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .time_utils import float_to_time, local_to_utc, timezone_for


class AppointmentType(models.Model):
    _name = "ps.appointment.type"
    _description = "Appointment Service Type"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True, index=True)
    code = fields.Char(required=True, default="/", readonly=True, copy=False, index=True)
    description = fields.Html()
    duration_minutes = fields.Integer(required=True, default=60, tracking=True)
    buffer_minutes = fields.Integer(default=0, tracking=True)
    price = fields.Monetary(tracking=True)
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    user_ids = fields.Many2many(
        "res.users", "ps_appointment_type_user_rel", "type_id", "user_id", string="Eligible staff"
    )
    group_ids = fields.Many2many(
        "res.groups", "ps_appointment_type_group_rel", "type_id", "group_id", string="Staff groups"
    )
    resource_ids = fields.Many2many(
        "ps.appointment.resource",
        "ps_appointment_type_resource_rel",
        "type_id",
        "resource_id",
        string="Eligible resources",
    )
    min_notice_hours = fields.Integer(default=2, tracking=True)
    booking_window_days = fields.Integer(default=90, tracking=True)
    reminder_lead_hours = fields.Integer(default=24, tracking=True)
    email_template_id = fields.Many2one(
        "mail.template",
        default=lambda self: self.env.ref(
            "ps_appointment.mail_template_appointment_notification", raise_if_not_found=False
        ),
        domain="[('model', '=', 'ps.appointment')]",
    )
    service_product_ref = fields.Reference(
        selection="_selection_products", string="Optional sales product"
    )
    appointment_count = fields.Integer(compute="_compute_appointment_count")
    active = fields.Boolean(default=True, tracking=True)

    _type_code_unique = models.Constraint(
        "unique(code, company_id)", "Appointment service codes must be unique per company."
    )

    @api.model
    def _selection_products(self):
        return [("product.product", _("Product"))] if "product.product" in self.env.registry.models else []

    @api.depends("name")
    def _compute_appointment_count(self):
        counts = dict(
            self.env["ps.appointment"]._read_group(
                [("appointment_type_id", "in", self.ids)], ["appointment_type_id"], ["__count"]
            )
        )
        for appointment_type in self:
            appointment_type.appointment_count = counts.get(appointment_type, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") or vals["code"] == "/":
                vals["code"] = self.env["ir.sequence"].next_by_code("ps.appointment.type") or "/"
        return super().create(vals_list)

    @api.constrains(
        "duration_minutes", "buffer_minutes", "price", "min_notice_hours",
        "booking_window_days", "reminder_lead_hours", "company_id",
    )
    def _check_type_values(self):
        for appointment_type in self:
            if appointment_type.duration_minutes <= 0:
                raise ValidationError(_("Appointment duration must be greater than zero."))
            if min(
                appointment_type.buffer_minutes,
                appointment_type.min_notice_hours,
                appointment_type.booking_window_days,
                appointment_type.reminder_lead_hours,
            ) < 0:
                raise ValidationError(_("Buffer, notice, booking window and reminder values cannot be negative."))

    def action_open_slots(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Generate available slots"),
            "res_model": "ps.appointment.slot.generator",
            "view_mode": "form",
            "target": "new",
            "context": {"default_appointment_type_id": self.id},
        }

    def action_view_appointments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Appointments"),
            "res_model": "ps.appointment",
            "view_mode": "list,calendar,form",
            "domain": [("appointment_type_id", "=", self.id)],
            "context": {"default_appointment_type_id": self.id},
        }

    def _allows_user(self, user):
        self.ensure_one()
        if self.user_ids and user not in self.user_ids:
            return False
        if self.group_ids and not (self.group_ids & user.group_ids):
            return False
        return bool(user.active and user.share is False)


class AppointmentResource(models.Model):
    _name = "ps.appointment.resource"
    _description = "Appointment Room or Equipment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True, index=True)
    code = fields.Char(required=True, default="/", readonly=True, copy=False, index=True)
    resource_type = fields.Selection(
        [("room", "Room"), ("equipment", "Equipment"), ("other", "Other")],
        required=True,
        default="room",
        tracking=True,
    )
    description = fields.Text()
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    active = fields.Boolean(default=True, tracking=True)
    booking_count = fields.Integer(compute="_compute_booking_count")

    _resource_code_unique = models.Constraint(
        "unique(code, company_id)", "Appointment resource codes must be unique per company."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") or vals["code"] == "/":
                vals["code"] = self.env["ir.sequence"].next_by_code("ps.appointment.resource") or "/"
        return super().create(vals_list)

    @api.depends("name")
    def _compute_booking_count(self):
        counts = dict(
            self.env["ps.appointment.resource.booking"]._read_group(
                [("resource_id", "in", self.ids)], ["resource_id"], ["__count"]
            )
        )
        for resource in self:
            resource.booking_count = counts.get(resource, 0)

    def action_view_bookings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Resource bookings"),
            "res_model": "ps.appointment.resource.booking",
            "view_mode": "list,form",
            "domain": [("resource_id", "=", self.id)],
        }


class AppointmentSchedule(models.Model):
    _name = "ps.appointment.schedule"
    _description = "Appointment Staff Schedule"
    _order = "user_id, weekday, start_hour"

    name = fields.Char(compute="_compute_name", store=True)
    user_id = fields.Many2one("res.users", required=True, index=True)
    resource_id = fields.Many2one("ps.appointment.resource", index=True)
    weekday = fields.Selection(
        [
            ("0", "Monday"), ("1", "Tuesday"), ("2", "Wednesday"), ("3", "Thursday"),
            ("4", "Friday"), ("5", "Saturday"), ("6", "Sunday"),
        ],
        required=True,
        index=True,
    )
    start_hour = fields.Float(required=True, default=9.0)
    end_hour = fields.Float(required=True, default=17.0)
    break_start_hour = fields.Float()
    break_end_hour = fields.Float()
    valid_from = fields.Date()
    valid_until = fields.Date()
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    active = fields.Boolean(default=True)

    @api.depends("user_id", "weekday", "start_hour", "end_hour")
    def _compute_name(self):
        weekdays = dict(self._fields["weekday"].selection)
        for schedule in self:
            schedule.name = _("%(user)s · %(day)s %(from)s–%(to)s") % {
                "user": schedule.user_id.name or "",
                "day": weekdays.get(schedule.weekday, ""),
                "from": schedule.start_hour,
                "to": schedule.end_hour,
            }

    @api.constrains(
        "start_hour", "end_hour", "break_start_hour", "break_end_hour", "valid_from", "valid_until",
        "user_id", "resource_id", "company_id",
    )
    def _check_schedule_values(self):
        for schedule in self:
            if not (0 <= schedule.start_hour < schedule.end_hour <= 24):
                raise ValidationError(_("Schedule start and end must be within a valid 24-hour day."))
            if bool(schedule.break_start_hour) != bool(schedule.break_end_hour):
                if not (schedule.break_start_hour == 0 and schedule.break_end_hour > 0):
                    raise ValidationError(_("Enter both break start and break end."))
            if schedule.break_start_hour or schedule.break_end_hour:
                if not (
                    schedule.start_hour <= schedule.break_start_hour < schedule.break_end_hour <= schedule.end_hour
                ):
                    raise ValidationError(_("The break must fall inside the working hours."))
            if schedule.valid_from and schedule.valid_until and schedule.valid_until < schedule.valid_from:
                raise ValidationError(_("Schedule end date cannot precede its start date."))
            if schedule.company_id not in schedule.user_id.company_ids:
                raise ValidationError(_("The staff user must be allowed to work in the schedule company."))
            if schedule.resource_id and schedule.resource_id.company_id != schedule.company_id:
                raise ValidationError(_("Schedule and resource must belong to the same company."))


class AppointmentHoliday(models.Model):
    _name = "ps.appointment.holiday"
    _description = "Appointment Staff or Resource Leave"
    _order = "date_from, name"

    name = fields.Char(required=True, index=True)
    date_from = fields.Date(required=True, index=True)
    date_to = fields.Date(required=True, index=True)
    user_id = fields.Many2one("res.users", index=True)
    resource_id = fields.Many2one("ps.appointment.resource", index=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    description = fields.Text()

    @api.constrains("date_from", "date_to", "resource_id", "company_id")
    def _check_holiday_values(self):
        for holiday in self:
            if holiday.date_to < holiday.date_from:
                raise ValidationError(_("Leave end date cannot precede its start date."))
            if holiday.resource_id and holiday.resource_id.company_id != holiday.company_id:
                raise ValidationError(_("Leave and resource must belong to the same company."))


class AppointmentSlot(models.Model):
    _name = "ps.appointment.slot"
    _description = "Available Appointment Slot"
    _order = "start_datetime, user_id, resource_id"

    name = fields.Char(compute="_compute_name", store=True)
    appointment_type_id = fields.Many2one("ps.appointment.type", required=True, index=True, ondelete="cascade")
    schedule_id = fields.Many2one("ps.appointment.schedule", required=True, index=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", required=True, index=True)
    resource_id = fields.Many2one("ps.appointment.resource", index=True)
    start_datetime = fields.Datetime(required=True, index=True)
    end_datetime = fields.Datetime(required=True, index=True)
    state = fields.Selection(
        [("available", "Available"), ("booked", "Booked"), ("cancelled", "Cancelled")],
        required=True,
        default="available",
        index=True,
    )
    appointment_id = fields.Many2one("ps.appointment", readonly=True, copy=False, index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)

    @api.depends("appointment_type_id", "start_datetime", "user_id", "resource_id")
    def _compute_name(self):
        for slot in self:
            slot.name = _("%(service)s · %(date)s · %(staff)s%(resource)s") % {
                "service": slot.appointment_type_id.name or "",
                "date": fields.Datetime.to_string(slot.start_datetime) if slot.start_datetime else "",
                "staff": slot.user_id.name or "",
                "resource": f" · {slot.resource_id.name}" if slot.resource_id else "",
            }

    @api.constrains("start_datetime", "end_datetime", "appointment_type_id", "schedule_id", "company_id")
    def _check_slot_values(self):
        for slot in self:
            if slot.end_datetime <= slot.start_datetime:
                raise ValidationError(_("Slot end must be after slot start."))
            if slot.company_id != slot.appointment_type_id.company_id or slot.company_id != slot.schedule_id.company_id:
                raise ValidationError(_("The slot, service and schedule must belong to the same company."))

    def action_book(self):
        self.ensure_one()
        if self.state != "available":
            raise UserError(_("This appointment slot is no longer available."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Request Appointment"),
            "res_model": "ps.appointment",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_slot_id": self.id,
                "default_appointment_type_id": self.appointment_type_id.id,
                "default_user_id": self.user_id.id,
                "default_resource_id": self.resource_id.id,
                "default_start_datetime": self.start_datetime,
                "default_end_datetime": self.end_datetime,
                "default_company_id": self.company_id.id,
            },
        }


class AppointmentSlotGenerator(models.TransientModel):
    _name = "ps.appointment.slot.generator"
    _description = "Generate Appointment Availability"

    appointment_type_id = fields.Many2one("ps.appointment.type", required=True)
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(required=True, default=lambda self: fields.Date.context_today(self) + timedelta(days=14))
    generated_count = fields.Integer(readonly=True)

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_to < wizard.date_from:
                raise ValidationError(_("The end date cannot precede the start date."))
            if (wizard.date_to - wizard.date_from).days > 180:
                raise ValidationError(_("Generate slots for no more than 180 days at a time."))

    def action_generate(self):
        self.ensure_one()
        if not self.env.user.has_group("ps_appointment.group_appointment_manager"):
            raise AccessError(_("Only an Appointment Manager can generate available slots."))
        service = self.appointment_type_id
        schedules = self.env["ps.appointment.schedule"].search(
            [("active", "=", True), ("company_id", "=", service.company_id.id)]
        )
        created = 0
        day_count = (self.date_to - self.date_from).days + 1
        for offset in range(day_count):
            day = self.date_from + timedelta(days=offset)
            weekday = str(day.weekday())
            for schedule in schedules.filtered(lambda item: item.weekday == weekday):
                if schedule.valid_from and day < schedule.valid_from:
                    continue
                if schedule.valid_until and day > schedule.valid_until:
                    continue
                if not service._allows_user(schedule.user_id):
                    continue
                timezone = timezone_for(service.company_id, schedule.user_id)
                candidate_resources = service.resource_ids.filtered(lambda item: item.active)
                if schedule.resource_id:
                    candidate_resources = (
                        candidate_resources & schedule.resource_id
                        if candidate_resources
                        else schedule.resource_id
                    )
                resource_values = list(candidate_resources) if candidate_resources else [False]
                start_minutes = round(schedule.start_hour * 60)
                end_minutes = round(schedule.end_hour * 60)
                interval = service.duration_minutes + service.buffer_minutes
                while start_minutes + service.duration_minutes <= end_minutes:
                    local_start = datetime.combine(day, float_to_time(start_minutes / 60))
                    local_end = local_start + timedelta(minutes=service.duration_minutes)
                    interval_start = start_minutes / 60
                    interval_end = interval_start + service.duration_minutes / 60
                    if schedule.break_start_hour or schedule.break_end_hour:
                        if interval_start < schedule.break_end_hour and interval_end > schedule.break_start_hour:
                            start_minutes = max(start_minutes + interval, round(schedule.break_end_hour * 60))
                            continue
                    try:
                        utc_start = local_to_utc(local_start, timezone)
                        utc_end = local_to_utc(local_end, timezone)
                    except ValidationError:
                        start_minutes += interval
                        continue
                    for resource in resource_values:
                        values = {
                            "appointment_type_id": service.id,
                            "user_id": schedule.user_id.id,
                            "resource_id": resource.id if resource else False,
                            "start_datetime": fields.Datetime.to_string(utc_start),
                            "end_datetime": fields.Datetime.to_string(utc_end),
                            "company_id": service.company_id.id,
                        }
                        domain = [
                            ("appointment_type_id", "=", service.id),
                            ("schedule_id", "=", schedule.id),
                            ("start_datetime", "=", values["start_datetime"]),
                            ("user_id", "=", schedule.user_id.id),
                            ("resource_id", "=", resource.id if resource else False),
                        ]
                        existing = self.env["ps.appointment.slot"].search(domain, limit=1)
                        if existing or not self.env["ps.appointment"]._is_available_values(
                            service, schedule.user_id, resource, utc_start, utc_end
                        ):
                            continue
                        self.env["ps.appointment.slot"].create(
                            {**values, "schedule_id": schedule.id}
                        )
                        created += 1
                    start_minutes += interval
        self.generated_count = created
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Availability generated"),
                "message": _("Created %(count)s available time slots.") % {"count": created},
                "type": "success",
                "sticky": False,
            },
        }
