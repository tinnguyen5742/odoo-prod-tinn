from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWarrantyWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.today = fields.Date.today()
        cls.partner = cls.env["res.partner"].create({"name": "Warranty Test Customer"})
        template = cls.env["product.template"].create({"name": "Warranty Test Product"})
        cls.product = template.product_variant_id
        cls.policy = cls.env["ps.warranty.policy"].create(
            {
                "name": "Warranty Test Policy",
                "duration": 12,
                "duration_unit": "month",
                "product_ids": [(6, 0, [cls.product.id])],
                "company_id": cls.company.id,
            }
        )
        cls.user = cls._create_user("warranty.user", "group_warranty_user")
        cls.officer = cls._create_user("warranty.officer", "group_warranty_officer")
        cls.manager = cls._create_user("warranty.manager", "group_warranty_manager")

    @classmethod
    def _create_user(cls, login, group_xmlid):
        group = cls.env.ref(f"ps_warranty.{group_xmlid}")
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

    def _create_registration(self):
        return self.env["ps.warranty.registration"].with_user(self.officer).create(
            {
                "partner_id": self.partner.id,
                "product_id": self.product.id,
                "serial_number": "SERIAL-TEST-001",
                "policy_id": self.policy.id,
                "purchase_date": self.today,
                "start_date": self.today,
                "company_id": self.company.id,
            }
        )

    def _create_claim(self, registration, user=None):
        return self.env["ps.warranty.claim"].with_user(user or self.user).create(
            {
                "registration_id": registration.id,
                "partner_id": self.partner.id,
                "product_id": self.product.id,
                "serial_number": registration.serial_number,
                "description": "<p>Product does not power on.</p>",
                "company_id": self.company.id,
            }
        )

    def test_policy_registration_dates_and_expiry_cron(self):
        registration = self._create_registration()
        expected_end = self.today + relativedelta(months=12) - relativedelta(days=1)
        self.assertEqual(registration.end_date, expected_end)
        registration.with_user(self.officer).action_activate()
        self.assertEqual(registration.state, "active")
        registration.with_user(self.officer).write(
            {"start_date": self.today - relativedelta(years=2)}
        )
        self.env["ps.warranty.registration"]._cron_expire_registrations()
        self.assertEqual(registration.state, "expired")

    def test_registration_context_cannot_bypass_transition_checks(self):
        registration = self._create_registration()
        forged_context = {
            "ps_warranty_state_transition": True,
            "ps_warranty_expiry_cron": True,
        }
        with self.assertRaises(AccessError):
            registration.with_user(self.manager).with_context(**forged_context).write(
                {"state": "expired"}
            )

        self.policy.with_user(self.manager).write({"active": False})
        with self.assertRaises(UserError):
            registration.with_user(self.officer).with_context(**forged_context).write(
                {"state": "active"}
            )

    def test_dashboard_new_actions_follow_warranty_roles(self):
        dashboard_model = self.env["ps.warranty.dashboard"]
        user_dashboard = dashboard_model.with_user(self.user).create({})
        claim_action = user_dashboard.action_new_claim()
        self.assertEqual(claim_action["res_model"], "ps.warranty.claim")
        self.assertEqual(claim_action["context"]["default_company_id"], self.company.id)
        with self.assertRaises(AccessError):
            user_dashboard.action_new_registration()

        officer_dashboard = dashboard_model.with_user(self.officer).create({})
        self.assertEqual(
            officer_dashboard.action_new_registration()["res_model"],
            "ps.warranty.registration",
        )
        self.assertEqual(officer_dashboard.action_new_rma()["res_model"], "ps.warranty.rma")

        manager_dashboard = dashboard_model.with_user(self.manager).create({})
        self.assertEqual(
            manager_dashboard.action_new_policy()["res_model"], "ps.warranty.policy"
        )

    def test_claim_approval_repair_cost_and_rma_flow(self):
        registration = self._create_registration()
        registration.with_user(self.officer).action_activate()
        claim = self._create_claim(registration)
        claim.with_user(self.user).action_submit()
        self.assertEqual(claim.state, "submitted")
        claim.with_user(self.officer).action_start_review()
        self.assertEqual(claim.state, "under_review")
        with self.assertRaises(AccessError):
            claim.with_user(self.officer).action_approve()
        claim.with_user(self.manager).action_approve()
        self.assertEqual(claim.approved_by_id, self.manager)
        self.assertTrue(claim.approved_date)
        claim.with_user(self.officer).action_start_work()
        self.env["ps.warranty.claim.line"].with_user(self.officer).create(
            {
                "claim_id": claim.id,
                "line_type": "part",
                "product_id": self.product.id,
                "name": "Replacement component",
                "quantity": 2,
                "unit_cost": 15,
            }
        )
        self.assertEqual(claim.cost_total, 30)
        action = claim.with_user(self.officer).action_create_rma()
        rma = self.env["ps.warranty.rma"].with_user(self.officer).browse(action["res_id"])
        rma.action_mark_received()
        rma.write(
            {
                "inspection_result": "<p>Fault confirmed.</p>",
                "resolution": "replace",
                "replacement_product_id": self.product.id,
                "replacement_serial": "SERIAL-REPLACEMENT-001",
            }
        )
        rma.action_inspect()
        with self.assertRaises(UserError):
            rma.with_context(ps_warranty_rma_transition=True).write(
                {"state": "returned"}
            )
        rma.action_mark_replaced()
        self.assertEqual(rma.state, "replaced")
        self.assertTrue(rma.date_received)
        self.assertTrue(rma.date_closed)
        claim.with_user(self.officer).write({"resolution_note": "Replaced the faulty component."})
        claim.with_user(self.officer).action_resolve()
        self.assertTrue(claim.resolved_date)
        claim.with_user(self.officer).action_close()
        self.assertEqual(claim.state, "closed")
        self.assertTrue(claim.closed_date)
        self.assertEqual(claim.resolution_days, 0)

    def test_user_cannot_read_another_users_claim(self):
        registration = self._create_registration()
        registration.with_user(self.officer).action_activate()
        claim = self._create_claim(registration)
        other_user = self._create_user("warranty.other", "group_warranty_user")
        other_claim = self._create_claim(registration, user=other_user)
        visible = self.env["ps.warranty.claim"].with_user(self.user).search(
            [("id", "=", other_claim.id)]
        )
        self.assertFalse(visible)
        self.assertTrue(claim.with_user(self.user).exists())

    def test_claim_submission_requires_active_warranty(self):
        registration = self._create_registration()
        claim = self._create_claim(registration)
        with self.assertRaises(UserError):
            claim.with_user(self.user).action_submit()

    def test_rejection_requires_reason(self):
        registration = self._create_registration()
        registration.with_user(self.officer).action_activate()
        claim = self._create_claim(registration)
        claim.with_user(self.user).action_submit()
        claim.with_user(self.officer).action_start_review()
        with self.assertRaises(UserError):
            claim.with_user(self.manager).with_context(
                ps_warranty_state_transition=True,
                review_note="This context value is not a saved rejection reason.",
            ).write({"state": "rejected"})
        with self.assertRaises(UserError):
            claim.with_user(self.manager).action_reject()
        claim.with_user(self.manager).write({"review_note": "Physical damage is outside policy."})
        claim.with_user(self.manager).action_reject()
        self.assertEqual(claim.state, "rejected")
