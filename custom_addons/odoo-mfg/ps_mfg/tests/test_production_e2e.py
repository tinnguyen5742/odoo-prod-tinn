from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from .common import (
    create_received_component_request,
    get_component_source_location,
    operation_line,
)


@tagged("post_install", "-at_install")
class TestMfgProductionE2E(TransactionCase):
    """Luồng đầy đủ: MO → YCCP → nhận NVL → giao ca các công đoạn →
    nhập thành phẩm → hoàn thành MO (kể cả theo lot / serial)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        parent_loc = cls.env["stock.location"].search(
            [
                ("usage", "=", "internal"),
                ("company_id", "in", (False, cls.env.company.id)),
            ],
            limit=1,
        )
        cls.dest_good = cls.env["stock.location"].create(
            {
                "name": "E2E Finish Good Dest",
                "usage": "internal",
                "location_id": parent_loc.id,
            }
        )
        account = cls.env["account.account"].search([], limit=1)
        cls.workcenter = cls.env["ps.mfg.work.center"].create(
            {
                "name": "WC E2E Test",
                "code": "WC-E2E-T",
                "location_id": parent_loc.id,
                "expense_account_id": account.id,
                "wip_account_id": account.id,
                "mo_prefix": "MO/E2E/",
                "comp_request_prefix": "CR/E2E/",
                "receipt_request_prefix": "RC/E2E/",
            }
        )
        cls.workshop = cls.workcenter.location_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _make_product(self, name, tracking=None, **vals):
        values = {
            "name": name,
            "type": "consu",
            "uom_id": self.uom_unit.id,
            "is_storable": True,
        }
        if tracking:
            values["tracking"] = tracking
        values.update(vals)
        return self.env["product.product"].create(values)

    def _make_lot(self, product, name):
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": product.id,
                "company_id": self.env.company.id,
            }
        )

    def _build_production(self, qty, comp_tracking=None, fg_tracking=None):
        """MO ``qty`` sp, BoM 2 công đoạn, 1 NVL (1:1) ở Op 1; đã confirm + start."""
        self.finished = self._make_product("E2E Finished", fg_tracking)
        self.comp = self._make_product(
            "E2E Component", comp_tracking, standard_price=10.0
        )
        bom = self.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": self.finished.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": self.uom_unit.id,
                "operation_ids": [
                    operation_line(self.env, "E2E Op 1", 1),
                    operation_line(self.env, "E2E Op 2", 2),
                ],
            }
        )
        op1 = bom.operation_ids.filtered(lambda o: o.name == "E2E Op 1")
        self.env["ps.mfg.bom.line"].create(
            {
                "bom_id": bom.id,
                "product_id": self.comp.id,
                "quantity": 1.0,
                "product_uom_id": self.uom_unit.id,
                "operation_id": op1.id,
            }
        )
        production = self.env["ps.mfg.production"].create(
            {
                "bom_id": bom.id,
                "product_id": self.finished.id,
                "product_qty": qty,
                "workcenter_id": self.workcenter.id,
            }
        )
        self.assertEqual(production.state, "draft")
        self.assertEqual(len(production.workorder_ids), 2)
        production.action_confirm()
        self.assertEqual(production.state, "confirmed")
        production.action_start()
        self.assertEqual(production.state, "in_progress")
        self.source_location = get_component_source_location(self.env, self.workshop)
        return production

    def _stock(self, product, location, lot=None):
        return self.env["stock.quant"]._get_available_quantity(
            product, location, lot_id=lot, strict=True
        )

    def _receive_tracked_components(self, production, qty, lot_qtys):
        """YCCP duyệt + phiếu lấy NVL, gán lot/serial trên move line rồi validate."""
        request = self.env["ps.mfg.component.request"].create(
            {
                "production_id": production.id,
                "product_qty": qty,
                "location_id": self.source_location.id,
            }
        )
        request.action_approve()
        lines = request.component_line_ids
        lines.action_create_pick_transfer()
        pickings = lines.move_ids.picking_id
        move = pickings.move_ids
        self.assertEqual(len(move), 1)
        move.move_line_ids.unlink()
        move.move_line_ids = [
            Command.create(
                {
                    "product_id": move.product_id.id,
                    "product_uom_id": move.product_uom.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "lot_id": lot.id,
                    "quantity": lot_qty,
                    "picked": True,
                }
            )
            for lot, lot_qty in lot_qtys
        ]
        move.picked = True
        pickings.button_validate()
        self.assertEqual(pickings.state, "done")
        return request

    def _workorder_move(self, production, to_wo, qty, from_wo=None, **vals):
        values = {
            "production_id": production.id,
            "to_workorder_id": to_wo.id,
            "move_qty": qty,
        }
        if from_wo:
            values["from_workorder_id"] = from_wo.id
        values.update(vals)
        return self.env["ps.mfg.workorder.move"].create(values)

    def _create_finish_proposal(self, workorder, qty):
        return self.env["ps.mfg.proposal.finish"].create(
            {
                "dst_location_id": self.dest_good.id,
                "line_ids": [
                    Command.create(
                        {
                            "production_id": workorder.production_id.id,
                            "workorder_id": workorder.id,
                            "finish_qty": qty,
                            "dst_location_id": self.dest_good.id,
                        }
                    )
                ],
            }
        )

    def _set_lot_names(self, line, qty_by_name):
        """Mô phỏng nhập lot ở popup Details: move line có lot_name."""
        move = line.move_id
        move.move_line_ids.unlink()
        move.move_line_ids = [
            Command.create(
                {
                    "lot_name": name,
                    "quantity": qty,
                    "product_id": move.product_id.id,
                    "product_uom_id": move.product_uom.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                }
            )
            for name, qty in qty_by_name.items()
        ]

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_full_flow_mo_to_done(self):
        production = self._build_production(100.0)
        self.env["stock.quant"]._update_available_quantity(
            self.comp, self.source_location, 100.0
        )
        create_received_component_request(
            self.env, production, 100.0, self.source_location
        )
        self.assertEqual(self._stock(self.comp, self.source_location), 0.0)
        self.assertEqual(self._stock(self.comp, self.workshop), 100.0)

        wo1, wo2 = production.workorder_ids.sorted("sequence")
        self._workorder_move(production, wo1, 100.0).action_approve()
        # NVL đã tiêu hao ở kho xưởng; còn công đoạn 2 chưa giao ca
        self.assertEqual(self._stock(self.comp, self.workshop), 0.0)
        self.assertFalse(production.all_workorders_done)

        self._workorder_move(production, wo2, 100.0, from_wo=wo1).action_approve()
        self.assertTrue(production.all_workorders_done)

        proposal = self._create_finish_proposal(wo2, 100.0)
        proposal.action_submit_approval()
        self.assertEqual(proposal.state, "pending")
        proposal.action_approve()
        self.assertEqual(proposal.state, "approved")
        self.assertTrue(all(m.state == "done" for m in proposal.move_ids))
        self.assertEqual(self._stock(self.finished, self.dest_good), 100.0)
        self.assertAlmostEqual(proposal.move_ids.price_unit, wo2.unit_cost, places=4)

        production.action_done()
        self.assertEqual(production.state, "done")
        self.assertTrue(production.date_finished)
        self.assertEqual(production.qty_produced, 100.0)

    def test_partial_flow_not_all_done(self):
        production = self._build_production(100.0)
        self.env["stock.quant"]._update_available_quantity(
            self.comp, self.source_location, 100.0
        )
        create_received_component_request(
            self.env, production, 100.0, self.source_location
        )
        wo1, wo2 = production.workorder_ids.sorted("sequence")
        self._workorder_move(production, wo1, 50.0).action_approve()
        self._workorder_move(production, wo2, 50.0, from_wo=wo1).action_approve()
        self.assertFalse(production.all_workorders_done)

        proposal = self._create_finish_proposal(wo2, 50.0)
        proposal.action_approve()
        self.assertEqual(proposal.state, "approved")
        self.assertEqual(self._stock(self.finished, self.dest_good), 50.0)

    def test_done_exceeds_tolerance_raises(self):
        production = self._build_production(10.0)
        production.qty_produced = 20.0
        with self.assertRaises(UserError):
            production.action_done()
        self.assertEqual(production.state, "in_progress")

    def test_done_from_draft_raises(self):
        production = self._build_production(10.0)
        production.action_cancel()
        production.action_draft()
        self.assertEqual(production.state, "draft")
        with self.assertRaises(UserError):
            production.action_done()

    def test_full_flow_with_lot_tracking(self):
        production = self._build_production(
            100.0, comp_tracking="lot", fg_tracking="lot"
        )
        lot_c1 = self._make_lot(self.comp, "E2E-LOT-C-1")
        lot_c2 = self._make_lot(self.comp, "E2E-LOT-C-2")
        quant = self.env["stock.quant"]
        quant._update_available_quantity(
            self.comp, self.source_location, 60.0, lot_id=lot_c1
        )
        quant._update_available_quantity(
            self.comp, self.source_location, 60.0, lot_id=lot_c2
        )
        self._receive_tracked_components(
            production, 100.0, [(lot_c1, 60.0), (lot_c2, 40.0)]
        )
        self.assertEqual(self._stock(self.comp, self.workshop, lot_c1), 60.0)
        self.assertEqual(self._stock(self.comp, self.workshop, lot_c2), 40.0)
        self.assertEqual(self._stock(self.comp, self.source_location, lot_c1), 0.0)
        self.assertEqual(self._stock(self.comp, self.source_location, lot_c2), 20.0)

        wo1, wo2 = production.workorder_ids.sorted("sequence")
        move1 = self._workorder_move(production, wo1, 100.0)
        line = move1.workorder_component_line_ids.filtered(
            lambda ln: ln.component_id == self.comp
        )
        line.lot_line_ids = [
            Command.clear(),
            Command.create({"lot_id": lot_c1.id, "qty": 60.0}),
            Command.create({"lot_id": lot_c2.id, "qty": 40.0}),
        ]
        move1.action_approve()
        sml = move1.consumption_move_ids.move_line_ids
        self.assertEqual(
            {ml.lot_id: ml.quantity for ml in sml}, {lot_c1: 60.0, lot_c2: 40.0}
        )
        self.assertEqual(self._stock(self.comp, self.workshop, lot_c1), 0.0)
        self.assertEqual(self._stock(self.comp, self.workshop, lot_c2), 0.0)
        self.assertEqual(wo1.consumed_lot_ids, lot_c1 | lot_c2)

        self._workorder_move(production, wo2, 100.0, from_wo=wo1).action_approve()
        self.assertTrue(production.all_workorders_done)

        proposal = self._create_finish_proposal(wo2, 100.0)
        fg_line = proposal.line_ids
        with self.assertRaises(UserError):
            proposal.action_submit_approval()
        self._set_lot_names(fg_line, {"E2E-LOT-FG-A": 70.0, "E2E-LOT-FG-B": 30.0})
        proposal.action_submit_approval()
        proposal.action_approve()
        self.assertEqual(proposal.state, "approved")
        fg_lots = {
            ml.lot_id.name: ml.quantity for ml in proposal.move_ids.move_line_ids
        }
        self.assertEqual(fg_lots, {"E2E-LOT-FG-A": 70.0, "E2E-LOT-FG-B": 30.0})
        for lot in proposal.move_ids.move_line_ids.lot_id:
            expected = fg_lots[lot.name]
            self.assertEqual(self._stock(self.finished, self.dest_good, lot), expected)

        production.action_done()
        self.assertEqual(production.state, "done")

    def test_full_flow_with_serial_tracking(self):
        production = self._build_production(
            3.0, comp_tracking="serial", fg_tracking="serial"
        )
        serials = [self._make_lot(self.comp, f"E2E-SN-C-{i}") for i in (1, 2, 3)]
        for serial in serials:
            self.env["stock.quant"]._update_available_quantity(
                self.comp, self.source_location, 1.0, lot_id=serial
            )
        self._receive_tracked_components(
            production, 3.0, [(serial, 1.0) for serial in serials]
        )
        for serial in serials:
            self.assertEqual(self._stock(self.comp, self.workshop, serial), 1.0)

        wo1, wo2 = production.workorder_ids.sorted("sequence")
        move1 = self._workorder_move(production, wo1, 3.0)
        line = move1.workorder_component_line_ids.filtered(
            lambda ln: ln.component_id == self.comp
        )
        line.actual_qty = 3.0
        line.lot_line_ids = [
            Command.create({"lot_id": serial.id, "qty": 1.0}) for serial in serials
        ]
        move1.action_approve()
        sml = move1.consumption_move_ids.move_line_ids
        self.assertEqual(set(sml.lot_id.ids), set(s.id for s in serials))
        for serial in serials:
            self.assertEqual(self._stock(self.comp, self.workshop, serial), 0.0)

        self._workorder_move(production, wo2, 3.0, from_wo=wo1).action_approve()
        self.assertTrue(production.all_workorders_done)

        proposal = self._create_finish_proposal(wo2, 3.0)
        fg_move = proposal.line_ids.move_id
        fg_move._generate_serial_numbers("E2E-SN-FG-001", next_serial_count=3)
        proposal.action_approve()
        self.assertEqual(proposal.state, "approved")
        self.assertEqual(fg_move.state, "done")
        fg_serials = fg_move.move_line_ids.lot_id
        self.assertEqual(
            sorted(fg_serials.mapped("name")),
            ["E2E-SN-FG-001", "E2E-SN-FG-002", "E2E-SN-FG-003"],
        )
        for serial in fg_serials:
            self.assertEqual(self._stock(self.finished, self.dest_good, serial), 1.0)
        self.assertEqual(proposal.line_ids.lot_ids, fg_serials)

        production.action_done()
        self.assertEqual(production.state, "done")
