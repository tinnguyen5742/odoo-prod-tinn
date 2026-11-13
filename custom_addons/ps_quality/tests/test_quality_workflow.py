from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestQualityWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.today = fields.Date.today()
        cls.template = cls.env["product.template"].create({"name": "Quality Test Product"})
        cls.product = cls.template.product_variant_id
        cls.admin = cls._create_user("quality.admin", "group_quality_administrator")
        cls.manager = cls._create_user("quality.manager", "group_quality_manager")
        cls.inspector = cls._create_user("quality.inspector", "group_quality_inspector")
        cls.user = cls._create_user("quality.user", "group_quality_user")

    @classmethod
    def _create_user(cls, login, group_xmlid):
        group = cls.env.ref(f"ps_quality.{group_xmlid}")
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

    def _create_active_standard(self):
        standard = self.env["ps.quality.standard"].with_user(self.admin).create(
            {
                "name": "Quality Test Standard",
                "product_id": self.product.id,
                "company_id": self.company.id,
            }
        )
        self.env["ps.quality.standard.line"].with_user(self.admin).create(
            {
                "standard_id": standard.id,
                "name": "Dimension",
                "criterion_type": "numeric",
                "has_minimum": True,
                "min_value": 4,
                "has_maximum": True,
                "max_value": 6,
                "unit": "mm",
            }
        )
        standard.with_user(self.admin).action_activate()
        return standard

    def _create_inspection(self, standard, quantity=1):
        inspection = self.env["ps.quality.inspection"].with_user(self.inspector).create(
            {
                "standard_id": standard.id,
                "product_id": self.product.id,
                "inspector_id": self.inspector.id,
                "inspection_type": "iqc",
                "quantity_sampled": quantity,
                "quantity_passed": quantity,
                "company_id": self.company.id,
            }
        )
        inspection.with_user(self.inspector).action_confirm()
        inspection.with_user(self.inspector).action_start()
        return inspection

    def test_standard_versioning_and_active_criteria_are_immutable(self):
        standard = self._create_active_standard()
        with self.assertRaises(UserError):
            standard.line_ids.with_user(self.admin).write({"name": "Changed"})
        action = standard.with_user(self.admin).action_new_version()
        version = self.env["ps.quality.standard"].browse(action["res_id"])
        self.assertEqual(version.version, standard.version + 1)
        self.assertEqual(standard.state, "obsolete")
        self.assertEqual(version.line_ids.mapped("name"), ["Dimension"])

    def test_plan_generates_inspection_and_advances_recurring_schedule(self):
        standard = self._create_active_standard()
        plan = self.env["ps.quality.plan"].with_user(self.manager).create(
            {
                "name": "Daily incoming inspection",
                "product_id": self.product.id,
                "standard_id": standard.id,
                "inspection_type": "iqc",
                "frequency": "daily",
                "frequency_interval": 2,
                "sample_size": 3,
                "next_date": self.today,
                "inspector_id": self.inspector.id,
                "company_id": self.company.id,
            }
        )
        plan.with_user(self.manager).action_activate()
        action = plan.with_user(self.inspector).action_create_inspection()
        inspection = self.env["ps.quality.inspection"].browse(action["res_id"])
        self.assertEqual(inspection.quantity_sampled, 3)
        self.assertEqual(inspection.inspector_id, self.inspector)
        self.assertEqual(plan.next_date, self.today + timedelta(days=2))

    def test_pass_and_fail_results_and_automatic_ncr(self):
        standard = self._create_active_standard()
        passed = self._create_inspection(standard)
        with self.assertRaises(AccessError):
            passed.line_ids.with_user(self.user).write({"observed_value": "5"})
        passed.line_ids.with_user(self.inspector).write({"observed_value": "5.25"})
        passed.with_user(self.inspector).action_complete()
        self.assertEqual((passed.state, passed.result), ("passed", "pass"))

        failed = self._create_inspection(standard)
        failed.line_ids.with_user(self.inspector).write({"observed_value": "7.0"})
        failed.with_user(self.inspector).write(
            {"quantity_passed": 0, "quantity_failed": 1, "disposition": "quarantine"}
        )
        failed.with_user(self.inspector).action_complete()
        self.assertEqual((failed.state, failed.result), ("failed", "fail"))
        self.assertEqual(len(failed.ncr_ids), 1)
        self.assertEqual(failed.ncr_ids.source_type, "iqc")

    def test_ncr_capa_effectiveness_and_inspection_close_flow(self):
        standard = self._create_active_standard()
        inspection = self._create_inspection(standard)
        inspection.line_ids.with_user(self.inspector).write({"observed_value": "8"})
        inspection.with_user(self.inspector).write(
            {"quantity_passed": 0, "quantity_failed": 1, "disposition": "quarantine"}
        )
        inspection.with_user(self.inspector).action_complete()
        ncr = inspection.ncr_ids
        ncr.with_user(self.inspector).write(
            {
                "root_cause": "<p>Supplier process variation</p>",
                "containment_action": "<p>Quarantined the lot</p>",
                "disposition": "return",
            }
        )
        ncr.with_user(self.inspector).action_start_analysis()
        ncr.with_user(self.manager).action_plan_actions()
        action = ncr.with_user(self.manager).action_create_capa()
        capa = self.env["ps.quality.capa"].browse(action["res_id"])
        self.assertTrue(capa.due_date)
        capa.with_user(self.manager).write(
            {
                "root_cause": "<p>Supplier process variation</p>",
                "corrective_action": "<p>Replace rejected goods</p>",
                "preventive_action": "<p>Increase incoming sampling</p>",
            }
        )
        capa.with_user(self.manager).action_start()
        attachment = self.env["ir.attachment"].sudo().create(
            {
                "name": "quality-evidence.txt",
                "type": "binary",
                "datas": "UXVhbGl0eSBldmlkZW5jZQ==",
                "res_model": capa._name,
                "res_id": capa.id,
            }
        )
        capa.with_user(self.manager).write(
            {"evidence_attachment_ids": [(4, attachment.id)]}
        )
        capa.with_user(self.inspector).action_submit_effectiveness()
        capa.with_user(self.manager).write(
            {"effectiveness_result": "ineffective", "effectiveness_note": "<p>Not yet sustained</p>"}
        )
        capa.with_user(self.manager).action_evaluate_effectiveness()
        self.assertEqual(capa.state, "ineffective")
        capa.with_user(self.inspector).action_start()
        self.assertEqual((capa.state, capa.effectiveness_result), ("open", "pending"))
        capa.with_user(self.inspector).action_submit_effectiveness()
        capa.with_user(self.manager).write(
            {"effectiveness_result": "effective", "effectiveness_note": "<p>Verified after retry</p>"}
        )
        capa.with_user(self.manager).action_evaluate_effectiveness()
        capa.with_user(self.manager).action_close()
        ncr.with_user(self.inspector).action_verify()
        ncr.with_user(self.manager).action_close()
        inspection.with_user(self.manager).action_approve()
        inspection.with_user(self.inspector).action_close()
        self.assertEqual((capa.state, ncr.state, inspection.state), ("closed", "closed", "closed"))

    def test_calibration_history_and_failed_result_takes_equipment_out_of_service(self):
        equipment = self.env["ps.quality.equipment"].with_user(self.manager).create(
            {
                "name": "Test caliper",
                "calibration_interval_days": 365,
                "warning_days": 30,
                "responsible_id": self.manager.id,
                "company_id": self.company.id,
            }
        )
        calibration = self.env["ps.quality.calibration"].with_user(self.inspector).create(
            {
                "equipment_id": equipment.id,
                "result": "fail",
                "calibrated_by_id": self.inspector.id,
                "company_id": self.company.id,
            }
        )
        calibration.with_user(self.inspector).action_confirm()
        self.assertEqual(equipment.last_calibration_date, self.today)
        self.assertEqual(equipment.next_calibration_date, self.today + timedelta(days=365))
        self.assertTrue(equipment.out_of_service)
        self.assertEqual(equipment.calibration_state, "out_of_service")

    def test_calibration_due_cron_creates_only_one_reminder(self):
        equipment = self.env["ps.quality.equipment"].with_user(self.manager).create(
            {
                "name": "Due calibration test gauge",
                "calibration_interval_days": 365,
                "last_calibration_date": self.today - timedelta(days=335),
                "warning_days": 30,
                "responsible_id": self.manager.id,
                "company_id": self.company.id,
            }
        )
        equipment_model = self.env["ps.quality.equipment"]
        equipment_model._cron_calibration_due()
        equipment_model._cron_calibration_due()
        reminder_count = self.env["mail.activity"].sudo().search_count(
            [
                ("res_model", "=", equipment._name),
                ("res_id", "=", equipment.id),
                ("summary", "=", "Measurement equipment calibration due"),
                ("date_done", "=", False),
            ]
        )
        self.assertEqual(reminder_count, 1)

    def test_quality_user_cannot_activate_standard(self):
        standard = self.env["ps.quality.standard"].with_user(self.admin).create(
            {
                "name": "Draft standard",
                "product_id": self.product.id,
                "company_id": self.company.id,
            }
        )
        self.env["ps.quality.standard.line"].with_user(self.admin).create(
            {"standard_id": standard.id, "name": "Visual check", "criterion_type": "pass_fail"}
        )
        with self.assertRaises(AccessError):
            standard.with_user(self.user).action_activate()

    def test_optional_erp_references_only_advertise_installed_models(self):
        inspection_model = self.env["ps.quality.inspection"]
        selections = (
            inspection_model._selection_purchase_orders(),
            inspection_model._selection_productions(),
            inspection_model._selection_sale_orders(),
            inspection_model._selection_pickings(),
            inspection_model._selection_lots(),
            self.env["ps.quality.equipment"]._selection_maintenance_equipment(),
        )
        for selection in selections:
            for model_name, _label in selection:
                self.assertIn(model_name, self.env.registry.models)
