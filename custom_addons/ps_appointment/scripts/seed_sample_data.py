"""Create an idempotent sample dataset for Appointment Management.

Run from an Odoo shell. This script creates exactly 40 clearly marked sample
appointments plus the staff, customers, services, resources, schedules and
slots needed to demonstrate the workflows. It never deletes unrelated records.
"""

from datetime import datetime, time, timedelta

from odoo import Command, api, fields

from odoo.addons.ps_appointment.models.time_utils import local_to_utc, timezone_for


PREFIX = "[MẪU]"
MARKER = "ps_appointment_sample_data_v1"

operator = env.ref("base.user_admin")
if not operator.has_group("ps_appointment.group_appointment_administrator"):
    raise RuntimeError("The admin user must have Appointment Administrator access.")
env = api.Environment(env.cr, operator.id, env.context)
company = operator.company_id or env.company
today = fields.Date.context_today(env["ps.appointment"])
company_tz = timezone_for(company, operator)

counts = {
    "staff": 0,
    "customers": 0,
    "resources": 0,
    "services": 0,
    "schedules": 0,
    "holidays": 0,
    "slots": 0,
    "appointments": 0,
    "cancelled_mail": 0,
    "cancelled_reminders": 0,
}


def _get_staff(index):
    login = f"appointment.sample.staff{index:02d}"
    user = env["res.users"].sudo().search([("login", "=", login)], limit=1)
    appointment_group = env.ref("ps_appointment.group_appointment_user")
    if not user:
        user = env["res.users"].sudo().with_context(no_reset_password=True).create(
            {
                "name": f"{PREFIX} Nhân viên lịch hẹn {index:02d}",
                "login": login,
                "email": f"appointment.staff{index:02d}@example.invalid",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "tz": str(company_tz),
                "group_ids": [Command.set([appointment_group.id])],
            }
        )
        counts["staff"] += 1
    else:
        update = {}
        if company.id not in user.company_ids.ids:
            update["company_ids"] = [Command.link(company.id)]
        if appointment_group not in user.group_ids:
            update["group_ids"] = [Command.link(appointment_group.id)]
        if not user.active:
            update["active"] = True
        if update:
            user.write(update)
    return user


def _get_customer(index):
    reference = f"APPT-DEMO-CUSTOMER-{index:02d}"
    customer = env["res.partner"].sudo().search([("ref", "=", reference)], limit=1)
    if not customer:
        customer = env["res.partner"].sudo().create(
            {
                "name": f"{PREFIX} Khách hàng lịch hẹn {index:02d}",
                "ref": reference,
                "company_type": "person",
                "email": f"appointment.customer{index:02d}@example.invalid",
                "company_id": company.id,
            }
        )
        counts["customers"] += 1
    return customer


staff = [_get_staff(index) for index in range(1, 7)]
customers = [_get_customer(index) for index in range(1, 41)]

resource_specs = [
    ("CONSULT", "Phòng tư vấn 01", "room"),
    ("SERVICE", "Phòng kỹ thuật 01", "room"),
    ("EQUIP", "Bộ thiết bị kiểm tra 01", "equipment"),
    ("TRAIN", "Phòng đào tạo 01", "room"),
]
resources = []
for code, label, resource_type in resource_specs:
    name = f"{PREFIX} {label}"
    resource = env["ps.appointment.resource"].search(
        [("name", "=", name), ("company_id", "=", company.id)], limit=1
    )
    if not resource:
        resource = env["ps.appointment.resource"].create(
            {
                "name": name,
                "resource_type": resource_type,
                "description": f"{MARKER}; resource for demonstrations only.",
                "company_id": company.id,
            }
        )
        counts["resources"] += 1
    elif resource.resource_type != resource_type:
        resource.write({"resource_type": resource_type})
    resources.append(resource)

service_specs = [
    ("CONSULT", "Tư vấn dịch vụ", 60, 15, 0, 0),
    ("SERVICE", "Bảo trì thiết bị", 90, 15, 250000, 1),
    ("EQUIP", "Hỗ trợ kỹ thuật", 60, 15, 150000, 2),
    ("TRAIN", "Đào tạo khách hàng", 60, 15, 0, 3),
]
services = []
for code, label, duration, buffer, price, resource_index in service_specs:
    name = f"{PREFIX} {label}"
    service = env["ps.appointment.type"].search(
        [("name", "=", name), ("company_id", "=", company.id)], limit=1
    )
    values = {
        "name": name,
        "description": f"<p>{MARKER}; service example, not a commercial offer.</p>",
        "duration_minutes": duration,
        "buffer_minutes": buffer,
        "price": price,
        "min_notice_hours": 2,
        "booking_window_days": 60,
        "reminder_lead_hours": 24,
        "user_ids": [Command.set([user.id for user in staff])],
        "resource_ids": [Command.set([resources[resource_index].id])],
        "company_id": company.id,
        "active": True,
    }
    if service:
        service.write(values)
    else:
        service = env["ps.appointment.type"].create(values)
        counts["services"] += 1
    services.append(service)

# Weekday schedules cover the sample booking period; breaks are respected by
# the normal appointment validation workflow.
weekdays = set()
sample_days = []
day = today + timedelta(days=1)
while len(sample_days) < 10:
    if day.weekday() < 5:
        sample_days.append(day)
        weekdays.add(day.weekday())
    day += timedelta(days=1)

schedule_by_user_and_weekday = {}
for user in staff:
    for weekday in sorted(weekdays):
        schedule = env["ps.appointment.schedule"].search(
            [
                ("user_id", "=", user.id),
                ("weekday", "=", str(weekday)),
                ("company_id", "=", company.id),
                ("start_hour", "=", 8.0),
                ("end_hour", "=", 18.0),
                ("resource_id", "=", False),
            ],
            limit=1,
        )
        if not schedule:
            schedule = env["ps.appointment.schedule"].create(
                {
                    "user_id": user.id,
                    "weekday": str(weekday),
                    "start_hour": 8.0,
                    "end_hour": 18.0,
                    "break_start_hour": 12.0,
                    "break_end_hour": 13.0,
                    "company_id": company.id,
                }
            )
            counts["schedules"] += 1
        schedule_by_user_and_weekday[(user.id, weekday)] = schedule

holiday_specs = [
    ("Ngày nghỉ toàn công ty", 25, False, False),
    ("Nhân viên 01 nghỉ phép", 32, staff[0].id, False),
    ("Nhân viên 04 nghỉ phép", 39, staff[3].id, False),
    ("Phòng kỹ thuật bảo trì", 46, False, resources[1].id),
    ("Thiết bị kiểm tra hiệu chuẩn", 53, False, resources[2].id),
    ("Nhân viên 06 nghỉ phép", 57, staff[5].id, False),
]
holiday_model = env["ps.appointment.holiday"]
for label, day_offset, user_id, resource_id in holiday_specs:
    name = f"{PREFIX} {label}"
    date = today + timedelta(days=day_offset)
    holiday = holiday_model.search(
        [("name", "=", name), ("company_id", "=", company.id)], limit=1
    )
    values = {
        "name": name,
        "date_from": date,
        "date_to": date,
        "user_id": user_id,
        "resource_id": resource_id,
        "company_id": company.id,
        "description": f"{MARKER}; sample leave or maintenance date. Not a real company closure.",
    }
    if holiday:
        holiday.write(values)
    else:
        holiday_model.create(values)
        counts["holidays"] += 1

slot_hours = (9.0, 10.5, 14.0, 16.0)
target_states = ["draft"] * 8 + ["requested"] * 12 + ["confirmed"] * 12 + ["cancelled"] * 4 + ["rejected"] * 4
appointment_model = env["ps.appointment"]
slot_model = env["ps.appointment.slot"]


def _advance_to_target(appointment, target, assigned_staff, index):
    if target == "draft":
        return
    if appointment.state == "draft":
        appointment.with_user(assigned_staff).action_request()
    if target == "requested":
        return
    if target in ("confirmed", "cancelled") and appointment.state == "requested":
        appointment.action_confirm()
    if target == "confirmed":
        return
    if target == "cancelled" and appointment.state == "confirmed":
        if not appointment.cancellation_reason:
            appointment.write(
                {"cancellation_reason": f"{PREFIX} The customer asked to choose another date. Example only."}
            )
        appointment.action_cancel()
    if target == "rejected" and appointment.state == "requested":
        if not appointment.rejection_reason:
            appointment.write(
                {"rejection_reason": f"{PREFIX} Example rejection reason: requested resource is unavailable."}
            )
        appointment.action_reject()


for index, target_state in enumerate(target_states, start=1):
    name = f"{PREFIX} APT-{index:03d}"
    marker = f"{MARKER}:appointment:{index:03d}"
    customer = customers[index - 1]
    assigned_staff = staff[(index - 1) % len(staff)]
    slot_index = (index - 1) % 4
    sample_day = sample_days[(index - 1) // 4]
    service = services[slot_index]
    resource = resources[slot_index]
    schedule = schedule_by_user_and_weekday[(assigned_staff.id, sample_day.weekday())]
    local_start = datetime.combine(sample_day, time()) + timedelta(hours=slot_hours[slot_index])
    start = local_to_utc(local_start, company_tz)
    end = start + timedelta(minutes=service.duration_minutes)
    start_text = fields.Datetime.to_string(start)
    end_text = fields.Datetime.to_string(end)

    appointment = appointment_model.search([("name", "=", name)], limit=1)
    if appointment and marker not in (appointment.request_notes or ""):
        raise RuntimeError(f"Reference {name} already exists and is not this sample record.")

    slot = appointment.slot_id if appointment else slot_model.search(
        [
            ("appointment_type_id", "=", service.id),
            ("schedule_id", "=", schedule.id),
            ("user_id", "=", assigned_staff.id),
            ("resource_id", "=", resource.id),
            ("start_datetime", "=", start_text),
        ],
        limit=1,
    )
    if not slot:
        slot = slot_model.create(
            {
                "appointment_type_id": service.id,
                "schedule_id": schedule.id,
                "user_id": assigned_staff.id,
                "resource_id": resource.id,
                "start_datetime": start_text,
                "end_datetime": end_text,
                "company_id": company.id,
            }
        )
        counts["slots"] += 1

    if not appointment:
        appointment = appointment_model.create(
            {
                "name": name,
                "appointment_type_id": service.id,
                "partner_id": customer.id,
                "user_id": assigned_staff.id,
                "resource_id": resource.id,
                "slot_id": slot.id,
                "start_datetime": start_text,
                "end_datetime": end_text,
                "company_id": company.id,
                "request_notes": (
                    f"{PREFIX} Sample customer request {index:03d}. {marker}. "
                    "This record is illustrative and contains no real customer data."
                ),
                "description": f"<p>{PREFIX} Demonstration record {index:03d}; not a real appointment.</p>",
            }
        )
        counts["appointments"] += 1
    _advance_to_target(appointment, target_state, assigned_staff, index)

# Confirm/reject actions normally enqueue email. Sample data must never contact
# external recipients, so keep the audit messages but cancel unsent queue items
# and reminders before the transaction commits. The .invalid addresses are also
# reserved and cannot belong to real customers.
sample_appointments = appointment_model.search(
    [("request_notes", "ilike", MARKER), ("company_id", "=", company.id)]
)
sample_messages = env["mail.message"].sudo().search(
    [("model", "=", "ps.appointment"), ("res_id", "in", sample_appointments.ids)]
)
sample_mails = env["mail.mail"].sudo().search(
    [("mail_message_id", "in", sample_messages.ids), ("state", "in", ["outgoing", "exception"])]
)
counts["cancelled_mail"] = len(sample_mails)
sample_mails.write({"state": "cancel"})
sample_reminders = env["ps.appointment.reminder"].sudo().search(
    [
        ("appointment_id", "in", sample_appointments.ids),
        ("state", "in", ["pending", "queued"]),
    ]
)
counts["cancelled_reminders"] = len(sample_reminders)
sample_reminders.write({"state": "cancelled"})
sample_appointments.sudo().write(
    {"notification_status": "not_sent", "notification_error": False, "notification_date": False}
)

env.cr.commit()
sample_count = appointment_model.search_count(
    [("request_notes", "ilike", MARKER), ("company_id", "=", company.id)]
)
state_counts = {
    state: appointment_model.search_count(
        [("request_notes", "ilike", MARKER), ("company_id", "=", company.id), ("state", "=", state)]
    )
    for state in ("draft", "requested", "confirmed", "cancelled", "rejected")
}
print(
    f"Appointment sample data ready: {sample_count} sample appointments in {company.name}; "
    f"created this run: {counts}; states: {state_counts}. Existing sample records were reused."
)
