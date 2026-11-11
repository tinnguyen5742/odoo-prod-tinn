from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.service.model import call_kw
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import get_operation


@tagged("post_install", "-at_install")
class TestMfgOperationShared(TransactionCase):
    """A shared operation (công đoạn) is reused by several BoMs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
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
                "name": "WC Shared Op Test",
                "code": "WC-SHOP-T",
                "company_id": company.id,
                "location_id": location.id,
                "expense_account_id": account.id,
                "wip_account_id": account.id,
                "mo_prefix": "MO/SHOP/",
                "comp_request_prefix": "CR/SHOP/",
                "receipt_request_prefix": "RC/SHOP/",
            }
        )
        cost_item = cls.env["ps.mfg.cost.item"].create(
            {"name": "Shared Op Labor", "code": "SHOP_LABOR_T"}
        )
        cls.resource = cls.env["ps.mfg.resource"].create(
            {
                "name": "Shared Op Worker",
                "code": "RES_SHOP_T",
                "cost_item_id": cost_item.id,
                "account_id": account.id,
            }
        )
        cls.operation = get_operation(
            cls.env, "Shared Assembly", resources=[(cls.resource, 70000.0)]
        )
        cls.comp = cls.env["product.product"].create(
            {"name": "Shared Op Comp", "type": "consu", "uom_id": cls.uom_unit.id}
        )
        cls.fg_a, cls.fg_b = cls.env["product.product"].create(
            [
                {"name": "Shared Op FG A", "type": "consu", "uom_id": cls.uom_unit.id},
                {"name": "Shared Op FG B", "type": "consu", "uom_id": cls.uom_unit.id},
            ]
        )
        cls.bom_a = cls._create_bom(cls.fg_a)
        cls.bom_b = cls._create_bom(cls.fg_b)

    @classmethod
    def _create_bom(cls, product):
        bom = cls.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": cls.uom_unit.id,
                "operation_ids": [
                    (0, 0, {"operation_id": cls.operation.id, "sequence": 10})
                ],
            }
        )
        cls.env["ps.mfg.bom.line"].create(
            {
                "bom_id": bom.id,
                "product_id": cls.comp.id,
                "quantity": 1.0,
                "product_uom_id": cls.uom_unit.id,
                "operation_id": bom.operation_ids.id,
            }
        )
        return bom

    def _create_mo(self, product, bom):
        return self.env["ps.mfg.production"].create(
            {
                "product_id": product.id,
                "product_qty": 5.0,
                "workcenter_id": self.workcenter.id,
                "bom_id": bom.id,
            }
        )

    def test_operation_shared_by_boms(self):
        self.assertEqual(self.operation.bom_count, 2)
        for bom in (self.bom_a, self.bom_b):
            self.assertEqual(bom.operation_ids.name, "Shared Assembly")
            self.assertEqual(
                bom.operation_ids.resource_ids, self.operation.resource_ids
            )

    def test_workorders_take_resources_from_shared_operation(self):
        for product, bom in ((self.fg_a, self.bom_a), (self.fg_b, self.bom_b)):
            mo = self._create_mo(product, bom)
            wo = mo.workorder_ids
            self.assertEqual(len(wo), 1)
            self.assertEqual(wo.operation_id, self.operation)
            self.assertEqual(wo.name, "Shared Assembly")
            self.assertEqual(wo.resource_ids.resource_id, self.resource)
            self.assertEqual(wo.resource_ids.planned_cost, 70000.0)
            self.assertEqual(mo.component_ids.workorder_id, wo)

    def test_master_rename_propagates_to_boms(self):
        self.operation.name = "Shared Assembly v2"
        self.assertEqual(self.bom_a.operation_ids.name, "Shared Assembly v2")
        self.assertEqual(self.bom_b.operation_ids.name, "Shared Assembly v2")

    def test_operation_unique_per_bom(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.bom_a.write(
                    {
                        "operation_ids": [
                            (0, 0, {"operation_id": self.operation.id, "sequence": 20})
                        ]
                    }
                )
                self.env.flush_all()

    def test_operation_in_use_cannot_be_deleted(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.operation.unlink()
                self.env.flush_all()

    def test_new_version_keeps_shared_operation(self):
        new_bom = self.bom_a.copy({"version": self.bom_a.version + 1})
        self.assertEqual(new_bom.operation_ids.operation_id, self.operation)
        self.assertEqual(new_bom.bom_line_ids.operation_id, new_bom.operation_ids)
        self.assertEqual(self.operation.bom_count, 3)

    def test_new_operation_gets_free_sequence_code(self):
        operation_model = self.env["ps.mfg.operation"]
        # A code already taken (e.g. created by the migration) is skipped.
        sequence = self.env.ref("ps_mfg.seq_ps_mfg_operation")
        taken = f"OP{sequence.number_next_actual:03d}"
        operation_model.create({"name": "Taken", "code": taken})
        op_a, op_b = operation_model.create([{"name": "Auto A"}, {"name": "Auto B"}])
        for op in (op_a, op_b):
            self.assertTrue(op.code.startswith("OP"))
            self.assertNotEqual(op.code, taken)
        self.assertNotEqual(op_a.code, op_b.code)

    def test_bom_operation_opens_full_page(self):
        routing = self.bom_a.operation_ids
        action = routing.action_open_routing()
        self.assertEqual(action["res_model"], "ps.mfg.routing")
        self.assertEqual(action["res_id"], routing.id)
        self.assertEqual(action["target"], "current")
        action = routing.action_open_operation()
        self.assertEqual(action["res_model"], "ps.mfg.operation")
        self.assertEqual(action["res_id"], self.operation.id)
        self.assertEqual(action["target"], "current")

    def test_bom_operation_lists_its_components(self):
        routing = self.bom_a.operation_ids
        self.assertEqual(routing.bom_line_ids, self.bom_a.bom_line_ids)
        self.assertEqual(routing.bom_line_ids.product_id, self.comp)

    def test_add_operation_from_bom_links_routing(self):
        action = (
            self.env["ps.mfg.routing"]
            .with_context(ps_mfg_bom_id=self.bom_a.id)
            .action_open_operation_form()
        )
        self.assertEqual(action["res_model"], "ps.mfg.operation")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["context"]["ps_mfg_link_bom_id"], self.bom_a.id)

        new_op = (
            self.env["ps.mfg.operation"]
            .with_context(**action["context"])
            .create({"name": "Painting From BoM"})
        )
        routing = self.bom_a.operation_ids.filtered(lambda r: r.operation_id == new_op)
        self.assertEqual(len(routing), 1)
        self.assertEqual(routing.sequence, 11)
        self.assertFalse(
            self.bom_b.operation_ids.filtered(lambda r: r.operation_id == new_op)
        )

    def test_create_operation_without_bom_context_has_no_routing(self):
        new_op = self.env["ps.mfg.operation"].create({"name": "Standalone Op"})
        self.assertFalse(new_op.routing_ids)

    def test_add_operation_requires_saved_bom(self):
        with self.assertRaises(UserError):
            self.env["ps.mfg.routing"].action_open_operation_form()

    def test_add_operation_button_rpc(self):
        """The control button reaches the method through call_button with empty ids."""
        action = call_kw(
            self.env["ps.mfg.routing"],
            "action_open_operation_form",
            [[]],
            {"context": {"ps_mfg_bom_id": self.bom_a.id}},
        )
        self.assertEqual(action["res_model"], "ps.mfg.operation")
