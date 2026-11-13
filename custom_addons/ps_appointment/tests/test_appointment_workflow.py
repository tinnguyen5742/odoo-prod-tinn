from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from ..models.time_utils import local_to_utc, timezone_for


@tagged("post_install", "-at_install")
class TestAppointmentWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.admin = cls._create_user("appointment.admin", "group_appointment_administrator")
        cls.manager = cls._create_user("appointment.manager", "group_appointment_manager")
        cls.receptionist = cls._create_user("appointment.reception", "group_appointment_receptionist")
        cls.staff = cls._create_user("appointment.staff", "group_appointment_user")
        cls.customer = cls.env["res.partner"].create(
            {"name": "Appointment Test Customer", "email": "customer@example.test"}
        )
        cls.resource = cls.env["ps.appointment.resource"].with_user(cls.admin).create(
            {
                "name": "Appointment Test Room",
                "resource_type": "room",
                "company_id": cls.company.id,
            }
        )
        cls.service = cls.env["ps.appointment.type"].with_user(cls.admin).create(
            {
                "name": "Consultation",
                "duration_minutes": 60,
                "buffer_minutes": 15,
                "min_notice_hours": 0,
                "booking_window_days": 90,
                "reminder_lead_hours": 24,
                "user_ids": [(6, 0, [cls.staff.id])],
                "resource_ids": [(6, 0, [cls.resource.id])],
                "company_id": cls.company.id,
            }
        )
        cls.appointment_day = fields.Date.today() + timedelta(days=5)
        cls.env["ps.appointment.schedule"].with_user(cls.admin).create(
            {
                "user_id": cls.staff.id,
                "resource_id": cls.resource.id,
                "weekday": str(cls.appointment_day.weekday()),
                "start_hour": 8,
                "end_hour": 18,
                "break_start_hour": 12,
                "break_end_hour": 13,
                "company_id": cls.company.id,
            }
        )
        tz = timezone_for(cls.company, cls.staff)
        cls.start = local_to_utc(datetime.combine(cls.appointment_day, datetime.min.time()).replace(hour=10), tz)
        cls.end = cls.start + timedelta(hours=1)

    @classmethod
    def _create_user(cls, login, group_xmlid):
        group = cls.env.ref(f"ps_appointment.{group_xmlid}")
        return cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": login,
                "login": login,
                "email": f"{login}@example.test",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
                "group_ids": [(6, 0, [group.id])],
            }
        )

    def _new_appointment(self, user=None):
        return self.env["ps.appointment"].with_user(user or self.staff).create(
            {
                "appointment_type_id": self.service.id,
                "partner_id": self.customer.id,
                "start_datetime": fields.Datetime.to_string(self.start),
                "end_datetime": fields.Datetime.to_string(self.end),
                "company_id": self.company.id,
                "request_notes": "Please call when I arrive.",
            }
        )

    def test_request_confirm_reminder_and_cancel_release_reservations(self):
        appointment = self._new_appointment()
        appointment.with_user(self.staff).action_request()
        self.assertEqual(appointment.state, "requested")
        self.assertEqual(appointment.user_id, self.staff)
        self.assertEqual(appointment.resource_id, self.resource)
        self.assertEqual(appointment.resource_booking_ids.filtered(lambda row: row.state == "reserved").resource_id, self.resource)
        self.assertEqual(
            self.env["ps.appointment.history"].search(
                [("appointment_id", "=", appointment.id), ("event_type", "=", "requested")],
                limit=1,
            ).event_type,
            "requested",
        )

        appointment.with_user(self.manager).action_confirm()
        self.assertEqual(appointment.state, "confirmed")
        self.assertEqual(appointment.reminder_ids.filtered(lambda row: row.state == "pending").reminder_datetime, self.start - timedelta(hours=24))
        appointment._schedule_reminder()
        self.assertEqual(appointment.reminder_ids.search_count([("appointment_id", "=", appointment.id)]), 1)
        appointment.with_user(self.manager).write({"cancellation_reason": "Customer requested a new date."})
        appointment.with_user(self.manager).action_cancel()
        self.assertEqual(appointment.state, "cancelled")
        self.assertFalse(appointment.resource_booking_ids.filtered(lambda row: row.state == "reserved"))
        self.assertTrue(appointment.reminder_ids.filtered(lambda row: row.state == "cancelled"))

    def test_overlapping_appointment_is_rejected(self):
        first = self._new_appointment()
        first.with_user(self.staff).action_request()
        second = self._new_appointment()
        with self.assertRaises(UserError):
            second.with_user(self.staff).action_request()

    def test_same_resource_cannot_be_double_booked_for_two_staff(self):
        second_staff = self._create_user("appointment.staff2", "group_appointment_user")
        self.service.with_user(self.admin).write({"user_ids": [(4, second_staff.id)]})
        self.env["ps.appointment.schedule"].with_user(self.admin).create(
            {
                "user_id": second_staff.id,
                "resource_id": self.resource.id,
                "weekday": str(self.appointment_day.weekday()),
                "start_hour": 8,
                "end_hour": 18,
                "company_id": self.company.id,
            }
        )
        first = self._new_appointment()
        first.with_user(self.staff).action_request()
        second = self._new_appointment()
        with self.assertRaises(UserError):
            second.with_user(self.staff).action_request()

    def test_confirmed_appointment_can_be_started_and_completed(self):
        appointment = self._new_appointment()
        appointment.with_user(self.staff).action_request()
        appointment.with_user(self.manager).action_confirm()
        appointment.with_user(self.staff).action_start()
        appointment.with_user(self.staff).action_done()
        self.assertEqual(appointment.state, "done")
        self.assertFalse(appointment.resource_booking_ids.filtered(lambda row: row.state == "reserved"))

    def test_staff_cannot_see_another_users_unassigned_draft(self):
        own = self._new_appointment()
        other = self._new_appointment(user=self.receptionist)
        other.with_user(self.receptionist).write({"user_id": self.receptionist.id})
        visible = self.env["ps.appointment"].with_user(self.staff).search([])
        self.assertIn(own, visible)
        self.assertNotIn(other, visible)

    def test_users_cannot_delete_appointments_or_edit_audit_history(self):
        appointment = self._new_appointment()
        with self.assertRaises(AccessError):
            appointment.with_user(self.staff).unlink()
        with self.assertRaises(AccessError):
            appointment.with_user(self.staff).write(
                {"state": "cancelled", "state_date": fields.Datetime.now()}
            )
        with self.assertRaises(AccessError):
            appointment.history_ids.with_user(self.staff).create(
                {
                    "appointment_id": appointment.id,
                    "event_type": "linked",
                    "user_id": self.staff.id,
                    "company_id": self.company.id,
                }
            )

    def test_slot_generation_is_idempotent(self):
        wizard = self.env["ps.appointment.slot.generator"].with_user(self.manager).create(
            {
                "appointment_type_id": self.service.id,
                "date_from": self.appointment_day,
                "date_to": self.appointment_day,
            }
        )
        wizard.with_user(self.manager).action_generate()
        first_count = self.env["ps.appointment.slot"].search_count(
            [("appointment_type_id", "=", self.service.id), ("start_datetime", ">=", fields.Datetime.to_string(self.start))]
        )
        wizard.with_user(self.manager).action_generate()
        second_count = self.env["ps.appointment.slot"].search_count(
            [("appointment_type_id", "=", self.service.id), ("start_datetime", ">=", fields.Datetime.to_string(self.start))]
        )
        self.assertGreater(first_count, 0)
        self.assertEqual(first_count, second_count)
