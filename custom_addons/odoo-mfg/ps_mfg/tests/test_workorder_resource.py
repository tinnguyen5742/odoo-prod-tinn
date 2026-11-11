from odoo.tests import TransactionCase, tagged

from .common import operation_line


@tagged("post_install", "-at_install")
class TestMfgWorkOrderResource(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.finished = cls.env["product.product"].create(
            {
                "name": "WO Resource FG",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.comp_a = cls.env["product.product"].create(
            {
                "name": "WO Resource Comp A",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
                "standard_price": 100.0,
            }
        )
        company = cls.env.company
        location = cls.env["stock.location"].search(
            [("usage", "=", "internal"), ("company_id", "in", (False, company.id))],
            limit=1,
        )
        account = cls.env["account.account"].search(
            [("company_ids", "in", company.id)], limit=1
        ) or cls.env["account.account"].search([], limit=1)
        cls.workcenter = cls.env["ps.mfg.work.center"].create(
            {
                "name": "WC WO Resource Test",
                "code": "WC-WOR-T",
                "company_id": company.id,
                "location_id": location.id,
                "expense_account_id": account.id,
                "wip_account_id": account.id,
                "mo_prefix": "MO/WOR/",
                "comp_request_prefix": "CR/WOR/",
                "receipt_request_prefix": "RC/WOR/",
            }
        )
        cls.cost_item = cls.env["ps.mfg.cost.item"].create(
            {
                "name": "Labor Cost",
                "code": "LABOR_TEST_01",
            }
        )
        cls.account = cls.env["account.account"].search([], limit=1)
        cls.resource_labor = cls.env["ps.mfg.resource"].create(
            {
                "name": "Worker Shift 1",
                "code": "RES_LABOR_TEST_01",
                "cost_item_id": cls.cost_item.id,
                "account_id": cls.account.id,
            }
        )
        cls.resource_machine = cls.env["ps.mfg.resource"].create(
            {
                "name": "CNC Machine",
                "code": "RES_CNC_TEST_01",
                "cost_item_id": cls.cost_item.id,
                "account_id": cls.account.id,
            }
        )

        # BoM with 1 operation having 2 resources
        cls.bom = cls.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": cls.finished.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": cls.uom_unit.id,
                "operation_ids": [
                    operation_line(
                        cls.env,
                        "Cutting & Assembly",
                        10,
                        resources=[
                            (cls.resource_labor, 50000.0),
                            (cls.resource_machine, 30000.0),
                        ],
                    ),
                ],
            }
        )
        op = cls.bom.operation_ids.filtered(lambda o: o.name == "Cutting & Assembly")
        cls.env["ps.mfg.bom.line"].create(
            [
                {
                    "bom_id": cls.bom.id,
                    "product_id": cls.comp_a.id,
                    "quantity": 2.0,
                    "product_uom_id": cls.uom_unit.id,
                    "operation_id": op.id,
                }
            ]
        )

    def test_workorder_resource_clone_and_snapshot(self):
        # Create MO from BoM
        mo = self.env["ps.mfg.production"].create(
            {
                "product_id": self.finished.id,
                "product_qty": 10.0,
                "workcenter_id": self.workcenter.id,
                "bom_id": self.bom.id,
            }
        )
        self.assertEqual(len(mo.workorder_ids), 1)
        wo = mo.workorder_ids[0]

        # Verify resources cloned to WO
        self.assertEqual(len(wo.resource_ids), 2)
        res_labor = wo.resource_ids.filtered(
            lambda r: r.resource_id == self.resource_labor
        )
        res_mach = wo.resource_ids.filtered(
            lambda r: r.resource_id == self.resource_machine
        )
        self.assertTrue(res_labor)
        self.assertTrue(res_mach)
        self.assertEqual(res_labor.planned_cost, 50000.0)
        self.assertEqual(res_labor.actual_cost, 50000.0)
        self.assertEqual(res_mach.planned_cost, 30000.0)
        self.assertEqual(res_mach.actual_cost, 30000.0)

        # Tài nguyên của công đoạn chỉ là định mức: chi phí thực tế tính trên các ca
        self.assertEqual(wo.resource_amount, 0.0)
        self.assertEqual(wo.material_amount, 0.0)
        self.assertEqual(wo.total_amount, 0.0)

        # Snapshot check: changing the shared operation resource cost does NOT
        # alter existing WO resource cost
        op = self.bom.operation_ids[0].operation_id
        routing_res_labor = op.resource_ids.filtered(
            lambda r: r.resource_id == self.resource_labor
        )
        routing_res_labor.resource_cost = 999999.0
        self.assertEqual(res_labor.planned_cost, 50000.0)

    def test_mo_workorder_smart_button(self):
        # 1. MO without BoM (0 WO)
        product_no_bom = self.env["product.product"].create(
            {
                "name": "No BoM Product",
                "type": "consu",
                "uom_id": self.uom_unit.id,
            }
        )
        mo_empty = self.env["ps.mfg.production"].create(
            {
                "product_id": product_no_bom.id,
                "product_qty": 5.0,
                "workcenter_id": self.workcenter.id,
            }
        )
        self.assertEqual(mo_empty.workorder_count, 0)
        action_empty = mo_empty.action_view_workorders()
        self.assertEqual(action_empty["res_model"], "ps.mfg.workorder")
        self.assertEqual(action_empty["view_mode"], "list,form")
        self.assertEqual(action_empty["domain"], [("production_id", "=", mo_empty.id)])

        # 2. MO with 1 WO
        mo_single = self.env["ps.mfg.production"].create(
            {
                "product_id": self.finished.id,
                "product_qty": 10.0,
                "workcenter_id": self.workcenter.id,
                "bom_id": self.bom.id,
            }
        )
        self.assertEqual(mo_single.workorder_count, 1)
        action_single = mo_single.action_view_workorders()
        self.assertEqual(action_single["res_model"], "ps.mfg.workorder")
        self.assertEqual(action_single["view_mode"], "form")
        self.assertEqual(action_single["res_id"], mo_single.workorder_ids[0].id)

        # 3. BoM with multiple operations -> MO with multiple WOs
        self.bom.write(
            {
                "operation_ids": [
                    operation_line(self.env, "Finishing & QA", 20)
                ]
            }
        )
        mo_multi = self.env["ps.mfg.production"].create(
            {
                "product_id": self.finished.id,
                "product_qty": 10.0,
                "workcenter_id": self.workcenter.id,
                "bom_id": self.bom.id,
            }
        )
        self.assertEqual(mo_multi.workorder_count, 2)
        action_multi = mo_multi.action_view_workorders()
        self.assertEqual(action_multi["res_model"], "ps.mfg.workorder")
        self.assertEqual(action_multi["view_mode"], "list,form")
        self.assertEqual(action_multi["domain"], [("production_id", "=", mo_multi.id)])
        self.assertEqual(action_multi["context"]["default_production_id"], mo_multi.id)
