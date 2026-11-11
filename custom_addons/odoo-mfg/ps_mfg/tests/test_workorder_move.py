from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import Form, TransactionCase, tagged

from .common import (
    create_received_component_request,
    get_component_source_location,
    operation_line,
)


@tagged("post_install", "-at_install")
class TestMfgWorkOrderMove(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.finished = cls.env["product.product"].create(
            {
                "name": "Move Finished",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.comp_a = cls.env["product.product"].create(
            {
                "name": "Move Component A",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
                "standard_price": 10.0,
            }
        )
        cls.comp_b = cls.env["product.product"].create(
            {
                "name": "Move Component B",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
                "standard_price": 5.0,
            }
        )
        cls.workcenter = cls.env["ps.mfg.work.center"].create(
            {
                "name": "WC Move Test",
                "code": "WC-MOVE-T",
                "location_id": cls.env["stock.location"]
                .search(
                    [
                        ("usage", "=", "internal"),
                        ("company_id", "in", (False, cls.env.company.id)),
                    ],
                    limit=1,
                )
                .id,
                "expense_account_id": cls.env["account.account"].search([], limit=1).id,
                "wip_account_id": cls.env["account.account"].search([], limit=1).id,
                "mo_prefix": "MO/T/",
                "comp_request_prefix": "CR/T/",
                "receipt_request_prefix": "RC/T/",
            }
        )
        # BoM: 1 finished = 1 x A (Op 1) + 2 x B (Op 1); Op 2 cho công đoạn sau.
        cls.bom = cls.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": cls.finished.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": cls.uom_unit.id,
                "operation_ids": [
                    operation_line(cls.env, "Op 1", 1),
                    operation_line(cls.env, "Op 2", 2),
                ],
            }
        )
        op1 = cls.bom.operation_ids.filtered(lambda o: o.name == "Op 1")
        op2 = cls.bom.operation_ids.filtered(lambda o: o.name == "Op 2")
        cls.env["ps.mfg.bom.line"].create(
            [
                {
                    "bom_id": cls.bom.id,
                    "product_id": cls.comp_a.id,
                    "quantity": 1.0,
                    "product_uom_id": cls.uom_unit.id,
                    "operation_id": op1.id,
                },
                {
                    "bom_id": cls.bom.id,
                    "product_id": cls.comp_b.id,
                    "quantity": 2.0,
                    "product_uom_id": cls.uom_unit.id,
                    "operation_id": op1.id,
                },
                {
                    "bom_id": cls.bom.id,
                    "product_id": cls.comp_a.id,
                    "quantity": 0.5,
                    "product_uom_id": cls.uom_unit.id,
                    "operation_id": op2.id,
                },
            ]
        )
        cls.production = cls.env["ps.mfg.production"].create(
            {
                "bom_id": cls.bom.id,
                "product_id": cls.finished.id,
                "product_qty": 100.0,
                "workcenter_id": cls.workcenter.id,
            }
        )
        cls.source_location = get_component_source_location(
            cls.env, cls.workcenter.location_id
        )
        cls.cmp_request = create_received_component_request(
            cls.env, cls.production, 100.0, cls.source_location
        )
        cls.wo1 = cls.production.workorder_ids.sorted("sequence")[0]
        cls.wo2 = cls.production.workorder_ids.sorted("sequence")[1]

    def _line_by_product(self, move, product):
        return move.workorder_component_line_ids.filtered(
            lambda l: l.component_id == product
        )

    def test_planned_qty_scaled_to_move_qty(self):
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        line_a = self._line_by_product(move, self.comp_a)
        line_b = self._line_by_product(move, self.comp_b)
        # BoM cho 50 sp: 50 x A + 100 x B (không phải cho full 100).
        self.assertEqual(line_a.planned_qty, 50.0)
        self.assertEqual(line_b.planned_qty, 100.0)
        # actual_qty default = planned_qty.
        self.assertEqual(line_a.actual_qty, 50.0)
        self.assertEqual(line_b.actual_qty, 100.0)
        self.assertEqual(move.amount_total, 50.0 * 10.0 + 100.0 * 5.0)

    def test_default_full_qty_from_component_request(self):
        # Không nhập move_qty → mặc định lấy toàn bộ SL hiện có (YCCP 100).
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
            }
        )
        self.assertEqual(self._line_by_product(move, self.comp_a).planned_qty, 100.0)
        self.assertEqual(self._line_by_product(move, self.comp_b).planned_qty, 200.0)

    def test_upstream_move_planned_from_upstream_qty(self):
        upstream = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        upstream.action_approve()
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "from_workorder_id": self.wo1.id,
                "to_workorder_id": self.wo2.id,
                "move_qty": 50.0,
            }
        )
        # CĐ sau scale theo 50 sp từ CĐ trước: 0.5 x A trên 50 sp = 25.
        self.assertEqual(self._line_by_product(move, self.comp_a).planned_qty, 25.0)

    def test_write_move_qty_rescales_lines(self):
        upstream = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        upstream.action_approve()
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "from_workorder_id": self.wo1.id,
                "to_workorder_id": self.wo2.id,
                "move_qty": 50.0,
            }
        )
        self.assertEqual(self._line_by_product(move, self.comp_a).planned_qty, 25.0)
        move.write({"move_qty": 25.0})
        # Rescale theo 25 sp, actual_qty reset về planned mới.
        self.assertEqual(self._line_by_product(move, self.comp_a).planned_qty, 12.5)
        self.assertEqual(self._line_by_product(move, self.comp_a).actual_qty, 12.5)

    def test_move_qty_exceeds_remaining_raises(self):
        self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        ).action_approve()
        with self.assertRaises(ValidationError):
            self.env["ps.mfg.workorder.move"].create(
                {
                    "production_id": self.production.id,
                    "to_workorder_id": self.wo1.id,
                    "shift": 2,
                    "move_qty": 60.0,  # remaining chỉ còn 50
                }
            )

    def test_approved_move_locked(self):
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        move.action_approve()
        with self.assertRaises(ValidationError):
            move.write({"move_qty": 40.0})
        with self.assertRaises(ValidationError):
            move.workorder_component_line_ids[0].write({"actual_qty": 999.0})
        with self.assertRaises(ValidationError):
            move.unlink()

    def test_line_location_is_workcenter_not_proposal_source(self):
        nvl_loc = self.env["stock.location"].create(
            {
                "name": "NVL Storage",
                "usage": "internal",
                "location_id": self.workcenter.location_id.location_id.id
                or self.workcenter.location_id.id,
            }
        )
        self.env["ps.mfg.proposal"].create(
            {
                "name": "Proposal Approved",
                "component_request_ids": [(6, 0, [self.cmp_request.id])],
                "source_location_id": nvl_loc.id,
                "state": "approved",
            }
        )
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        workshop = self.workcenter.location_id
        self.assertEqual(self._line_by_product(move, self.comp_a).location_id, workshop)
        self.assertEqual(self._line_by_product(move, self.comp_b).location_id, workshop)
        move.write(
            {
                "extra_component_line_ids": [
                    (
                        0,
                        0,
                        {
                            "component_id": self.comp_a.id,
                            "actual_qty": 1.0,
                            "uom_id": self.uom_unit.id,
                        },
                    )
                ],
            }
        )
        self.assertEqual(move.extra_component_line_ids.location_id, workshop)
        self.assertNotEqual(workshop, nvl_loc)

    def _stock_qty(self, product, location, lot=None):
        return self.env["stock.quant"]._get_available_quantity(
            product, location, lot_id=lot, strict=bool(lot)
        )

    def _set_stock(self, product, location, qty, lot=None):
        self.env["stock.quant"]._update_available_quantity(
            product, location, qty, lot_id=lot
        )

    def _make_lot(self, product, name):
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": product.id,
                "company_id": self.env.company.id,
            }
        )

    def _enable_tracking(self, product, tracking):
        product.product_tmpl_id.write(
            {
                "is_storable": True,
                "tracking": tracking,
            }
        )

    def test_approve_consumes_without_picking(self):
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        production_loc = move._get_production_location()
        move.action_approve()
        # Xuất tiêu hao: stock.move xưởng → Production, không có phiếu internal
        self.assertFalse(move.picking_ids)
        consumed = move.consumption_move_ids
        self.assertEqual(len(consumed), 2)
        self.assertFalse(consumed.picking_id)
        self.assertTrue(all(sm.state == "done" for sm in consumed))
        self.assertEqual(consumed.location_id, self.workcenter.location_id)
        self.assertEqual(consumed.location_dest_id, production_loc)
        self.assertEqual(production_loc.usage, "production")
        qty_by_product = {sm.product_id: sm.product_uom_qty for sm in consumed}
        self.assertEqual(qty_by_product[self.comp_a], 50.0)
        self.assertEqual(qty_by_product[self.comp_b], 100.0)
        # Không có phiếu: tham chiếu là mã ca để nhận ra trong Lịch sử dịch chuyển
        shift_ref = move._consumption_origin()
        self.assertTrue(shift_ref)
        self.assertEqual(consumed.mapped("reference"), [shift_ref] * 2)
        self.assertEqual(set(consumed.move_line_ids.mapped("reference")), {shift_ref})
        # Gọi lại không tạo thêm move
        move._create_and_done_consumption_moves()
        self.assertEqual(move.consumption_move_ids, consumed)
        # Smart button Stock Moves: view stock.move chuẩn, lọc theo ca
        action = move.action_view_stock_moves()
        self.assertEqual(action["res_model"], "stock.move.line")
        self.assertEqual(
            action["domain"], [("move_id.ps_workorder_move_id", "=", move.id)]
        )
        self.assertEqual(
            action["views"][0][0], self.env.ref("stock.view_move_line_tree").id
        )
        self.assertEqual(
            self.env["stock.move.line"].search(action["domain"]),
            consumed.move_line_ids,
        )
        # Tên ca = tham chiếu; bấm dòng trong Lịch sử dịch chuyển mở về ca
        self.assertEqual(move.display_name, shift_ref)
        for record in (consumed[0], consumed[0].move_line_ids[:1]):
            ref_action = record.action_open_reference()
            self.assertEqual(ref_action["res_model"], "ps.mfg.workorder.move")
            self.assertEqual(ref_action["res_id"], move.id)

    def test_approve_consumption_value_matches_line_amount(self):
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        move.action_approve()
        currency = move.currency_id
        value_by_product = {sm.product_id: sm.value for sm in move.consumption_move_ids}
        for line in move.workorder_component_line_ids:
            self.assertAlmostEqual(
                currency.round(line.amount),
                currency.round(value_by_product[line.component_id]),
                places=2,
            )
        self.assertAlmostEqual(
            currency.round(move.amount_total),
            currency.round(sum(value_by_product.values())),
            places=2,
        )

    def test_approve_storable_decreases_workshop_quant(self):
        self.comp_a.is_storable = True
        self.comp_b.is_storable = True
        workshop = self.workcenter.location_id
        self._set_stock(self.comp_a, workshop, 80.0)
        self._set_stock(self.comp_b, workshop, 200.0)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        move.action_approve()
        self.assertEqual(self._stock_qty(self.comp_a, workshop), 30.0)
        self.assertEqual(self._stock_qty(self.comp_b, workshop), 100.0)

    def test_approve_storable_insufficient_stock_raises(self):
        self.comp_a.is_storable = True
        workshop = self.workcenter.location_id
        self._set_stock(self.comp_a, workshop, 1.0)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        with self.assertRaises(UserError):
            move.action_approve()
        self.assertEqual(move.state, "draft")
        self.assertFalse(move.consumption_move_ids)

    def test_shift_defaults_only_on_new_record(self):
        first = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 10.0,
            }
        )
        self.assertEqual(first.shift, 1)

        new_rec = self.env["ps.mfg.workorder.move"].new(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
            }
        )
        new_rec._onchange_default_move_qty()
        self.assertEqual(new_rec.shift, 2)

        existing = self.env["ps.mfg.workorder.move"].new(
            {
                "production_id": first.production_id.id,
                "to_workorder_id": first.to_workorder_id.id,
                "shift": first.shift,
                "move_qty": first.move_qty,
            },
            origin=first,
        )
        existing._onchange_default_move_qty()
        self.assertEqual(existing.shift, 1)
        first.write({"move_qty": 20.0})
        self.assertEqual(first.shift, 1)

    def test_approve_lot_writes_move_line_and_decreases_quant(self):
        self._enable_tracking(self.comp_a, "lot")
        self._enable_tracking(self.comp_b, "lot")
        workshop = self.workcenter.location_id
        lot_a = self._make_lot(self.comp_a, "LOT-A-1")
        lot_b = self._make_lot(self.comp_b, "LOT-B-1")
        self._set_stock(self.comp_a, workshop, 80.0, lot_a)
        self._set_stock(self.comp_b, workshop, 200.0, lot_b)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        line_a = self._line_by_product(move, self.comp_a)
        line_b = self._line_by_product(move, self.comp_b)
        self.assertEqual(len(line_a.lot_line_ids), 1)
        self.assertEqual(line_a.lot_line_ids.qty, 50.0)
        line_a.lot_line_ids.lot_id = lot_a
        line_b.lot_line_ids.lot_id = lot_b
        move.action_approve()
        consumed = move.consumption_move_ids
        sml_a = consumed.move_line_ids.filtered(lambda ml: ml.product_id == self.comp_a)
        sml_b = consumed.move_line_ids.filtered(lambda ml: ml.product_id == self.comp_b)
        self.assertEqual(sml_a.lot_id, lot_a)
        self.assertEqual(sml_a.quantity, 50.0)
        self.assertEqual(sml_b.lot_id, lot_b)
        self.assertEqual(sml_b.quantity, 100.0)
        self.assertEqual(
            self.env["stock.quant"]._get_available_quantity(
                self.comp_a, workshop, lot_id=lot_a, strict=True
            ),
            30.0,
        )
        self.assertEqual(
            self.env["stock.quant"]._get_available_quantity(
                self.comp_b, workshop, lot_id=lot_b, strict=True
            ),
            100.0,
        )
        self.assertEqual(self.wo1.consumed_lot_ids, lot_a | lot_b)
        currency = move.currency_id
        value_by_product = {sm.product_id: sm.value for sm in consumed}
        for line in move.workorder_component_line_ids:
            self.assertAlmostEqual(
                currency.round(line.amount),
                currency.round(value_by_product[line.component_id]),
                places=2,
            )

    def test_approve_tracked_missing_lot_raises(self):
        self._enable_tracking(self.comp_a, "lot")
        workshop = self.workcenter.location_id
        lot_a = self._make_lot(self.comp_a, "LOT-A-MISS")
        self._set_stock(self.comp_a, workshop, 80.0, lot_a)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        with self.assertRaises(UserError):
            move.action_approve()
        self.assertEqual(move.state, "draft")
        self.assertFalse(move.consumption_move_ids)

    def test_approve_lot_insufficient_qty_raises(self):
        self._enable_tracking(self.comp_a, "lot")
        workshop = self.workcenter.location_id
        lot_short = self._make_lot(self.comp_a, "LOT-A-SHORT")
        lot_other = self._make_lot(self.comp_a, "LOT-A-OTHER")
        self._set_stock(self.comp_a, workshop, 10.0, lot_short)
        self._set_stock(self.comp_a, workshop, 80.0, lot_other)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        line_a = self._line_by_product(move, self.comp_a)
        line_a.lot_line_ids.lot_id = lot_short
        with self.assertRaises(UserError):
            move.action_approve()
        self.assertEqual(move.state, "draft")
        self.assertFalse(move.consumption_move_ids)

    def test_approve_splits_two_lots(self):
        self._enable_tracking(self.comp_a, "lot")
        workshop = self.workcenter.location_id
        lot1 = self._make_lot(self.comp_a, "LOT-A-SPLIT-1")
        lot2 = self._make_lot(self.comp_a, "LOT-A-SPLIT-2")
        self._set_stock(self.comp_a, workshop, 30.0, lot1)
        self._set_stock(self.comp_a, workshop, 40.0, lot2)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        line_a = self._line_by_product(move, self.comp_a)
        line_a.lot_line_ids = [
            (5, 0, 0),
            (0, 0, {"lot_id": lot1.id, "qty": 30.0}),
            (0, 0, {"lot_id": lot2.id, "qty": 20.0}),
        ]
        move.action_approve()
        sml = move.consumption_move_ids.move_line_ids.filtered(
            lambda ml: ml.product_id == self.comp_a
        )
        qty_by_lot = {ml.lot_id: ml.quantity for ml in sml}
        self.assertEqual(qty_by_lot[lot1], 30.0)
        self.assertEqual(qty_by_lot[lot2], 20.0)
        self.assertEqual(
            self.env["stock.quant"]._get_available_quantity(
                self.comp_a, workshop, lot_id=lot1, strict=True
            ),
            0.0,
        )
        self.assertEqual(
            self.env["stock.quant"]._get_available_quantity(
                self.comp_a, workshop, lot_id=lot2, strict=True
            ),
            20.0,
        )

    def test_serial_consume_and_duplicate_raises(self):
        self._enable_tracking(self.comp_a, "serial")
        workshop = self.workcenter.location_id
        sn1 = self._make_lot(self.comp_a, "SN-A-1")
        sn2 = self._make_lot(self.comp_a, "SN-A-2")
        self._set_stock(self.comp_a, workshop, 1.0, sn1)
        self._set_stock(self.comp_a, workshop, 1.0, sn2)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 2.0,
            }
        )
        line_a = self._line_by_product(move, self.comp_a)
        self.assertFalse(line_a.lot_line_ids)
        line_a.actual_qty = 2.0
        line_a.lot_line_ids = [
            (0, 0, {"lot_id": sn1.id, "qty": 1.0}),
            (0, 0, {"lot_id": sn2.id, "qty": 1.0}),
        ]
        move.action_approve()
        sml = move.consumption_move_ids.move_line_ids.filtered(
            lambda ml: ml.product_id == self.comp_a
        )
        self.assertEqual(set(sml.lot_id.ids), {sn1.id, sn2.id})
        self.assertTrue(all(ml.quantity == 1.0 for ml in sml))

        move2 = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "shift": 2,
                "move_qty": 1.0,
            }
        )
        line2 = self._line_by_product(move2, self.comp_a)
        line2.actual_qty = 1.0
        with self.assertRaises(ValidationError):
            line2.lot_line_ids = [
                (0, 0, {"lot_id": sn1.id, "qty": 1.0}),
                (0, 0, {"lot_id": sn1.id, "qty": 1.0}),
            ]

    def test_extra_line_lot_consume(self):
        extra = self.env["product.product"].create(
            {
                "name": "Move Extra Lot",
                "type": "consu",
                "uom_id": self.uom_unit.id,
                "standard_price": 3.0,
            }
        )
        self._enable_tracking(extra, "lot")
        workshop = self.workcenter.location_id
        lot = self._make_lot(extra, "LOT-EXTRA-1")
        self._set_stock(extra, workshop, 5.0, lot)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        move.write(
            {
                "extra_component_line_ids": [
                    (
                        0,
                        0,
                        {
                            "component_id": extra.id,
                            "actual_qty": 2.0,
                            "uom_id": self.uom_unit.id,
                        },
                    )
                ],
            }
        )
        extra_line = move.extra_component_line_ids
        self.assertEqual(len(extra_line.lot_line_ids), 1)
        extra_line.lot_line_ids.lot_id = lot
        extra_line.lot_line_ids.qty = 2.0
        move.action_approve()
        sml = move.consumption_move_ids.move_line_ids.filtered(
            lambda ml: ml.product_id == extra
        )
        self.assertEqual(sml.lot_id, lot)
        self.assertEqual(sml.quantity, 2.0)
        self.assertEqual(
            self.env["stock.quant"]._get_available_quantity(
                extra, workshop, lot_id=lot, strict=True
            ),
            3.0,
        )

    def test_lot_ids_inverse_writes_lot_lines(self):
        self._enable_tracking(self.comp_a, "lot")
        workshop = self.workcenter.location_id
        lot_a = self._make_lot(self.comp_a, "LOT-A-TAGS")
        self._set_stock(self.comp_a, workshop, 80.0, lot_a)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        line_a = self._line_by_product(move, self.comp_a)
        line_a.lot_ids = lot_a
        self.assertEqual(line_a.lot_line_ids.lot_id, lot_a)
        self.assertEqual(line_a.lot_line_ids.qty, 50.0)
        action = line_a.action_show_lot_details()
        self.assertEqual(action["res_model"], "ps.mfg.workorder.move.line")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["res_id"], line_a.id)
        self.assertEqual(
            action["view_id"],
            self.env.ref("ps_mfg.ps_mfg_workorder_move_line_lot_form").id,
        )
        move.action_approve()
        sml_a = move.consumption_move_ids.move_line_ids.filtered(
            lambda ml: ml.product_id == self.comp_a
        )
        self.assertEqual(sml_a.lot_id, lot_a)
        self.assertEqual(sml_a.quantity, 50.0)

    def test_serial_lot_ids_sets_actual_qty(self):
        self._enable_tracking(self.comp_a, "serial")
        workshop = self.workcenter.location_id
        sn1 = self._make_lot(self.comp_a, "SN-A-TAGS-1")
        sn2 = self._make_lot(self.comp_a, "SN-A-TAGS-2")
        self._set_stock(self.comp_a, workshop, 1.0, sn1)
        self._set_stock(self.comp_a, workshop, 1.0, sn2)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 2.0,
            }
        )
        line_a = self._line_by_product(move, self.comp_a)
        line_a.lot_ids = sn1 | sn2
        self.assertEqual(line_a.actual_qty, 2.0)
        self.assertEqual(set(line_a.lot_line_ids.lot_id.ids), {sn1.id, sn2.id})
        self.assertTrue(all(ll.qty == 1.0 for ll in line_a.lot_line_ids))
        move.action_approve()
        sml = move.consumption_move_ids.move_line_ids.filtered(
            lambda ml: ml.product_id == self.comp_a
        )
        self.assertEqual(set(sml.lot_id.ids), {sn1.id, sn2.id})

    def test_extra_line_lot_ids_inverse(self):
        extra = self.env["product.product"].create(
            {
                "name": "Move Extra Lot Tags",
                "type": "consu",
                "uom_id": self.uom_unit.id,
                "standard_price": 3.0,
            }
        )
        self._enable_tracking(extra, "lot")
        workshop = self.workcenter.location_id
        lot = self._make_lot(extra, "LOT-EXTRA-TAGS")
        self._set_stock(extra, workshop, 5.0, lot)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        move.write(
            {
                "extra_component_line_ids": [
                    (
                        0,
                        0,
                        {
                            "component_id": extra.id,
                            "actual_qty": 2.0,
                            "uom_id": self.uom_unit.id,
                        },
                    )
                ],
            }
        )
        extra_line = move.extra_component_line_ids
        extra_line.lot_ids = lot
        self.assertEqual(extra_line.lot_line_ids.lot_id, lot)
        self.assertEqual(extra_line.lot_line_ids.qty, 2.0)
        action = extra_line.action_show_lot_details()
        self.assertEqual(action["res_model"], "ps.mfg.workorder.move.extra.line")
        self.assertEqual(
            action["view_id"],
            self.env.ref("ps_mfg.ps_mfg_workorder_move_extra_line_lot_form").id,
        )

    def test_form_has_inline_lots_no_tab(self):
        arch = self.env.ref("ps_mfg.ps_mfg_workorder_move_view_form").arch
        self.assertNotIn('<page string="Lot / Serial"', arch)
        self.assertIn("action_show_lot_details", arch)
        self.assertIn('name="lot_ids" widget="many2many_tags"', arch)
        self.assertNotIn('lot_ids" widget="many2many_tags" readonly="1"', arch)
        self.assertGreaterEqual(arch.count('name="allowed_lot_ids"'), 2)

    def test_allowed_lot_ids_only_workshop_stock(self):
        self._enable_tracking(self.comp_a, "lot")
        self._enable_tracking(self.comp_b, "serial")
        workshop = self.workcenter.location_id
        other_loc = self.env["stock.location"].create(
            {
                "name": "Other Internal",
                "usage": "internal",
                "location_id": workshop.location_id.id or workshop.id,
            }
        )
        lot_here = self._make_lot(self.comp_a, "LOT-WS-HERE")
        lot_other = self._make_lot(self.comp_a, "LOT-WS-OTHER")
        lot_empty = self._make_lot(self.comp_a, "LOT-WS-EMPTY")
        sn_here = self._make_lot(self.comp_b, "SN-WS-HERE")
        sn_other = self._make_lot(self.comp_b, "SN-WS-OTHER")
        self._set_stock(self.comp_a, workshop, 80.0, lot_here)
        self._set_stock(self.comp_a, other_loc, 80.0, lot_other)
        self._set_stock(self.comp_a, workshop, 1.0, lot_empty)
        self._set_stock(self.comp_a, workshop, -1.0, lot_empty)
        self._set_stock(self.comp_b, workshop, 1.0, sn_here)
        self._set_stock(self.comp_b, other_loc, 1.0, sn_other)

        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        line_a = self._line_by_product(move, self.comp_a)
        line_b = self._line_by_product(move, self.comp_b)
        self.assertEqual(line_a.allowed_lot_ids, lot_here)
        self.assertEqual(line_b.allowed_lot_ids, sn_here)
        self.assertEqual(line_a.lot_line_ids.allowed_lot_ids, lot_here)

        extra = self.env["product.product"].create(
            {
                "name": "Move Extra Allowed Lots",
                "type": "consu",
                "uom_id": self.uom_unit.id,
                "standard_price": 3.0,
            }
        )
        self._enable_tracking(extra, "lot")
        extra_here = self._make_lot(extra, "LOT-EXTRA-HERE")
        extra_other = self._make_lot(extra, "LOT-EXTRA-OTHER")
        self._set_stock(extra, workshop, 5.0, extra_here)
        self._set_stock(extra, other_loc, 5.0, extra_other)
        move.write(
            {
                "extra_component_line_ids": [
                    (
                        0,
                        0,
                        {
                            "component_id": extra.id,
                            "actual_qty": 2.0,
                            "uom_id": self.uom_unit.id,
                        },
                    )
                ],
            }
        )
        extra_line = move.extra_component_line_ids
        self.assertEqual(extra_line.allowed_lot_ids, extra_here)
        self.assertEqual(extra_line.lot_line_ids.allowed_lot_ids, extra_here)

    # ------------------------------------------------------------------
    # Costing: NVL + extra + tài nguyên của ca, cộng dồn giá công đoạn trước
    # ------------------------------------------------------------------
    def _make_resource(self, code):
        cost_item = self.env["ps.mfg.cost.item"].create(
            {"name": f"Cost {code}", "code": f"CI-{code}"}
        )
        return self.env["ps.mfg.resource"].create(
            {
                "code": code,
                "name": f"Resource {code}",
                "account_id": self.env["account.account"].search([], limit=1).id,
                "cost_item_id": cost_item.id,
            }
        )

    def _approved_shift(self, to_wo, qty, from_wo=False, resource_cost=None):
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "from_workorder_id": from_wo and from_wo.id,
                "to_workorder_id": to_wo.id,
                "move_qty": qty,
            }
        )
        if resource_cost is not None:
            move.resource_line_ids.actual_cost = resource_cost
        move.action_approve()
        return move

    def test_resource_lines_default_from_workorder(self):
        resource = self._make_resource("RES-WO1")
        self.wo1.resource_ids = [
            Command.create(
                {"resource_id": resource.id, "planned_cost": 4.0, "actual_cost": 0.0}
            )
        ]
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        line = move.resource_line_ids
        self.assertEqual(line.resource_id, resource)
        # BoM qty = 1 -> đơn giá 4; 50 sp -> 200
        self.assertEqual(line.unit_cost, 4.0)
        self.assertEqual(line.planned_cost, 200.0)
        self.assertEqual(line.actual_cost, 200.0)
        line.actual_cost = 300.0
        # NVL: 50 x A(10) + 100 x B(5) = 1000; tài nguyên 300
        self.assertEqual(move.material_amount, 1000.0)
        self.assertEqual(move.resource_amount, 300.0)
        self.assertEqual(move.stage_cost, 1300.0)
        self.assertEqual(move.stage_unit_cost, 26.0)
        self.assertEqual(move.transferred_in_cost, 0.0)
        self.assertEqual(move.unit_cost, 26.0)

    def test_resource_cost_is_per_bom_unit_times_move_qty(self):
        """(Chi phí BoM / SL thành phẩm BoM) x SL chuyển."""
        self.bom.product_qty = 10.0
        resource = self._make_resource("RES-UNIT")
        self.wo1.resource_ids = [
            Command.create({"resource_id": resource.id, "planned_cost": 400.0})
        ]
        self.assertEqual(self.wo1.resource_ids.unit_cost, 40.0)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 50.0,
            }
        )
        line = move.resource_line_ids
        self.assertEqual(line.actual_cost, 2000.0)
        move.move_qty = 20.0
        self.assertEqual(line.planned_cost, 800.0)
        self.assertEqual(line.actual_cost, 800.0)
        # BoM đổi sau đó không làm đổi đơn giá đã chốt ở lệnh công đoạn
        self.bom.product_qty = 100.0
        self.assertEqual(self.wo1.resource_ids.unit_cost, 40.0)

    def test_resource_cost_persists_when_saved_from_form(self):
        """Client không gửi lại trường readonly: server phải tự suy ra đơn giá."""
        resource = self._make_resource("RES-FORM")
        extra = self._make_resource("RES-FORM-EXTRA")
        self.wo1.resource_ids = [
            Command.create({"resource_id": resource.id, "planned_cost": 50.0}),
            Command.create({"resource_id": extra.id, "planned_cost": 80.0}),
        ]
        form = Form(self.env["ps.mfg.workorder.move"])
        form.workcenter_id = self.workcenter
        form.production_id = self.production
        form.to_workorder_id = self.wo1
        form.move_qty = 2.0
        move = form.save()
        lines = move.resource_line_ids.sorted("sequence")
        self.assertEqual(lines.mapped("unit_cost"), [50.0, 80.0])
        self.assertEqual(lines.mapped("planned_cost"), [100.0, 160.0])
        self.assertEqual(lines.mapped("actual_cost"), [100.0, 160.0])

    def test_manual_resource_line_takes_unit_cost_from_workorder(self):
        resource = self._make_resource("RES-MANUAL")
        self.wo1.resource_ids = [
            Command.create({"resource_id": resource.id, "planned_cost": 30.0})
        ]
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 4.0,
            }
        )
        move.resource_line_ids.unlink()
        line = self.env["ps.mfg.workorder.move.resource"].create(
            {"workorder_move_id": move.id, "resource_id": resource.id}
        )
        self.assertEqual(line.unit_cost, 30.0)
        self.assertEqual(line.planned_cost, 120.0)
        self.assertEqual(line.actual_cost, 120.0)

    def test_cumulative_cost_snapshot_from_upstream(self):
        resource = self._make_resource("RES-CUM")
        self.wo1.resource_ids = [
            Command.create({"resource_id": resource.id, "planned_cost": 200.0})
        ]
        # CĐ1: 1000 NVL + 200 tài nguyên cho 50 sp -> 24/sp
        self._approved_shift(self.wo1, 50.0, resource_cost=200.0)
        self.assertEqual(self.wo1.total_amount, 1200.0)
        self.assertEqual(self.wo1.unit_cost, 24.0)

        # CĐ2: nhận 50 sp từ CĐ1 (24/sp) + 25 x A(10) NVL riêng
        down = self._approved_shift(self.wo2, 50.0, from_wo=self.wo1)
        self.assertEqual(down.transferred_in_unit_cost, 24.0)
        self.assertEqual(down.transferred_in_cost, 1200.0)
        self.assertEqual(down.stage_cost, 250.0)
        self.assertEqual(down.stage_unit_cost, 5.0)
        self.assertEqual(down.total_cost, 1450.0)
        self.assertEqual(down.unit_cost, 29.0)
        self.assertEqual(self.wo2.total_amount, 250.0)
        self.assertEqual(self.wo2.stage_unit_cost, 5.0)
        self.assertEqual(self.wo2.transferred_in_cost, 1200.0)
        self.assertEqual(self.wo2.unit_cost, 29.0)

        # Ca CĐ1 mới giá khác: giá CĐ1 đổi nhưng ca CĐ2 đã duyệt giữ giá đã chốt
        self._approved_shift(self.wo1, 50.0, resource_cost=700.0)
        self.assertEqual(self.wo1.unit_cost, 29.0)
        self.assertEqual(down.transferred_in_unit_cost, 24.0)
        self.assertEqual(down.unit_cost, 29.0)

    def test_approved_resource_line_locked(self):
        resource = self._make_resource("RES-LOCK")
        self.wo1.resource_ids = [
            Command.create({"resource_id": resource.id, "planned_cost": 10.0})
        ]
        move = self._approved_shift(self.wo1, 10.0)
        with self.assertRaises(ValidationError):
            move.resource_line_ids.actual_cost = 99.0

    def test_workcenter_defaults_from_production(self):
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 10.0,
            }
        )
        self.assertEqual(move.workcenter_id, self.workcenter)

    def test_workcenter_must_match_production(self):
        other_wc = self.workcenter.copy({"name": "WC Move Other", "code": "WC-MOVE-O"})
        with self.assertRaises(ValidationError):
            self.env["ps.mfg.workorder.move"].create(
                {
                    "workcenter_id": other_wc.id,
                    "production_id": self.production.id,
                    "to_workorder_id": self.wo1.id,
                    "move_qty": 10.0,
                }
            )

    def test_change_workcenter_clears_foreign_production(self):
        other_wc = self.workcenter.copy(
            {"name": "WC Move Other 2", "code": "WC-MOVE-O2"}
        )
        with Form(self.env["ps.mfg.workorder.move"]) as form:
            form.workcenter_id = self.workcenter
            form.production_id = self.production
            form.workcenter_id = other_wc
            self.assertFalse(form.production_id)
            form.workcenter_id = self.workcenter
            form.production_id = self.production
            form.to_workorder_id = self.wo1
            form.move_qty = 5.0

    # ------------------------------------------------------------------
    # UX chuyển công đoạn: "Bắt đầu", đảo luồng To -> From, stepper
    # ------------------------------------------------------------------
    def test_start_move_label_and_quantities(self):
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "to_workorder_id": self.wo1.id,
                "move_qty": 30.0,
            }
        )
        self.assertFalse(move.from_workorder_id)
        self.assertEqual(move.from_label, "Start")
        # Từ "Bắt đầu": SL trước = 0, SL khả dụng = lượng theo NVL đã cấp.
        self.assertEqual(move.previous_qty, 0.0)
        self.assertEqual(move.available_qty, 100.0)

    def test_previous_qty_from_upstream(self):
        self._approved_shift(self.wo1, 50.0)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "from_workorder_id": self.wo1.id,
                "to_workorder_id": self.wo2.id,
                "move_qty": 20.0,
            }
        )
        self.assertEqual(move.from_label, self.wo1.display_name)
        self.assertEqual(move.previous_qty, 50.0)
        self.assertEqual(move.available_qty, 50.0)

    def test_onchange_to_sets_from(self):
        self._approved_shift(self.wo1, 50.0)
        form = Form(self.env["ps.mfg.workorder.move"])
        form.workcenter_id = self.workcenter
        form.production_id = self.production
        form.to_workorder_id = self.wo2
        self.assertEqual(form.from_workorder_id, self.wo1)
        form.to_workorder_id = self.wo1
        self.assertFalse(form.from_workorder_id)

    def test_onchange_to_leaves_from_empty_without_wip(self):
        form = Form(self.env["ps.mfg.workorder.move"])
        form.workcenter_id = self.workcenter
        form.production_id = self.production
        form.to_workorder_id = self.wo2
        self.assertFalse(form.from_workorder_id)

    def test_allowed_workorders_at_production_start(self):
        move = self.env["ps.mfg.workorder.move"].new(
            {"production_id": self.production.id}
        )
        # Mới bắt đầu: chỉ có thể nhận từ "Bắt đầu" vào công đoạn đầu.
        self.assertEqual(move.allowed_to_workorder_ids._origin.ids, self.wo1.ids)
        self.assertFalse(move.allowed_from_workorder_ids)

    def test_allowed_workorders_follow_to(self):
        self._approved_shift(self.wo1, 50.0)
        move = self.env["ps.mfg.workorder.move"].new(
            {"production_id": self.production.id, "to_workorder_id": self.wo2.id}
        )
        # Record .new() trả NewId: so sánh theo id gốc.
        self.assertEqual(
            move.allowed_to_workorder_ids._origin.ids,
            self.production.workorder_ids.ids,
        )
        self.assertEqual(move.allowed_from_workorder_ids._origin.ids, self.wo1.ids)

    def test_allowed_from_excludes_fully_moved_workorder(self):
        self._approved_shift(self.wo1, 50.0)
        moved = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": self.production.id,
                "from_workorder_id": self.wo1.id,
                "to_workorder_id": self.wo2.id,
                "move_qty": 50.0,
            }
        )
        new_move = self.env["ps.mfg.workorder.move"].new(
            {"production_id": self.production.id, "to_workorder_id": self.wo2.id}
        )
        self.assertFalse(new_move.allowed_from_workorder_ids)
        # Ca đã lưu vẫn thấy lại công đoạn nguồn của chính nó.
        self.assertEqual(moved.allowed_from_workorder_ids.ids, self.wo1.ids)

    def test_start_into_non_first_workorder_raises(self):
        with self.assertRaises(ValidationError):
            self.env["ps.mfg.workorder.move"].create(
                {
                    "production_id": self.production.id,
                    "to_workorder_id": self.wo2.id,
                }
            )

    def test_from_after_to_raises(self):
        with self.assertRaises(ValidationError):
            self.env["ps.mfg.workorder.move"].create(
                {
                    "production_id": self.production.id,
                    "from_workorder_id": self.wo2.id,
                    "to_workorder_id": self.wo1.id,
                }
            )

    def test_routing_progress(self):
        self._approved_shift(self.wo1, 40.0)
        move = self.env["ps.mfg.workorder.move"].new(
            {
                "production_id": self.production.id,
                "from_workorder_id": self.wo1.id,
                "to_workorder_id": self.wo2.id,
            }
        )
        progress = move.routing_progress
        self.assertEqual(progress["from_id"], self.wo1.id)
        self.assertEqual(progress["to_id"], self.wo2.id)
        self.assertEqual(progress["product_qty"], 100.0)
        steps = progress["steps"]
        self.assertFalse(steps[0]["id"])
        self.assertEqual(
            [s["id"] for s in steps[1:]], self.production.workorder_ids.ids
        )
        self.assertEqual(steps[1]["done_qty"], 40.0)
        self.assertEqual(steps[2]["done_qty"], 0.0)
        self.assertFalse(steps[0]["selectable"])
        self.assertTrue(steps[1]["selectable"])
        self.assertTrue(steps[2]["selectable"])

    def test_routing_progress_selectable_at_production_start(self):
        move = self.env["ps.mfg.workorder.move"].new(
            {"production_id": self.production.id}
        )
        steps = move.routing_progress["steps"]
        # Mới bắt đầu: chỉ công đoạn đầu chọn được (nhận từ "Bắt đầu").
        self.assertEqual(
            [s["selectable"] for s in steps],
            [False, True, False],
        )

    def test_workorder_action_prefills_move(self):
        action = self.wo2.action_create_workorder_move()
        ctx = action["context"]
        self.assertEqual(action["res_model"], "ps.mfg.workorder.move")
        self.assertEqual(ctx["default_to_workorder_id"], self.wo2.id)
        self.assertEqual(ctx["default_from_workorder_id"], self.wo1.id)
        self.assertEqual(ctx["default_production_id"], self.production.id)
        self.assertEqual(ctx["default_workcenter_id"], self.workcenter.id)
        self.assertFalse(
            self.wo1.action_create_workorder_move()["context"][
                "default_from_workorder_id"
            ]
        )
