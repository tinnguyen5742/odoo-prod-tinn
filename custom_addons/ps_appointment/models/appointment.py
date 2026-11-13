import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .time_utils import timezone_for, utc_to_local

_logger = logging.getLogger(__name__)

ACTIVE_APPOINTMENT_STATES = ("requested", "confirmed", "in_progress")
WORKFLOW_AUDIT_FIELDS = {
    "state_date", "confirmed_by_id", "confirmed_date", "started_by_id", "started_date",
    "completed_by_id", "completed_date",
}


class Appointment(models.Model):
    _name = "ps.appointment"
    _description = "Customer Appointment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_datetime desc, id desc"

    name = fields.Char(required=True, default="/", copy=False, index=True, tracking=True)
    appointment_type_id = fields.Many2one(
        "ps.appointment.type", required=True, tracking=True, index=True, ondelete="restrict"
    )
    partner_id = fields.Many2one("res.partner", required=True, tracking=True, index=True)
    user_id = fields.Many2one("res.users", string="Assigned staff", tracking=True, index=True)
    employee_ref = fields.Reference(selection="_selection_employees", string="Employee record")
    resource_id = fields.Many2one("ps.appointment.resource", tracking=True, index=True)
    slot_id = fields.Many2one("ps.appointment.slot", tracking=True, index=True, ondelete="set null")
    crm_lead_ref = fields.Reference(selection="_selection_crm_leads", string="CRM opportunity / lead")
    sale_order_ref = fields.Reference(selection="_selection_sale_orders", string="Sales order")
    field_service_ref = fields.Reference(selection="_selection_field_service_tasks", string="Field Service task")
    calendar_event_ref = fields.Reference(selection="_selection_calendar_events", string="Calendar event", copy=False)
    start_datetime = fields.Datetime(required=True, tracking=True, index=True)
    end_datetime = fields.Datetime(required=True, tracking=True, index=True)
    duration_minutes = fields.Float(compute="_compute_duration", store=True, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("requested", "Requested"),
            ("confirmed", "Confirmed"),
            ("in_progress", "In Progress"),
            ("done", "Done"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
            ("no_show", "No Show"),
        ],
        required=True,
        default="draft",
        tracking=True,
        index=True,
    )
    state_date = fields.Datetime(readonly=True, copy=False)
    confirmed_by_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    confirmed_date = fields.Datetime(readonly=True, copy=False)
    started_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    started_date = fields.Datetime(readonly=True, copy=False)
    completed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    completed_date = fields.Datetime(readonly=True, copy=False)
    cancellation_reason = fields.Text(tracking=True)
    rejection_reason = fields.Text(tracking=True)
    request_notes = fields.Text()
    description = fields.Html()
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    price = fields.Monetary(compute="_compute_price", store=True, currency_field="currency_id")
    reminder_ids = fields.One2many("ps.appointment.reminder", "appointment_id", copy=False)
    history_ids = fields.One2many("ps.appointment.history", "appointment_id", copy=False)
    resource_booking_ids = fields.One2many(
        "ps.appointment.resource.booking", "appointment_id", copy=False
    )
    history_count = fields.Integer(compute="_compute_counts")
    reminder_count = fields.Integer(compute="_compute_counts")
    customer_appointment_count = fields.Integer(compute="_compute_counts")
    notification_status = fields.Selection(
        [("pending", "Pending"), ("queued", "Queued"), ("failed", "Failed"), ("not_sent", "Not Sent")],
        default="not_sent",
        readonly=True,
        copy=False,
    )
    notification_error = fields.Text(readonly=True, copy=False)
    notification_date = fields.Datetime(readonly=True, copy=False)

    _appointment_name_unique = models.Constraint(
        "unique(name)", "Appointment references must be unique."
    )

    @api.model
    def _selection_employees(self):
        return [("hr.employee", _("Employee"))] if "hr.employee" in self.env.registry.models else []

    @api.model
    def _selection_crm_leads(self):
        return [("crm.lead", _("Lead / Opportunity"))] if "crm.lead" in self.env.registry.models else []

    @api.model
    def _selection_sale_orders(self):
        return [("sale.order", _("Sales Order"))] if "sale.order" in self.env.registry.models else []

    @api.model
    def _selection_field_service_tasks(self):
        task_model = self.env.registry.models.get("project.task")
        if task_model and "is_fsm" in task_model._fields:
            return [("project.task", _("Field Service Task"))]
        return []

    @api.model
    def _selection_calendar_events(self):
        return [("calendar.event", _("Calendar Event"))] if "calendar.event" in self.env.registry.models else []

    @api.depends("start_datetime", "end_datetime")
    def _compute_duration(self):
        for appointment in self:
            if appointment.start_datetime and appointment.end_datetime:
                delta = appointment.end_datetime - appointment.start_datetime
                appointment.duration_minutes = delta.total_seconds() / 60
            else:
                appointment.duration_minutes = 0

    @api.depends("appointment_type_id", "appointment_type_id.price")
    def _compute_price(self):
        for appointment in self:
            appointment.price = appointment.appointment_type_id.price

    @api.depends("history_ids", "reminder_ids", "partner_id")
    def _compute_counts(self):
        for appointment in self:
            appointment.history_count = len(appointment.history_ids)
            appointment.reminder_count = len(appointment.reminder_ids)
            appointment.customer_appointment_count = self.search_count(
                [("partner_id", "=", appointment.partner_id.id)]
            ) if appointment.partner_id else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "draft") != "draft":
                raise AccessError(_("Appointments must be created in Draft and advanced through workflow actions."))
            if WORKFLOW_AUDIT_FIELDS.intersection(vals):
                raise AccessError(_("Workflow audit fields are set only by appointment actions."))
            if not vals.get("name") or vals["name"] == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("ps.appointment") or "/"
            appointment_type = self.env["ps.appointment.type"].browse(vals.get("appointment_type_id"))
            if appointment_type:
                vals.setdefault("company_id", appointment_type.company_id.id)
                if vals.get("start_datetime") and not vals.get("end_datetime"):
                    start = fields.Datetime.to_datetime(vals["start_datetime"])
                    vals["end_datetime"] = fields.Datetime.to_string(
                        start + timedelta(minutes=appointment_type.duration_minutes)
                    )
            if vals.get("employee_ref") and not vals.get("user_id"):
                employee = self._record_from_reference(vals["employee_ref"])
                if employee and "user_id" in employee._fields:
                    vals["user_id"] = employee.user_id.id
        appointments = super().create(vals_list)
        appointments.message_post(body=_("Appointment created in Draft."))
        self.env["ps.appointment.history"].sudo().create(
            [
                {
                    "appointment_id": appointment.id,
                    "event_type": "created",
                    "description": _("Appointment created in Draft."),
                    "user_id": self.env.user.id,
                    "company_id": appointment.company_id.id,
                }
                for appointment in appointments
            ]
        )
        return appointments

    @api.model
    def _record_from_reference(self, value):
        if not value or not isinstance(value, str) or "," not in value:
            return self.env["res.partner"]
        model_name, record_id = value.split(",", 1)
        if model_name not in self.env.registry.models:
            return self.env["res.partner"]
        return self.env[model_name].browse(int(record_id)).exists()

    @api.onchange("appointment_type_id", "start_datetime")
    def _onchange_service_or_start(self):
        if self.appointment_type_id and self.start_datetime:
            self.end_datetime = self.start_datetime + timedelta(
                minutes=self.appointment_type_id.duration_minutes
            )
            if not self.company_id:
                self.company_id = self.appointment_type_id.company_id

    @api.onchange("slot_id")
    def _onchange_slot(self):
        if self.slot_id:
            self.appointment_type_id = self.slot_id.appointment_type_id
            self.user_id = self.slot_id.user_id
            self.resource_id = self.slot_id.resource_id
            self.start_datetime = self.slot_id.start_datetime
            self.end_datetime = self.slot_id.end_datetime
            self.company_id = self.slot_id.company_id

    @api.onchange("employee_ref")
    def _onchange_employee_ref(self):
        if self.employee_ref and "user_id" in self.employee_ref._fields:
            self.user_id = self.employee_ref.user_id

    @api.constrains(
        "appointment_type_id", "partner_id", "start_datetime", "end_datetime", "company_id",
        "resource_id", "user_id", "slot_id",
    )
    def _check_appointment_values(self):
        for appointment in self:
            if appointment.end_datetime <= appointment.start_datetime:
                raise ValidationError(_("Appointment end must be after appointment start."))
            if appointment.appointment_type_id.company_id != appointment.company_id:
                raise ValidationError(_("Appointment and service type must belong to the same company."))
            if appointment.resource_id and appointment.resource_id.company_id != appointment.company_id:
                raise ValidationError(_("Appointment and resource must belong to the same company."))
            if appointment.slot_id and appointment.slot_id.appointment_type_id != appointment.appointment_type_id:
                raise ValidationError(_("The selected slot must match the appointment service type."))

    def write(self, vals):
        vals = dict(vals)
        if len(self) > 1 and ("state" in vals or self._schedule_fields().intersection(vals)):
            raise UserError(_("Change appointment workflow or schedule one record at a time."))
        if WORKFLOW_AUDIT_FIELDS.intersection(vals):
            raise AccessError(_("Workflow audit fields are set only by appointment actions."))

        old_schedule = {}
        for appointment in self:
            old_schedule[appointment.id] = {
                "slot_id": appointment.slot_id,
                "user_id": appointment.user_id,
                "resource_id": appointment.resource_id,
                "start_datetime": appointment.start_datetime,
                "end_datetime": appointment.end_datetime,
                "appointment_type_id": appointment.appointment_type_id,
            }
            if self._schedule_fields().intersection(vals) and appointment.state in ACTIVE_APPOINTMENT_STATES:
                if not (
                    self.env.user.has_group("ps_appointment.group_appointment_receptionist")
                    or self.env.user.has_group("ps_appointment.group_appointment_manager")
                ):
                    raise AccessError(_("Only a Receptionist or Manager can reschedule an active appointment."))
                proposed = appointment._proposed_values(vals)
                appointment._lock_conflict_keys(
                    proposed["service"], proposed["user"], proposed["resource"]
                )
                appointment._validate_booking_values(**proposed, exclude_id=appointment.id)

        if "state" in vals:
            if len(self) != 1:
                raise UserError(_("Process one appointment state transition at a time."))
            self._check_state_transition(vals["state"], vals)
            target = vals["state"]
            vals["state_date"] = fields.Datetime.now()
            if target == "confirmed":
                vals.update({"confirmed_by_id": self.env.user.id, "confirmed_date": fields.Datetime.now()})
            elif target == "in_progress":
                vals.update({"started_by_id": self.env.user.id, "started_date": fields.Datetime.now()})
            elif target == "done":
                vals.update({"completed_by_id": self.env.user.id, "completed_date": fields.Datetime.now()})

        result = super().write(vals)
        for appointment in self:
            before = old_schedule.get(appointment.id, {})
            if "state" in vals:
                appointment._after_state_change(vals["state"], before)
            elif self._schedule_fields().intersection(vals):
                appointment._sync_reservations(previous=before)
                appointment._sync_calendar_event()
                appointment._reset_reminders()
                appointment._record_history(
                    "rescheduled", _("Appointment schedule or assignment changed."), before=before
                )
                appointment._send_customer_notification()
        return result

    @staticmethod
    def _schedule_fields():
        return {
            "appointment_type_id", "user_id", "resource_id", "slot_id", "start_datetime",
            "end_datetime", "company_id", "employee_ref",
        }

    def _proposed_values(self, vals):
        self.ensure_one()
        service = self.env["ps.appointment.type"].browse(
            vals.get("appointment_type_id", self.appointment_type_id.id)
        )
        user = self.env["res.users"].browse(vals.get("user_id", self.user_id.id))
        resource = self.env["ps.appointment.resource"].browse(vals.get("resource_id", self.resource_id.id))
        slot = self.env["ps.appointment.slot"].browse(vals.get("slot_id", self.slot_id.id))
        start = fields.Datetime.to_datetime(vals.get("start_datetime", self.start_datetime))
        end_value = vals.get("end_datetime")
        if end_value:
            end = fields.Datetime.to_datetime(end_value)
        else:
            end = start + timedelta(minutes=service.duration_minutes)
        return {
            "service": service,
            "user": user,
            "resource": resource,
            "slot": slot,
            "start": start,
            "end": end,
        }

    def _check_state_transition(self, target, vals=None):
        self.ensure_one()
        vals = vals or {}
        user = self.env.user
        is_user = user.has_group("ps_appointment.group_appointment_user")
        is_receptionist = user.has_group("ps_appointment.group_appointment_receptionist")
        is_manager = user.has_group("ps_appointment.group_appointment_manager")
        assigned = self.user_id == user
        allowed = {
            "requested": self.state == "draft" and is_user,
            "confirmed": self.state == "requested" and is_manager,
            "in_progress": self.state == "confirmed" and (assigned or is_manager),
            "done": self.state == "in_progress" and (assigned or is_manager),
            "rejected": self.state == "requested" and (is_receptionist or is_manager),
            "cancelled": self.state in ("draft", "requested", "confirmed") and (
                is_receptionist or is_manager or (is_user and self.create_uid == user)
            ),
            "no_show": self.state == "confirmed" and (is_receptionist or is_manager),
        }
        if not allowed.get(target, False):
            raise AccessError(_("This user or appointment state cannot make that transition."))
        if target in ("requested", "confirmed"):
            if target == "confirmed" and not self.user_id:
                raise UserError(_("Assign a staff member before confirming the appointment."))
            values = self._proposed_values(vals)
            if target == "requested" and not values["user"]:
                values["user"] = self._find_available_staff(values)
            if target == "requested" and not values["user"]:
                raise UserError(_("No eligible staff member is available at this time."))
            if target == "requested" and not vals.get("user_id"):
                vals["user_id"] = values["user"].id
            if not values["resource"]:
                values["resource"] = self._find_available_resource(values)
                if values["resource"]:
                    vals["resource_id"] = values["resource"].id
            self._lock_conflict_keys(values["service"], values["user"], values["resource"])
            self._validate_booking_values(**values, exclude_id=self.id if self.id else False)
        if target == "rejected" and not (vals.get("rejection_reason") or self.rejection_reason):
            raise UserError(_("Enter a reason before rejecting an appointment."))
        if target == "cancelled" and not (vals.get("cancellation_reason") or self.cancellation_reason):
            raise UserError(_("Enter a reason before cancelling an appointment."))
        if target == "no_show" and self.start_datetime > fields.Datetime.now():
            raise UserError(_("An appointment cannot be marked No Show before its start time."))

    def _find_available_staff(self, values):
        service = values["service"]
        candidates = service.user_ids or self.env["ps.appointment.schedule"].search(
            [("active", "=", True), ("company_id", "=", service.company_id.id)]
        ).mapped("user_id")
        for candidate in candidates:
            if not service._allows_user(candidate):
                continue
            test_values = dict(values, user=candidate)
            if self._is_available_values(**test_values, exclude_id=self.id if self.id else False):
                return candidate
        return self.env["res.users"]

    def _find_available_resource(self, values):
        service = values["service"]
        schedule = self.env["ps.appointment.schedule"].search(
            [
                ("user_id", "=", values["user"].id),
                ("weekday", "=", str(utc_to_local(values["start"], timezone_for(service.company_id, values["user"])).weekday())),
                ("company_id", "=", service.company_id.id),
                ("active", "=", True),
            ]
        )
        schedule_resources = schedule.mapped("resource_id")
        candidates = service.resource_ids.filtered("active")
        if schedule_resources:
            candidates = candidates & schedule_resources if candidates else schedule_resources.filtered("active")
        for resource in candidates:
            test_values = dict(values, resource=resource)
            if self._is_available_values(**test_values, exclude_id=self.id if self.id else False):
                return resource
        raise UserError(_("No required room or equipment is available at this time."))

    def _validate_booking_values(self, service, user, resource, slot, start, end, exclude_id=False):
        if not service or not service.active:
            raise UserError(_("Choose an active appointment service."))
        if not user or not service._allows_user(user):
            raise UserError(_("The assigned staff member is not eligible for this service."))
        if start is None or end is None or end <= start:
            raise ValidationError(_("Appointment end must be after appointment start."))
        if round((end - start).total_seconds() / 60) != service.duration_minutes:
            raise ValidationError(_("Appointment duration must match the selected service."))
        if service.company_id != self.company_id and self.id:
            raise ValidationError(_("Appointment and service must belong to the same company."))
        now = fields.Datetime.to_datetime(fields.Datetime.now())
        if start < now + timedelta(hours=service.min_notice_hours):
            raise UserError(_("This appointment does not meet the service minimum booking notice."))
        if service.booking_window_days and start > now + timedelta(days=service.booking_window_days):
            raise UserError(_("This appointment falls outside the service booking window."))

        timezone = timezone_for(service.company_id, user)
        local_start = utc_to_local(start, timezone)
        local_end = utc_to_local(end, timezone)
        if local_start.date() != local_end.date():
            raise UserError(_("Appointments cannot span local calendar days."))
        weekday = str(local_start.weekday())
        schedule_domain = [
            ("user_id", "=", user.id),
            ("weekday", "=", weekday),
            ("company_id", "=", service.company_id.id),
            ("active", "=", True),
        ]
        if resource:
            schedule_domain += [
                "|", ("resource_id", "=", False), ("resource_id", "=", resource.id)
            ]
        schedules = self.env["ps.appointment.schedule"].search(schedule_domain)
        start_hour = local_start.hour + local_start.minute / 60 + local_start.second / 3600
        end_hour = local_end.hour + local_end.minute / 60 + local_end.second / 3600
        matching_schedule = schedules.filtered(
            lambda item: (not item.valid_from or item.valid_from <= local_start.date())
            and (not item.valid_until or item.valid_until >= local_start.date())
            and item.start_hour <= start_hour
            and end_hour <= item.end_hour
            and not (
                (item.break_start_hour or item.break_end_hour)
                and start_hour < item.break_end_hour
                and end_hour > item.break_start_hour
            )
        )
        if not matching_schedule:
            raise UserError(_("The appointment is outside the assigned staff working hours or during a break."))

        leaves = self.env["ps.appointment.holiday"].search(
            [
                ("company_id", "=", service.company_id.id),
                ("date_from", "<=", local_start.date()),
                ("date_to", ">=", local_start.date()),
            ]
        )
        if leaves.filtered(
            lambda leave: (not leave.user_id and not leave.resource_id)
            or leave.user_id == user
            or (resource and leave.resource_id == resource)
        ):
            raise UserError(_("The staff member or resource is unavailable on this date."))

        if resource:
            if not resource.active or resource.company_id != service.company_id:
                raise UserError(_("Choose an active resource from the service company."))
            if service.resource_ids and resource not in service.resource_ids:
                raise UserError(_("The selected resource is not enabled for this service."))
            block_end = end + timedelta(minutes=service.buffer_minutes)
            bookings = self.env["ps.appointment.resource.booking"].search(
                [
                    ("resource_id", "=", resource.id),
                    ("company_id", "=", service.company_id.id),
                    ("state", "=", "reserved"),
                    ("start_datetime", "<", fields.Datetime.to_string(block_end)),
                    ("end_datetime", ">", fields.Datetime.to_string(start)),
                    ("appointment_id", "!=", exclude_id or 0),
                ]
            )
            if bookings:
                raise UserError(_("The selected room or equipment is already booked."))

        candidate_end = end + timedelta(minutes=service.buffer_minutes)
        other_appointments = self.search(
            [
                ("user_id", "=", user.id),
                ("company_id", "=", service.company_id.id),
                ("state", "in", list(ACTIVE_APPOINTMENT_STATES)),
                ("id", "!=", exclude_id or 0),
            ]
        )
        for other in other_appointments:
            other_buffer_end = other.end_datetime + timedelta(
                minutes=other.appointment_type_id.buffer_minutes
            )
            if start < other_buffer_end and other.start_datetime < candidate_end:
                raise UserError(_("The assigned staff member already has an overlapping appointment."))

        if slot:
            if slot.appointment_type_id != service or slot.user_id != user or slot.resource_id != resource:
                raise ValidationError(_("The selected available slot does not match this appointment."))
            if slot.state != "available" and slot.appointment_id.id != exclude_id:
                raise UserError(_("The selected available slot has already been booked."))
            if slot.start_datetime != start or slot.end_datetime != end:
                raise ValidationError(_("Appointment time must match its selected slot."))
        return True

    @api.model
    def _is_available_values(self, service, user, resource, start, end, slot=False, exclude_id=False):
        try:
            return bool(
                self._validate_booking_values(
                    service, user, resource, slot, start, end, exclude_id=exclude_id
                )
            )
        except (UserError, ValidationError):
            return False

    @api.model
    def _lock_conflict_keys(self, service, user, resource):
        """Serialize availability checks; reservation data is still written via ORM."""
        if service:
            self.env.cr.execute("SELECT id FROM ps_appointment_type WHERE id = %s FOR UPDATE", [service.id])
        if user:
            self.env.cr.execute("SELECT id FROM res_users WHERE id = %s FOR UPDATE", [user.id])
        if resource:
            self.env.cr.execute("SELECT id FROM ps_appointment_resource WHERE id = %s FOR UPDATE", [resource.id])

    def _after_state_change(self, target, before):
        self.ensure_one()
        if target in ("requested", "confirmed"):
            self._sync_reservations(previous=before)
        elif target in ("rejected", "cancelled", "done", "no_show"):
            self._release_reservations()
            self._delete_calendar_event()
            self._cancel_pending_reminders()
        if target == "requested":
            self._record_history("requested", _("Appointment request submitted."), before=before)
            if self.user_id:
                self.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=self.user_id.id,
                    summary=_("Review appointment request"),
                    note=_("Review and confirm appointment %s.") % self.name,
                    date_deadline=self.start_datetime.date(),
                )
        elif target == "confirmed":
            self._record_history("confirmed", _("Appointment confirmed."), before=before)
            self._sync_calendar_event()
            self._schedule_reminder()
            self._send_customer_notification()
        elif target == "in_progress":
            self._record_history("started", _("Appointment started."), before=before)
        elif target == "done":
            self._record_history("done", _("Appointment completed."), before=before)
        elif target == "rejected":
            self._record_history("rejected", self.rejection_reason, before=before)
            self._send_customer_notification()
        elif target == "cancelled":
            self._record_history("cancelled", self.cancellation_reason, before=before)
            self._send_customer_notification()
        elif target == "no_show":
            self._record_history("no_show", _("Customer did not attend."), before=before)

    def _sync_reservations(self, previous=None):
        self.ensure_one()
        previous = previous or {}
        if previous.get("slot_id") and previous["slot_id"] != self.slot_id:
            previous["slot_id"].sudo().write({"state": "available", "appointment_id": False})
        old_resource = previous.get("resource_id")
        bookings = self.env["ps.appointment.resource.booking"].sudo().search(
            [("appointment_id", "=", self.id)]
        )
        for booking in bookings:
            if booking.resource_id != self.resource_id or self.state not in ACTIVE_APPOINTMENT_STATES:
                booking.write({"state": "released"})
        if self.resource_id and self.state in ACTIVE_APPOINTMENT_STATES:
            booking = bookings.filtered(lambda item: item.resource_id == self.resource_id)[:1]
            booking_values = {
                "start_datetime": self.start_datetime,
                "end_datetime": self.end_datetime + timedelta(
                    minutes=self.appointment_type_id.buffer_minutes
                ),
                "company_id": self.company_id.id,
                "state": "reserved",
            }
            if booking:
                booking.write(booking_values)
            else:
                self.env["ps.appointment.resource.booking"].sudo().create(
                    {"appointment_id": self.id, "resource_id": self.resource_id.id, **booking_values}
                )
        if self.slot_id and self.state in ACTIVE_APPOINTMENT_STATES:
            self.slot_id.sudo().write({"state": "booked", "appointment_id": self.id})

    def _release_reservations(self):
        self.ensure_one()
        self.resource_booking_ids.sudo().filtered(lambda item: item.state == "reserved").write(
            {"state": "released"}
        )
        if self.slot_id and self.slot_id.state == "booked" and self.slot_id.appointment_id == self:
            self.slot_id.sudo().write({"state": "available", "appointment_id": False})

    def _record_history(self, event_type, description, before=None):
        self.ensure_one()
        before = before or {}
        self.env["ps.appointment.history"].sudo().create(
            {
                "appointment_id": self.id,
                "event_type": event_type,
                "description": description,
                "old_start_datetime": before.get("start_datetime"),
                "new_start_datetime": self.start_datetime,
                "old_user_id": before.get("user_id").id if before.get("user_id") else False,
                "new_user_id": self.user_id.id,
                "old_resource_id": before.get("resource_id").id if before.get("resource_id") else False,
                "new_resource_id": self.resource_id.id,
                "user_id": self.env.user.id,
                "company_id": self.company_id.id,
            }
        )

    def _schedule_reminder(self):
        self.ensure_one()
        lead_hours = self.appointment_type_id.reminder_lead_hours
        if lead_hours <= 0:
            return
        remind_at = self.start_datetime - timedelta(hours=lead_hours)
        if remind_at <= fields.Datetime.now():
            return
        existing = self.env["ps.appointment.reminder"].sudo().search(
            [
                ("appointment_id", "=", self.id),
                ("channel", "=", "email"),
                ("reminder_datetime", "=", fields.Datetime.to_string(remind_at)),
            ],
            limit=1,
        )
        if existing and existing.state == "cancelled":
            existing.write({"state": "pending", "mail_id": False, "failure_reason": False})
        elif not existing:
            self.env["ps.appointment.reminder"].sudo().create(
                {
                    "appointment_id": self.id,
                    "channel": "email",
                    "reminder_datetime": fields.Datetime.to_string(remind_at),
                    "company_id": self.company_id.id,
                }
            )

    def _reset_reminders(self):
        self.ensure_one()
        self._cancel_pending_reminders()
        if self.state == "confirmed":
            self._schedule_reminder()

    def _cancel_pending_reminders(self):
        self.ensure_one()
        self.reminder_ids.sudo().filtered(lambda reminder: reminder.state == "pending").write(
            {"state": "cancelled"}
        )

    def _template_send(self):
        self.ensure_one()
        template = self.appointment_type_id.email_template_id
        email = self.partner_id.email
        if not template or not email:
            self.sudo().write(
                {
                    "notification_status": "failed" if not email else "not_sent",
                    "notification_error": _("The customer has no email address.") if not email else False,
                }
            )
            return False
        try:
            mail_id = template.sudo().send_mail(self.id, force_send=False, raise_exception=True)
            self.sudo().write(
                {
                    "notification_status": "queued",
                    "notification_error": False,
                    "notification_date": fields.Datetime.now(),
                }
            )
            return self.env["mail.mail"].sudo().browse(mail_id)
        except Exception as error:
            _logger.exception("Failed to queue appointment email for %s", self.name)
            self.sudo().write(
                {"notification_status": "failed", "notification_error": str(error)}
            )
            return False

    def _send_customer_notification(self):
        for appointment in self:
            appointment._template_send()

    @api.model
    def _cron_send_reminders(self):
        now = fields.Datetime.now()
        queued = self.env["ps.appointment.reminder"].sudo().search(
            [("state", "=", "queued"), ("mail_id", "!=", False)]
        )
        for reminder in queued:
            if reminder.mail_id.state == "sent":
                reminder.write({"state": "sent", "sent_date": fields.Datetime.now()})
            elif reminder.mail_id.state == "exception":
                reminder.write({"state": "failed", "failure_reason": reminder.mail_id.failure_reason or _("Email delivery failed.")})
        reminders = self.env["ps.appointment.reminder"].sudo().search(
            [
                ("state", "=", "pending"),
                ("channel", "=", "email"),
                ("reminder_datetime", "<=", now),
            ],
            order="reminder_datetime, id",
        )
        for reminder in reminders:
            appointment = reminder.appointment_id
            if appointment.state != "confirmed":
                reminder.write({"state": "cancelled"})
                continue
            mail = appointment._template_send()
            if mail:
                reminder.write({"state": "queued", "mail_id": mail.id})
                appointment.message_post(body=_("Appointment reminder queued for email delivery."))
            else:
                reminder.write(
                    {
                        "state": "failed",
                        "failure_reason": appointment.notification_error or _("No email was queued."),
                    }
                )

    def _sync_calendar_event(self):
        self.ensure_one()
        if "calendar.event" not in self.env.registry.models:
            return
        if self.state not in ("confirmed", "in_progress"):
            self._delete_calendar_event()
            return
        event_values = {
            "name": f"{self.appointment_type_id.name}: {self.partner_id.name}",
            "start": fields.Datetime.to_string(self.start_datetime),
            "stop": fields.Datetime.to_string(self.end_datetime),
            "user_id": self.user_id.id,
            "partner_ids": [(6, 0, [self.partner_id.id])],
            "description": _("Appointment %(reference)s. %(notes)s")
            % {"reference": self.name, "notes": self.request_notes or ""},
        }
        event = self.calendar_event_ref
        if event and event._name == "calendar.event":
            event.sudo().write(event_values)
        else:
            event = self.env["calendar.event"].sudo().create(event_values)
            self.sudo().write({"calendar_event_ref": f"calendar.event,{event.id}"})

    def _delete_calendar_event(self):
        self.ensure_one()
        event = self.calendar_event_ref
        if event and event._name == "calendar.event":
            event.sudo().unlink()
            self.sudo().write({"calendar_event_ref": False})

    def action_request(self):
        for appointment in self:
            appointment.write({"state": "requested"})
        return True

    def action_confirm(self):
        for appointment in self:
            appointment.write({"state": "confirmed"})
        return True

    def action_reject(self):
        for appointment in self:
            appointment.write({"state": "rejected"})
        return True

    def action_start(self):
        for appointment in self:
            appointment.write({"state": "in_progress"})
        return True

    def action_done(self):
        for appointment in self:
            appointment.write({"state": "done"})
        return True

    def action_cancel(self):
        for appointment in self:
            appointment.write({"state": "cancelled"})
        return True

    def action_no_show(self):
        for appointment in self:
            appointment.write({"state": "no_show"})
        return True

    def action_view_history(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Appointment History"),
            "res_model": "ps.appointment.history",
            "view_mode": "list,form",
            "domain": [("appointment_id", "=", self.id)],
        }

    def action_view_reminders(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Appointment Reminders"),
            "res_model": "ps.appointment.reminder",
            "view_mode": "list,form",
            "domain": [("appointment_id", "=", self.id)],
        }

    def action_view_partner_appointments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer Appointment History"),
            "res_model": self._name,
            "view_mode": "list,calendar,form",
            "domain": [("partner_id", "=", self.partner_id.id)],
        }

    def action_create_sale_order(self):
        self.ensure_one()
        if "sale.order" not in self.env.registry.models:
            raise UserError(_("Install Sales to create a sales order from an appointment."))
        product = self.appointment_type_id.service_product_ref
        if not product or product._name != "product.product":
            raise UserError(_("Select an optional sales product on the appointment service first."))
        order_model = self.env["sale.order"].sudo()
        values = {"partner_id": self.partner_id.id, "origin": self.name}
        if "company_id" in order_model._fields:
            values["company_id"] = self.company_id.id
        order = order_model.create(values)
        line_values = {
            "order_id": order.id,
            "product_id": product.id,
            "product_uom_qty": 1,
            "price_unit": self.price,
            "name": self.appointment_type_id.name,
        }
        order.order_line.create(line_values)
        self.sudo().write({"sale_order_ref": f"sale.order,{order.id}"})
        self._record_history("linked", _("Sales order %(order)s created.") % {"order": order.name})
        return {
            "type": "ir.actions.act_window",
            "name": order.display_name,
            "res_model": order._name,
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_create_field_service_task(self):
        self.ensure_one()
        if not self._selection_field_service_tasks():
            raise UserError(_("Install Field Service to create a task from an appointment."))
        task_model = self.env["project.task"].sudo()
        values = {"name": f"{self.appointment_type_id.name} - {self.partner_id.name}"}
        for field_name, value in {
            "partner_id": self.partner_id.id,
            "user_ids": [(6, 0, [self.user_id.id])],
            "company_id": self.company_id.id,
            "date_deadline": self.start_datetime.date(),
            "is_fsm": True,
        }.items():
            if field_name in task_model._fields:
                values[field_name] = value
        task = task_model.create(values)
        self.sudo().write({"field_service_ref": f"project.task,{task.id}"})
        self._record_history("linked", _("Field Service task %(task)s created.") % {"task": task.display_name})
        return {
            "type": "ir.actions.act_window",
            "name": task.display_name,
            "res_model": task._name,
            "res_id": task.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_calendar_event(self):
        self.ensure_one()
        if not self.calendar_event_ref:
            raise UserError(_("No Calendar event is linked."))
        return {
            "type": "ir.actions.act_window",
            "name": self.calendar_event_ref.display_name,
            "res_model": self.calendar_event_ref._name,
            "res_id": self.calendar_event_ref.id,
            "view_mode": "form",
            "target": "current",
        }


class AppointmentResourceBooking(models.Model):
    _name = "ps.appointment.resource.booking"
    _description = "Appointment Resource Reservation"
    _order = "start_datetime desc"

    appointment_id = fields.Many2one("ps.appointment", required=True, index=True, ondelete="cascade")
    resource_id = fields.Many2one("ps.appointment.resource", required=True, index=True, ondelete="restrict")
    start_datetime = fields.Datetime(required=True, index=True)
    end_datetime = fields.Datetime(required=True, index=True)
    state = fields.Selection(
        [("reserved", "Reserved"), ("released", "Released")], required=True, default="reserved", index=True
    )
    company_id = fields.Many2one("res.company", required=True, index=True)

    _booking_unique = models.Constraint(
        "unique(appointment_id, resource_id)", "An appointment can reserve a resource only once."
    )

    @api.constrains("start_datetime", "end_datetime", "appointment_id", "resource_id", "company_id")
    def _check_booking_values(self):
        for booking in self:
            if booking.end_datetime <= booking.start_datetime:
                raise ValidationError(_("Resource booking end must be after its start."))
            if booking.appointment_id.company_id != booking.company_id or booking.resource_id.company_id != booking.company_id:
                raise ValidationError(_("Appointment, resource and booking must belong to the same company."))


class AppointmentReminder(models.Model):
    _name = "ps.appointment.reminder"
    _description = "Appointment Email Reminder"
    _inherit = ["mail.thread"]
    _order = "reminder_datetime, id"

    appointment_id = fields.Many2one("ps.appointment", required=True, index=True, ondelete="cascade")
    channel = fields.Selection([("email", "Email")], required=True, default="email", index=True)
    reminder_datetime = fields.Datetime(required=True, index=True)
    state = fields.Selection(
        [
            ("pending", "Pending"), ("queued", "Queued"), ("sent", "Sent"),
            ("failed", "Failed"), ("cancelled", "Cancelled"),
        ],
        required=True,
        default="pending",
        tracking=True,
        index=True,
    )
    mail_id = fields.Many2one("mail.mail", readonly=True, copy=False)
    sent_date = fields.Datetime(readonly=True, copy=False)
    failure_reason = fields.Text(readonly=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, index=True)

    _reminder_unique = models.Constraint(
        "unique(appointment_id, channel, reminder_datetime)",
        "A reminder cannot be scheduled twice for the same appointment and time.",
    )


class AppointmentHistory(models.Model):
    _name = "ps.appointment.history"
    _description = "Appointment Change History"
    _order = "create_date desc, id desc"

    appointment_id = fields.Many2one("ps.appointment", required=True, index=True, ondelete="cascade")
    event_type = fields.Selection(
        [
            ("created", "Created"),
            ("requested", "Requested"), ("confirmed", "Confirmed"), ("rescheduled", "Rescheduled"),
            ("started", "Started"), ("done", "Completed"), ("rejected", "Rejected"),
            ("cancelled", "Cancelled"), ("no_show", "No Show"), ("linked", "ERP Link Created"),
        ],
        required=True,
        index=True,
    )
    description = fields.Text()
    old_start_datetime = fields.Datetime()
    new_start_datetime = fields.Datetime()
    old_user_id = fields.Many2one("res.users")
    new_user_id = fields.Many2one("res.users")
    old_resource_id = fields.Many2one("ps.appointment.resource")
    new_resource_id = fields.Many2one("ps.appointment.resource")
    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    company_id = fields.Many2one("res.company", required=True, index=True)


class AppointmentReminderSettings(models.TransientModel):
    _name = "ps.appointment.reminder.settings"
    _description = "Appointment Reminder Configuration"

    info = fields.Text(default=lambda self: _("Reminder timing is configured on each Appointment Service Type."))
