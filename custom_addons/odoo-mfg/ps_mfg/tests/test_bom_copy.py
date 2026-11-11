from odoo.tests import TransactionCase, tagged

from .common import operation_line


@tagged("post_install", "-at_install")
class TestMfgBomCopy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.finished = cls.env["product.product"].create(
            {
                "name": "Copy Finished",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.comp_a = cls.env["product.product"].create(
            {
                "name": "Copy Component A",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.comp_b = cls.env["product.product"].create(
            {
                "name": "Copy Component B",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )

    def _make_bom(self):
        # Operations created out of sequence order so id order differs from
        # (sequence, id) order — the old remap paired them wrongly.
        bom = self.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": self.finished.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": self.uom_unit.id,
                "operation_ids": [
                    operation_line(self.env, "Op B", 2),
                    operation_line(self.env, "Op A", 1),
                ],
            }
        )
        op_a = bom.operation_ids.filtered(lambda o: o.name == "Op A")
        op_b = bom.operation_ids.filtered(lambda o: o.name == "Op B")
        self.env["ps.mfg.bom.line"].create(
            [
                {
                    "bom_id": bom.id,
                    "product_id": self.comp_a.id,
                    "quantity": 1.0,
                    "product_uom_id": self.uom_unit.id,
                    "operation_id": op_a.id,
                },
                {
                    "bom_id": bom.id,
                    "product_id": self.comp_b.id,
                    "quantity": 2.0,
                    "product_uom_id": self.uom_unit.id,
                    "operation_id": op_b.id,
                },
            ]
        )
        return bom

    def test_new_version_keeps_lines_remapped_to_new_operations(self):
        bom = self._make_bom()
        action = bom.action_new_version()
        new_bom = self.env["ps.mfg.bom"].browse(action["res_id"])
        self.assertEqual(new_bom.version, bom.version + 1)
        self.assertEqual(len(new_bom.operation_ids), 2)
        self.assertEqual(len(new_bom.bom_line_ids), 2)
        # Every copied line must point at an operation of the NEW BoM...
        for line in new_bom.bom_line_ids:
            self.assertEqual(line.operation_id.bom_id, new_bom)
        # ...and stay on the same operation by name, with data preserved.
        by_product = {line.product_id.id: line for line in new_bom.bom_line_ids}
        self.assertEqual(by_product[self.comp_a.id].operation_id.name, "Op A")
        self.assertEqual(by_product[self.comp_a.id].quantity, 1.0)
        self.assertEqual(by_product[self.comp_b.id].operation_id.name, "Op B")
        self.assertEqual(by_product[self.comp_b.id].quantity, 2.0)

    def test_copy_bom_without_lines(self):
        bom = self.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": self.finished.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": self.uom_unit.id,
                "operation_ids": [operation_line(self.env, "Op 1", 1)],
            }
        )
        new_bom = bom.copy({"version": bom.version + 1})
        self.assertEqual(len(new_bom.operation_ids), 1)
        self.assertEqual(len(new_bom.bom_line_ids), 0)
