from datetime import timedelta, timezone
from odoo import fields, Command
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import AccessError, UserError, ValidationError


@tagged("post_install", "-at_install")
class TestEAM(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.team = cls.env["maintenance.team"].create({"name": "EAM QA", "company_id": cls.company.id})
        cls.eq = cls.env["maintenance.equipment"].create({
            "name": "Máy QA", "company_id": cls.company.id, "maintenance_team_id": cls.team.id,
            "cost": 1000, "effective_date": fields.Date.today() - timedelta(days=60)})
        cls.tech = cls.env["res.users"].create({
            "name": "EAM Technician", "login": "eam_qa_tech",
            "company_id": cls.company.id, "company_ids": [Command.set(cls.company.ids)],
            "group_ids": [Command.set([cls.env.ref("ps_enterprise_asset.group_eam_user").id])]})
        cls.manager = cls.env["res.users"].create({
            "name": "EAM Manager", "login": "eam_qa_manager",
            "company_id": cls.company.id, "company_ids": [Command.set(cls.company.ids)],
            "group_ids": [Command.set([cls.env.ref("ps_enterprise_asset.group_eam_manager").id,
                                     cls.env.ref("stock.group_stock_user").id,
                                     cls.env.ref("purchase.group_purchase_user").id])]})

    def order(self, **values):
        return self.env["maintenance.request"].create(dict({
            "name": "Sửa máy", "company_id": self.company.id,
            "equipment_id": self.eq.id, "eam_managed": True}, **values))

    def ready(self, rec):
        rec.with_user(self.manager).action_approve()
        rec.with_user(self.tech).action_start()
        rec.write({"root_cause": "Vòng bi mòn", "resolution": "Thay vòng bi",
                   "actual_hours": 2, "hourly_rate": 50, "acceptance_signature": b"c2lnbmF0dXJl"})

    def test_equipment_cycle_and_warranty_dates(self):
        child = self.eq.copy({"name": "Cụm con", "parent_id": self.eq.id})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.eq.parent_id = child
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.eq.write({"warranty_start": "2026-10-22", "warranty_date": "2026-10-21"})

    def test_time_plan_idempotence_and_completion(self):
        today = fields.Date.today()
        plan = self.env["ps.eam.plan"].create({
            "name": "PM tháng", "equipment_id": self.eq.id,
            "next_date": today, "checklist": "Vệ sinh\nKiểm tra dầu"})
        plan.action_generate()
        plan.action_generate()
        self.assertEqual(len(plan.request_ids), 1)
        order = plan.request_ids
        self.assertEqual(len(order.eam_check_ids), 2)
        self.ready(order)
        order.eam_check_ids.write({"checked": True})
        order.with_user(self.manager).action_done()
        self.assertGreater(plan.next_date, today)
        plan.action_generate()
        self.assertEqual(len(plan.request_ids), 1)

    def test_cancelled_plan_can_generate_again(self):
        plan = self.env["ps.eam.plan"].create({"name": "PM", "equipment_id": self.eq.id})
        plan.action_generate()
        plan.request_ids.with_user(self.manager).action_cancel()
        plan.action_generate()
        self.assertEqual(len(plan.request_ids), 2)

    def test_counter_monotonic_and_usage_plan(self):
        meter = self.env["ps.eam.meter"].create({"name": "Giờ chạy", "equipment_id": self.eq.id})
        plan = self.env["ps.eam.plan"].create({
            "name": "PM 100h", "equipment_id": self.eq.id, "trigger": "usage",
            "meter_id": meter.id, "next_value": 100, "usage_interval": 100})
        self.env["ps.eam.reading"].with_user(self.tech).create({"meter_id": meter.id, "value": 101})
        self.assertEqual(len(plan.request_ids), 1)
        plan.action_generate()
        self.assertEqual(len(plan.request_ids), 1)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["ps.eam.reading"].create({"meter_id": meter.id, "value": 99})
        self.ready(plan.request_ids)
        plan.request_ids.with_user(self.manager).action_done()
        self.assertEqual(plan.next_value, 201)

    def test_threshold_alert_deduplication(self):
        meter = self.env["ps.eam.meter"].create({
            "name": "Nhiệt độ", "equipment_id": self.eq.id, "kind": "condition",
            "unit": "C", "lower_limit": 10, "upper_limit": 80})
        readings = self.env["ps.eam.reading"].with_user(self.tech)
        readings.create({"meter_id": meter.id, "value": 90, "source": "event-1"})
        readings.create({"meter_id": meter.id, "value": 95, "source": "event-2"})
        orders = self.env["maintenance.request"].search([("eam_meter_id", "=", meter.id)])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders.priority, "3")
        with self.assertRaises(UserError):
            meter.reading_ids[:1].write({"value": 70})

    def test_workflow_approval_and_checklist(self):
        order = self.order(eam_check_ids=[Command.create({"name": "Kiểm tra an toàn"})])
        with self.assertRaises(AccessError):
            order.with_user(self.tech).action_approve()
        self.ready(order)
        with self.assertRaises(UserError):
            order.with_user(self.manager).action_done()
        with self.assertRaises(AccessError):
            order.eam_check_ids.with_user(self.tech).write({"required": False})
        with self.assertRaises(AccessError):
            order.eam_check_ids.with_user(self.tech).unlink()
        order.eam_check_ids.with_user(self.tech).write({"checked": True, "result": "Đạt"})
        order.with_user(self.manager).action_done()
        self.assertEqual(order.eam_state, "done")
        self.assertEqual(order.acceptance_user_id, self.manager)
        self.assertEqual(order.eam_total_cost, 100)
        with self.assertRaises(UserError):
            order.write({"actual_hours": 10})
        with self.assertRaises(UserError):
            order.eam_check_ids.write({"checked": False})
        with self.assertRaises(UserError):
            order.unlink()

    def test_native_stage_cannot_bypass_acceptance(self):
        order = self.order()
        with self.assertRaises(UserError):
            order.stage_id = self.env.ref("maintenance.stage_3")
        with self.assertRaises(UserError):
            order.eam_managed = False

    def test_claim_coverage_start_and_end(self):
        self.eq.write({"warranty_start": "2026-01-01", "warranty_date": "2026-12-31"})
        claim = self.env["ps.eam.claim"].create({
            "equipment_id": self.eq.id, "partner_id": self.env.company.partner_id.id,
            "claim_date": "2025-12-31"})
        self.assertFalse(claim.covered)
        claim.claim_date = "2026-06-01"
        self.assertTrue(claim.covered)
        claim.claim_date = "2027-01-01"
        self.assertFalse(claim.covered)

    def test_oee_and_validation(self):
        log = self.env["ps.eam.operation"].create({
            "equipment_id": self.eq.id, "planned_hours": 8, "running_hours": 6,
            "ideal_cycle_seconds": 60, "total_qty": 300, "good_qty": 270})
        self.assertAlmostEqual(log.availability, 75)
        self.assertAlmostEqual(log.performance, 83.333333, places=4)
        self.assertAlmostEqual(log.quality, 90)
        self.assertAlmostEqual(log.oee, 56.25)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            log.running_hours = 9

    def test_multi_company_isolation(self):
        other = self.env["res.company"].create({"name": "EAM Other Company"})
        other_eq = self.env["maintenance.equipment"].create({"name": "Other", "company_id": other.id})
        meter = self.env["ps.eam.meter"].create({
            "name": "Other Meter", "equipment_id": other_eq.id, "company_id": other.id})
        self.assertFalse(self.env["ps.eam.meter"].with_user(self.tech).search([("id", "=", meter.id)]))
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env["ps.eam.plan"].create({"name": "Invalid", "equipment_id": other_eq.id, "company_id": self.company.id})

    def test_stock_consumption_and_cost(self):
        product = self.env["product.product"].create({
            "name": "Vòng bi QA", "type": "consu", "is_storable": True, "standard_price": 25})
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        destination = self.env["stock.location"].create({
            "name": "Tiêu hao EAM QA", "usage": "inventory", "company_id": self.company.id,
            "eam_consumption": True})
        self.env["stock.quant"]._update_available_quantity(product, warehouse.lot_stock_id, 10)
        order = self.order(part_ids=[Command.create({"product_id": product.id, "quantity": 2})])
        order.with_user(self.manager).action_approve()
        order.with_user(self.manager).action_create_picking()
        order.with_user(self.manager).action_create_picking()
        self.assertEqual(len(order.picking_ids), 1)
        picking = order.picking_ids
        self.assertEqual(picking.location_dest_id, destination)
        self.assertEqual(order.eam_parts_cost, 0)
        picking.action_assign()
        picking.move_ids.write({"quantity": 2, "picked": True})
        picking.with_user(self.manager).button_validate()
        self.assertEqual(picking.state, "done")
        self.assertEqual(order.eam_parts_cost, 50)
        quant = self.env["stock.quant"].search([("product_id", "=", product.id),
                                               ("location_id", "=", warehouse.lot_stock_id.id)])
        self.assertEqual(sum(quant.mapped("quantity")), 8)

    def test_rfq_uses_product_uom(self):
        product = self.env["product.product"].create({"name": "Phụ tùng mua", "type": "consu"})
        vendor = self.env["res.partner"].create({"name": "EAM Vendor"})
        order = self.order(part_ids=[Command.create({"product_id": product.id, "quantity": 3, "vendor_id": vendor.id})])
        part = order.part_ids
        part.with_user(self.manager).action_rfq()
        part.with_user(self.manager).action_rfq()
        self.assertEqual(len(part.purchase_id.order_line), 1)
        self.assertEqual(part.purchase_id.order_line.product_qty, 3)
        self.assertEqual(part.purchase_id.state, "draft")

    def test_warranty_alert_is_not_duplicated(self):
        self.eq.warranty_date = fields.Date.today() + timedelta(days=5)
        self.eq._cron_warranty_alert()
        self.eq._cron_warranty_alert()
        alerts = self.eq.activity_ids.filtered(lambda a: a.summary == "Bảo hành nhà cung cấp sắp hết hạn")
        self.assertEqual(len(alerts), 1)

    def test_eam_menu_views_and_permissions(self):
        for action_name, expected in [("equipment_action", "list"), ("request_action", "list"),
                                      ("calendar_action", "calendar"), ("cost_action", "pivot")]:
            action = self.env.ref("ps_enterprise_asset." + action_name)
            self.assertEqual(action.views[0][1], expected)
        views = self.env["ir.ui.view"].search([("id", "in",
            self.env["ir.model.data"].search([("module", "=", "ps_enterprise_asset"), ("model", "=", "ir.ui.view")]).mapped("res_id"))])
        operator = self.integration_user("eam_views_operator", "ps_enterprise_asset.group_eam_operator")
        buyer = self.integration_user("eam_views_buyer", "purchase.group_purchase_manager")
        accountant = self.integration_user("eam_views_accountant", "account.group_account_manager")
        planner = self.integration_user("eam_views_planner", "mrp.group_mrp_user")
        restricted = {
            "ps.eam.breakdown": (operator, self.tech, self.manager),
            "ps.eam.depreciation": (accountant,),
            "ps.eam.purchase.requisition": (buyer,),
            "purchase.order": (buyer,),
            "resource.calendar.leaves": (planner,),
            "mrp.workcenter": (planner,),
            "stock.picking": (self.manager,),
            "stock.location": (self.manager,),
        }
        for view in views.filtered(lambda item: item.type != "qweb"):
            for user in restricted.get(view.model, (self.tech, self.manager)):
                self.env[view.model].with_user(user).get_view(view.id, view.type)

    def test_create_cannot_bypass_workflow(self):
        with self.assertRaises(UserError):
            self.order(stage_id=self.env.ref("maintenance.stage_3").id)
        native = self.env["maintenance.request"].create({"name": "Native", "maintenance_team_id": self.team.id})
        with self.assertRaises(UserError):
            native.write({"eam_managed": True, "eam_state": "done"})

    def test_work_order_report_html(self):
        order = self.order()
        html, _ = self.env["ir.actions.report"]._render_qweb_html(
            "ps_enterprise_asset.report_work_order", order.ids)
        self.assertIn(order.eam_number.encode(), html)

    def test_tech_cannot_reconfigure_plan(self):
        plan = self.env["ps.eam.plan"].create({"name": "PM", "equipment_id": self.eq.id})
        with self.assertRaises(AccessError):
            plan.with_user(self.tech).write({"interval": 5})

    def test_extra_pdf_reports_render_empty_relations(self):
        plan = self.env["ps.eam.plan"].create({"name": "PDF plan", "equipment_id": self.eq.id})
        meter = self.env["ps.eam.meter"].create({
            "name": "PDF meter", "equipment_id": self.eq.id, "kind": "condition", "unit": "C"})
        claim = self.env["ps.eam.claim"].create({
            "equipment_id": self.eq.id, "partner_id": self.env.user.partner_id.id})
        operation = self.env["ps.eam.operation"].create({
            "equipment_id": self.eq.id, "date": fields.Date.today(),
            "planned_hours": 8, "running_hours": 4, "ideal_cycle_seconds": 60,
            "total_qty": 240, "good_qty": 240})
        for key, records in [("equipment", self.eq), ("plan", plan), ("claim", claim),
                             ("meter", meter), ("operation", operation)]:
            action = self.env.ref("ps_enterprise_asset.report_" + key)
            self.assertEqual(action.binding_model_id.model, records._name)
            html, _ = action.with_user(self.manager)._render_qweb_html(action.report_name, records.ids)
            self.assertIn(self.company.name.encode(), html)
            if key == "operation":
                from lxml import html as lhtml
                tree = lhtml.fromstring(html)
                summary = tree.xpath("//table[1]/tbody/tr[3]/td")
                self.assertEqual(summary[0].text_content().strip(), "50.00")

    def test_cost_pdf_only_totals_selected_eam_orders(self):
        from lxml import html as lhtml
        first = self.order(eam_budget=200, actual_hours=2, hourly_rate=30,
                           cost_ids=[Command.create({"name": "Service", "amount": 45})])
        second = self.order(eam_budget=100, actual_hours=1, hourly_rate=20)
        self.order(eam_budget=9999, actual_hours=100, hourly_rate=100)
        native = self.env["maintenance.request"].create({
            "name": "Not an EAM order", "equipment_id": self.eq.id,
            "company_id": self.company.id, "actual_hours": 50, "hourly_rate": 100})
        html, _ = self.env.ref("ps_enterprise_asset.report_cost").with_user(self.manager)._render_qweb_html(
            "ps_enterprise_asset.cost_document", (first | second | native).ids)
        tree = lhtml.fromstring(html)
        rows = tree.xpath("//table[1]/tbody/tr")
        self.assertIn("300.00", rows[0].text_content())
        self.assertIn("125.00", rows[4].text_content())
        self.assertNotIn(native.name.encode(), html)
        self.assertIn(first.eam_number.encode(), html)
        self.assertIn(second.eam_number.encode(), html)

    def test_quarterly_plan_and_repair_elapsed_time(self):
        from dateutil.relativedelta import relativedelta
        today = fields.Date.today()
        plan = self.env["ps.eam.plan"].create({
            "name": "PM theo quý", "equipment_id": self.eq.id, "unit": "quarter", "next_date": today})
        plan.action_generate()
        order = plan.request_ids
        self.ready(order)
        started = fields.Datetime.now() - timedelta(hours=4)
        order.write({"work_started": started})
        order.with_user(self.manager).action_done()
        self.assertEqual(plan.next_date, today + relativedelta(months=3))
        self.assertAlmostEqual(order.eam_repair_hours, 4, places=2)
        self.assertEqual(order.actual_hours, 2)
        self.assertEqual(self.eq.eam_mttr_hours, 0)  # preventive work is excluded

    def test_mttr_uses_elapsed_time_not_labour_hours(self):
        order = self.order()
        self.ready(order)
        order.work_started = fields.Datetime.now() - timedelta(hours=3)
        order.with_user(self.manager).action_done()
        self.assertAlmostEqual(self.eq.eam_mttr_hours, 3, places=2)
        with self.assertRaises(UserError):
            order.with_user(self.tech).write({"work_started": fields.Datetime.now()})
        with self.assertRaises(UserError):
            order.with_user(self.manager).write({"maintenance_type": "preventive"})

    def test_equipment_oee_aggregates_underlying_values(self):
        logs = self.env["ps.eam.operation"]
        logs.create({"equipment_id": self.eq.id, "date": fields.Date.today(),
                     "planned_hours": 8, "running_hours": 4, "ideal_cycle_seconds": 60,
                     "total_qty": 240, "good_qty": 240})
        logs.create({"equipment_id": self.eq.id, "date": fields.Date.today() - timedelta(days=1),
                     "planned_hours": 2, "running_hours": 2, "ideal_cycle_seconds": 60,
                     "total_qty": 120, "good_qty": 60})
        self.assertAlmostEqual(self.eq.eam_availability, 60)
        self.assertAlmostEqual(self.eq.eam_performance, 100)
        self.assertAlmostEqual(self.eq.eam_oee, 50)
        self.eq.depreciation_recorded = 250
        self.assertEqual(self.eq.eam_book_value, 750)

    def test_warranty_claim_shortcut_and_creation_rights(self):
        order = self.order()
        action = order.with_user(self.tech).action_eam_claim()
        self.assertEqual(action["context"]["default_equipment_id"], self.eq.id)
        self.assertEqual(action["context"]["default_request_id"], order.id)
        with self.assertRaises(AccessError):
            self.env["ps.eam.claim"].with_user(self.tech).create({
                "equipment_id": self.eq.id, "partner_id": self.company.partner_id.id, "state": "accepted"})

    def test_production_reservation_lifecycle(self):
        center = self.env["mrp.workcenter"].create({"name": "Máy QA MRP", "company_id": self.company.id})
        self.eq.eam_workcenter_id = center
        now = fields.Datetime.now()
        order = self.order(schedule_date=now, schedule_end=now + timedelta(hours=2))
        order.with_user(self.manager).action_approve()
        leaves = self.env["resource.calendar.leaves"].search([("eam_request_id", "=", order.id)])
        self.assertEqual(len(leaves), 1)
        self.assertEqual(leaves.resource_id, center.resource_id)
        self.assertEqual(leaves.time_type, "leave")
        order.with_user(self.manager).write({"schedule_end": now + timedelta(hours=3)})
        self.assertEqual(leaves.date_to, now + timedelta(hours=3))
        with self.assertRaises(UserError):
            self.eq.eam_workcenter_id = False
        order.with_user(self.manager).action_cancel()
        self.assertFalse(leaves.exists())

    def test_production_start_blocked_during_maintenance(self):
        center = self.env["mrp.workcenter"].create({"name": "Máy QA stop", "company_id": self.company.id})
        self.eq.eam_workcenter_id = center
        now = fields.Datetime.now()
        order = self.order(schedule_date=now - timedelta(minutes=1), schedule_end=now + timedelta(hours=1))
        order.with_user(self.manager).action_approve()
        product = self.env["product.product"].create({"name": "Sản phẩm QA", "type": "consu"})
        production = self.env["mrp.production"].create({"product_id": product.id, "product_qty": 1})
        wo = self.env["mrp.workorder"].create({"name": "QA công đoạn", "workcenter_id": center.id,
                                             "production_id": production.id, "product_uom_id": product.uom_id.id})
        with self.assertRaises(UserError):
            wo.button_start()

    def test_schedule_validation_and_approved_equipment_lock(self):
        now = fields.Datetime.now()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.order(schedule_date=now, schedule_end=now - timedelta(hours=1))
        order = self.order()
        order.with_user(self.manager).action_approve()
        with self.assertRaises(UserError):
            order.equipment_id = self.eq.copy()

    def test_service_vendor_bill_draft_and_idempotence(self):
        expense, _, _, _ = self.setup_eam_accounts()
        vendor = self.setup_eam_vendor(expense)
        cost = self.order(cost_ids=[Command.create({"name": "Cân chỉnh", "amount": 125,
                                                   "vendor_id": vendor.id})]).cost_ids
        cost.action_vendor_bill()
        first = cost.bill_id
        cost.action_vendor_bill()
        self.assertEqual(cost.bill_id, first)
        self.assertEqual(first.state, "draft")
        self.assertEqual(first.move_type, "in_invoice")
        self.assertEqual(first.amount_total, 125)
        self.assertEqual(first.invoice_origin, cost.request_id.eam_number)
        self.assertEqual(cost.request_id.eam_total_cost, 125)


    def test_scope_has_seven_business_areas_and_keeps_requested_extras(self):
        root = self.env.ref("ps_enterprise_asset.menu_eam")
        expected = self.env["ir.ui.menu"]
        for key in ("equipment", "claim", "preventive", "condition", "request", "mro", "analytics"):
            expected |= self.env.ref("ps_enterprise_asset.menu_" + key)
        self.assertEqual(set(root.with_context(active_test=False).child_id.ids), set(expected.ids))
        self.assertFalse(self.env.ref("ps_enterprise_asset.menu_mro").active)
        self.assertTrue(self.env.ref("ps_enterprise_asset.menu_eam_spares_inventory").active)
        self.assertTrue(self.env.ref("ps_enterprise_asset.menu_requisition_purchase").active)
        for key in ("equipment", "plan", "claim", "meter", "cost", "operation", "work_order"):
            self.assertTrue(self.env.ref("ps_enterprise_asset.report_" + key).exists())
        self.assertTrue(self.env.ref("ps_enterprise_asset.cron_warranty").active)
        action = self.env.ref("ps_enterprise_asset.equipment_kpi_action")
        self.assertEqual(action.views[0][1], "list")
        self.assertIn((self.env.ref("ps_enterprise_asset.equipment_form").id, "form"), action.views)

    def test_mro_catalogue_and_reorder_scope(self):
        from odoo.tools.safe_eval import safe_eval
        spare = self.env["product.product"].create({
            "name": "MRO spare", "type": "consu", "eam_mro": True, "is_storable": True})
        finished = self.env["product.product"].create({
            "name": "Unrelated finished goods", "type": "consu", "is_storable": True})
        action = self.env.ref("ps_enterprise_asset.spare_action")
        products = self.env["product.product"].search(safe_eval(action.domain))
        self.assertIn(spare, products)
        self.assertNotIn(finished, products)
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        points = self.env["stock.warehouse.orderpoint"].create([
            {"product_id": p.id, "location_id": warehouse.lot_stock_id.id,
             "product_min_qty": 1, "product_max_qty": 5} for p in (spare, finished)])
        visible = self.env["stock.warehouse.orderpoint"].search(
            safe_eval(self.env.ref("ps_enterprise_asset.reorder_action").domain))
        self.assertIn(points[0], visible)
        self.assertNotIn(points[1], visible)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["product.product"].create({"name": "Invalid MRO service", "type": "service", "eam_mro": True})
        for model, view in (("product.template", "product_template_mro_form"),
                            ("product.product", "product_variant_mro_form")):
            self.env[model].with_user(self.manager).get_view(self.env.ref("ps_enterprise_asset." + view).id, "form")


    def integration_user(self, login, *groups):
        return self.env["res.users"].create({
            "name": login, "login": login, "company_id": self.company.id,
            "company_ids": [Command.set(self.company.ids)],
            "group_ids": [Command.set([self.env.ref(group).id for group in groups])],
        })

    def test_operator_breakdown_is_private_and_stops_production(self):
        operator = self.integration_user("eam_operator_qa", "ps_enterprise_asset.group_eam_operator")
        colleague = self.integration_user("eam_operator_other_qa", "ps_enterprise_asset.group_eam_operator")
        center = self.env["mrp.workcenter"].create({"name": "Trung tâm sự cố QA", "company_id": self.company.id})
        self.eq.eam_workcenter_id = center
        reports = self.env["ps.eam.breakdown"].with_user(operator)
        report = reports.create({
            "name": "Máy dừng", "equipment_id": self.eq.id, "description": "Motor ngừng quay", "urgent": True,
        })
        self.assertEqual(report.state, "draft")
        self.assertFalse(reports.with_user(colleague).search([("id", "=", report.id)]))
        with self.assertRaises(AccessError), self.cr.savepoint():
            report.write({"urgent": False})
        order = report.with_user(self.manager).request_id
        self.assertTrue(order.eam_breakdown_stop)
        self.assertEqual(center.eam_availability_state, "breakdown")
        self.assertEqual(order.maintenance_type, "corrective")
        self.assertEqual(order.priority, "3")
        product = self.env["product.product"].create({"name": "Thành phẩm sự cố", "type": "consu"})
        production = self.env["mrp.production"].create({"product_id": product.id, "product_qty": 1})
        workorder = self.env["mrp.workorder"].create({
            "name": "Công đoạn sự cố", "production_id": production.id, "workcenter_id": center.id,
            "product_uom_id": product.uom_id.id,
        })
        with self.assertRaises(UserError), self.cr.savepoint():
            workorder.button_start()
        order.action_cancel()
        self.assertEqual(report.state, "cancelled")

    def test_tool_cannot_be_issued_twice_or_leave_order_open(self):
        tool = self.eq.copy({"name": "Máy đo QA", "eam_is_tool": True})
        orders = self.order() | self.order()
        loans = self.env["ps.eam.tool.loan"].create([
            {"request_id": order.id, "tool_id": tool.id} for order in orders
        ])
        for order in orders:
            self.ready(order)
        loans[0].with_user(self.tech).action_issue()
        with self.assertRaises(UserError), self.cr.savepoint():
            loans[1].with_user(self.tech).action_issue()
        with self.assertRaises(UserError), self.cr.savepoint():
            orders[0].with_user(self.manager).action_done()
        loans[0].with_user(self.tech).action_return()
        orders[0].with_user(self.manager).action_done()
        loans[1].with_user(self.tech).action_issue()
        self.assertEqual(loans.mapped("state"), ["returned", "issued"])

    def test_mqtt_deduplication_and_permissions(self):
        user = self.integration_user("eam_mqtt_qa", "ps_enterprise_asset.group_eam_mqtt")
        meter = self.env["ps.eam.meter"].create({
            "name": "Nhiệt độ MQTT", "equipment_id": self.eq.id, "kind": "condition",
            "eam_mqtt_topic": "factory/press/temperature", "upper_limit": 80,
        })
        data = {
            "topic": meter.eam_mqtt_topic, "event_id": "press-001", "value": 90,
            "measured_at": fields.Datetime.now().replace(tzinfo=timezone.utc).isoformat(),
        }
        gateway = self.env["ps.eam.meter"].with_user(user)
        initial = gateway.eam_ingest_mqtt(**data)
        duplicate = gateway.eam_ingest_mqtt(**data)
        self.assertFalse(initial["duplicate"])
        self.assertEqual(duplicate, {"id": initial["id"], "duplicate": True})
        self.assertEqual(len(meter.reading_ids), 1)
        self.assertTrue(meter.alert_request_id)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            gateway.eam_ingest_mqtt(**dict(data, value=95))
        with self.assertRaises(AccessError), self.cr.savepoint():
            gateway.with_user(self.tech).eam_ingest_mqtt(**data)

    def test_customer_warranty_notice_and_reminder(self):
        self.eq.customer_warranty_end = fields.Date.today() + timedelta(days=10)
        self.assertIn("khách hàng", self.order().warranty_notice)
        self.eq._cron_warranty_alert()
        self.eq._cron_warranty_alert()
        reminders = self.eq.activity_ids.filtered(lambda activity: "khách hàng" in activity.summary)
        self.assertEqual(len(reminders), 1)

    def test_mro_orderpoint_requires_purchase_approval(self):
        buyer = self.integration_user("eam_purchase_manager_qa", "purchase.group_purchase_manager")
        self.company.eam_purchase_reviewer_id = buyer
        vendor = self.env["res.partner"].create({"name": "NCC tự động QA"})
        route = self.env.ref("purchase_stock.route_warehouse0_buy")
        product = self.env["product.product"].create({
            "name": "Phụ tùng PR QA", "type": "consu", "is_storable": True, "eam_mro": True,
            "route_ids": [Command.link(route.id)],
            "seller_ids": [Command.create({"partner_id": vendor.id, "price": 15})],
        })
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        point = self.env["stock.warehouse.orderpoint"].create({
            "product_id": product.id, "location_id": warehouse.lot_stock_id.id, "route_id": route.id,
            "product_min_qty": 2, "product_max_qty": 5, "trigger": "auto",
        })
        point._procure_orderpoint_confirm(company_id=self.company)
        point._procure_orderpoint_confirm(company_id=self.company)
        requisitions = self.env["ps.eam.purchase.requisition"].search([("orderpoint_id", "=", point.id)])
        self.assertEqual(len(requisitions), 1)
        self.assertEqual(requisitions.quantity, 5)
        self.assertEqual(requisitions.activity_ids.user_id, buyer)
        self.assertFalse(requisitions.purchase_ids)
        with self.assertRaises(AccessError), self.cr.savepoint():
            requisitions.with_user(self.manager).action_approve()
        requisitions.with_user(buyer).action_approve()
        self.assertEqual(requisitions.state, "approved")
        self.assertEqual(requisitions.purchase_ids.order_line.product_qty, 5)
        self.assertEqual(requisitions.purchase_ids.order_line.orderpoint_id, point)
        point._procure_orderpoint_confirm(company_id=self.company)
        self.assertEqual(self.env["ps.eam.purchase.requisition"].search_count([("orderpoint_id", "=", point.id)]), 1)
        with self.assertRaises(UserError), self.cr.savepoint():
            requisitions.with_user(buyer).action_approve()

    def test_maintenance_reschedules_conflicting_workorder(self):
        center = self.env["mrp.workcenter"].create({"name": "Trung tâm lập lịch QA", "company_id": self.company.id})
        self.eq.eam_workcenter_id = center
        product = self.env["product.product"].create({"name": "Thành phẩm lập lịch", "type": "consu"})
        bom = self.env["mrp.bom"].create({
            "product_tmpl_id": product.product_tmpl_id.id,
            "operation_ids": [Command.create({"name": "Chạy máy", "workcenter_id": center.id, "time_cycle_manual": 30})],
        })
        production = self.env["mrp.production"].create({
            "product_id": product.id, "product_qty": 1, "bom_id": bom.id,
            "date_start": fields.Datetime.now() + timedelta(days=2),
        })
        production.button_plan()
        workorder = production.workorder_ids
        self.assertTrue(workorder.leave_id)
        start, end = workorder.date_start, workorder.date_finished
        order = self.order(schedule_date=start, schedule_end=end)
        order.with_user(self.manager).action_approve()
        self.assertGreaterEqual(workorder.date_start, end)

    def setup_eam_accounts(self):
        accounts = self.env["account.account"].create([
            {"name": name, "code": code, "account_type": account_type,
             "company_ids": [Command.set(self.company.ids)]}
            for name, code, account_type in (
                ("Chi phí bảo trì QA", "EAMQA601", "expense"),
                ("Đối ứng giờ công QA", "EAMQA202", "liability_current"),
                ("Hao mòn QA", "EAMQA203", "asset_fixed"),
                ("Dở dang QA", "EAMQA105", "asset_current"),
            )
        ])
        journal = self.env["account.journal"].create({
            "name": "EAM QA", "code": "EAMQA", "type": "general", "company_id": self.company.id,
        })
        self.company.write({
            "eam_journal_id": journal.id, "eam_overhead_account_id": accounts[0].id,
            "eam_labor_clearing_id": accounts[1].id,
        })
        return accounts

    def setup_eam_vendor(self, expense):
        payable = self.env["account.account"].create({
            "name": "Phải trả QA", "code": "EAMQA331", "account_type": "liability_payable", "reconcile": True,
            "company_ids": [Command.set(self.company.ids)],
        })
        self.env["account.journal"].create({
            "name": "Mua dịch vụ QA", "code": "EQPUR", "type": "purchase", "company_id": self.company.id,
            "default_account_id": expense.id,
        })
        return self.env["res.partner"].create({"name": "Dịch vụ QA", "property_account_payable_id": payable.id})

    def test_overhead_is_posted_on_acceptance(self):
        expense, clearing, _, _ = self.setup_eam_accounts()
        order = self.order(eam_accounting_mode="overhead")
        self.ready(order)
        order.with_user(self.manager).action_done()
        entry = order.eam_posted_entry_id
        self.assertEqual(entry.state, "posted")
        self.assertEqual(entry.line_ids.filtered(lambda line: line.account_id == expense).balance, 100)
        self.assertEqual(entry.line_ids.filtered(lambda line: line.account_id == clearing).balance, -100)

    def test_overhead_reclassifies_posted_material_and_service_without_duplicate_expense(self):
        expense, clearing, stock_account, _ = self.setup_eam_accounts()
        source = self.env["account.account"].create({
            "name": "Tiêu hao vật tư QA", "code": "EAMQA602", "account_type": "expense",
            "company_ids": [Command.set(self.company.ids)],
        })
        self.company.account_stock_journal_id = self.company.eam_journal_id
        category = self.env["product.category"].create({
            "name": "Vật tư ghi sổ QA", "property_valuation": "real_time", "property_cost_method": "standard",
            "property_stock_valuation_account_id": stock_account.id,
        })
        product = self.env["product.product"].create({
            "name": "Phụ tùng ghi sổ QA", "type": "consu", "is_storable": True, "standard_price": 25,
            "eam_mro": True, "categ_id": category.id,
        })
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        self.env["stock.location"].create({
            "name": "Tiêu hao có tài khoản QA", "usage": "inventory", "company_id": self.company.id,
            "eam_consumption": True, "valuation_account_id": source.id,
        })
        self.env["stock.quant"]._update_available_quantity(product, warehouse.lot_stock_id, 10)
        vendor = self.setup_eam_vendor(source)
        order = self.order(
            eam_accounting_mode="overhead",
            part_ids=[Command.create({"product_id": product.id, "quantity": 2})],
            cost_ids=[Command.create({"name": "Sửa động cơ", "vendor_id": vendor.id, "amount": 75})],
        )
        self.ready(order)
        order.cost_ids.action_vendor_bill()
        bill = order.cost_ids.bill_id
        bill.invoice_date = fields.Date.today()
        bill.invoice_line_ids.account_id = source
        bill.action_post()
        self.assertEqual(bill.invoice_line_ids.account_id, source)
        self.assertEqual(bill.invoice_line_ids.balance, 75)
        order.with_user(self.manager).action_create_picking()
        picking = order.picking_ids
        picking.action_assign()
        picking.move_ids.write({"quantity": 2, "picked": True})
        picking.button_validate()
        stock_entry = picking.move_ids.account_move_id
        self.assertEqual(stock_entry.state, "posted")
        self.assertEqual(stock_entry.line_ids.filtered(lambda line: line.account_id == source).balance, 50)
        order.with_user(self.manager).action_done()
        entry = order.eam_posted_entry_id
        self.assertEqual(entry.line_ids.filtered(lambda line: line.account_id == source).balance, -125)
        self.assertEqual(entry.line_ids.filtered(lambda line: line.account_id == expense).balance, 225)
        self.assertEqual(entry.line_ids.filtered(lambda line: line.account_id == clearing).balance, -100)

    def test_production_cost_uses_actual_quantity_once(self):
        _, clearing, stock_account, wip = self.setup_eam_accounts()
        self.company.account_stock_journal_id = self.company.eam_journal_id
        category = self.env["product.category"].create({
            "name": "AVCO EAM QA", "property_valuation": "real_time", "property_cost_method": "average",
            "property_stock_valuation_account_id": stock_account.id,
        })
        location = self.env["stock.location"].create({
            "name": "WIP EAM QA", "usage": "production", "company_id": self.company.id,
            "valuation_account_id": wip.id,
        })
        product = self.env["product.product"].create({
            "name": "Thành phẩm chi phí QA", "type": "consu", "is_storable": True, "categ_id": category.id,
            "property_stock_production": location.id,
        })
        production = self.env["mrp.production"].create({"product_id": product.id, "product_qty": 2})
        order = self.order(eam_accounting_mode="production", eam_production_id=production.id)
        self.ready(order)
        order.with_user(self.manager).action_done()
        self.assertEqual(order.eam_capitalized_amount, 100)
        self.assertEqual(order.eam_posted_entry_id.line_ids.filtered(lambda line: line.account_id == wip).balance, 100)
        self.assertEqual(order.eam_posted_entry_id.line_ids.filtered(lambda line: line.account_id == clearing).balance, -100)
        production.action_confirm()
        production.qty_producing = 2
        production._post_inventory()
        finished = production.move_finished_ids
        self.assertEqual(finished.price_unit, 50)
        self.assertEqual(finished.value, 100)
        self.assertTrue(production.eam_cost_applied)
        entry = finished.account_move_id
        self.assertEqual(entry.state, "posted")
        self.assertEqual(entry.line_ids.filtered(lambda line: line.account_id == wip).balance, -100)

    def test_depreciation_posts_each_period_once(self):
        expense, _, accumulated, _ = self.setup_eam_accounts()
        first = fields.Date.today() - timedelta(days=90)
        schedule = self.env["ps.eam.depreciation"].create({
            "name": "Lịch khấu hao QA", "equipment_id": self.eq.id, "acquisition_value": 1000,
            "salvage_value": 100, "opening_depreciation": 50, "months": 3, "first_date": first,
            "expense_account_id": expense.id, "accumulated_account_id": accumulated.id,
        })
        schedule.action_activate()
        schedule._post_due()
        schedule._post_due()
        self.assertEqual(schedule.state, "done")
        self.assertEqual(len(schedule.entry_ids), 3)
        self.assertEqual(set(schedule.entry_ids.mapped("state")), {"posted"})
        self.assertEqual(self.eq.eam_depreciation_total, 900)
        self.assertEqual(self.eq.eam_book_value, 100)
