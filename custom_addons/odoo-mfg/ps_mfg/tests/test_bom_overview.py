from odoo.tests import TransactionCase, tagged

from .common import operation_line


@tagged("post_install", "-at_install")
class TestMfgBomOverview(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.finished = cls.env["product.product"].create(
            {
                "name": "Overview Finished",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.comp_a = cls.env["product.product"].create(
            {
                "name": "Overview Component A",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.comp_b = cls.env["product.product"].create(
            {
                "name": "Overview Component B",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )

    def _make_bom(self, product, lines):
        bom = self.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": self.uom_unit.id,
                "operation_ids": [
                    operation_line(self.env, "Op 1", 1),
                    operation_line(self.env, "Op 2", 2),
                ],
            }
        )
        for product_id, qty, op_index in lines:
            self.env["ps.mfg.bom.line"].create(
                {
                    "bom_id": bom.id,
                    "product_id": product_id,
                    "quantity": qty,
                    "product_uom_id": self.uom_unit.id,
                    "operation_id": bom.operation_ids[op_index].id,
                }
            )
        return bom

    def test_overview_groups_by_operation_with_codes_and_versions(self):
        bom = self._make_bom(
            self.finished,
            [
                (self.comp_a.id, 1.0, 0),
                (self.comp_b.id, 1.0, 1),
            ],
        )
        sub = self.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": self.comp_a.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": self.uom_unit.id,
                "operation_ids": [operation_line(self.env, "Sub Op", 1)],
            }
        )
        self.env["ps.mfg.bom.line"].create(
            {
                "bom_id": sub.id,
                "product_id": self.comp_b.id,
                "quantity": 2.0,
                "product_uom_id": self.uom_unit.id,
                "operation_id": sub.operation_ids[0].id,
            }
        )

        res = self.env["report.ps.mfg.bom_structure"].get_html(
            bom_id=bom.id, searchQty=3
        )
        root = res["lines"]
        self.assertEqual(root["bom_version"], 1)
        self.assertEqual(root["quantity"], 3)
        self.assertEqual([o.get("line_code") for o in root["operations"]], ["1", "2"])
        op1, op2 = root["operations"]
        self.assertEqual(len(op1["ps_components"]), 1)
        comp_node = op1["ps_components"][0]
        self.assertEqual(comp_node["line_code"], "1.1")
        self.assertEqual(comp_node["quantity"], 3.0)
        self.assertEqual(comp_node["type"], "bom")
        self.assertEqual(comp_node["bom_version"], sub.version)
        # Nested sub-BoMs list components flat: no operations section,
        # no line codes, badges kept.
        self.assertEqual(comp_node["operations"], [])
        nested = comp_node["ps_unassigned_components"]
        self.assertEqual(len(nested), 1)
        self.assertEqual(nested[0]["type"], "component")
        self.assertEqual(nested[0]["bom_version"], 0)
        self.assertFalse(nested[0].get("line_code"))
        self.assertEqual(nested[0]["quantity"], 6.0)
        leaf = op2["ps_components"][0]
        self.assertEqual(leaf["type"], "component")
        self.assertEqual(leaf["bom_version"], 0)
        self.assertEqual(leaf.get("line_code"), "2.1")
        self.assertEqual(leaf["quantity"], 3.0)

    def test_overview_json_safe(self):
        import json

        bom = self._make_bom(self.finished, [(self.comp_a.id, 1.0, 0)])
        res = self.env["report.ps.mfg.bom_structure"].get_html(bom_id=bom.id)
        json.dumps(res)
