from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from .common import (
    create_received_component_request,
    get_component_source_location,
    operation_line,
)


@tagged("post_install", "-at_install")
class TestMfgProposalFinish(TransactionCase):
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
                "name": "Finish Good Dest",
                "usage": "internal",
                "location_id": parent_loc.id,
            }
        )
        cls.dest_scrap = cls.env["stock.location"].create(
            {
                "name": "Finish Scrap Dest",
                "usage": "internal",
                "location_id": parent_loc.id,
            }
        )
        account = cls.env["account.account"].search([], limit=1)
        cls.finished = cls.env["product.product"].create(
            {
                "name": "Finish Product",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.comp = cls.env["product.product"].create(
            {
                "name": "Finish Component",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
                "standard_price": 10.0,
            }
        )
        cls.workcenter = cls.env["ps.mfg.work.center"].create(
            {
                "name": "WC Finish Test",
                "code": "WC-FIN-T",
                "location_id": parent_loc.id,
                "expense_account_id": account.id,
                "wip_account_id": account.id,
                "mo_prefix": "MO/F/",
                "comp_request_prefix": "CR/F/",
                "receipt_request_prefix": "RC/F/",
            }
        )
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
        cls.env["ps.mfg.bom.line"].create(
            {
                "bom_id": cls.bom.id,
                "product_id": cls.comp.id,
                "quantity": 1.0,
                "product_uom_id": cls.uom_unit.id,
                "operation_id": op1.id,
            }
        )
        cls.production = cls.env["ps.mfg.production"].create(
            {
                "bom_id": cls.bom.id,
                "product_id": cls.finished.id,
                "product_qty": 100.0,
                "workcenter_id": cls.workcenter.id,
            }
        )
        cls.production.action_confirm()
        cls.production.action_start()
        cls.source_location = get_component_source_location(
            cls.env, cls.workcenter.location_id
        )
        create_received_component_request(
            cls.env, cls.production, 100.0, cls.source_location
        )
        cls.wo1, cls.wo2 = cls.production.workorder_ids.sorted("sequence")
        cls.env["ps.mfg.workorder.move"].create(
            {
                "production_id": cls.production.id,
                "to_workorder_id": cls.wo1.id,
                "move_qty": 50.0,
            }
        ).action_approve()
        cls.env["ps.mfg.workorder.move"].create(
            {
                "production_id": cls.production.id,
                "from_workorder_id": cls.wo1.id,
                "to_workorder_id": cls.wo2.id,
                "move_qty": 50.0,
            }
        ).action_approve()

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

    def _create_proposal(self, lines, **vals):
        values = {
            "dst_location_id": self.dest_good.id,
            "line_ids": [Command.create(line) for line in lines],
        }
        values.update(vals)
        return self.env["ps.mfg.proposal.finish"].create(values)

    def _line_vals(self, workorder, qty, dest=None, **extra):
        vals = {
            "production_id": workorder.production_id.id,
            "workorder_id": workorder.id,
            "finish_qty": qty,
            "dst_location_id": (dest or self.dest_good).id,
        }
        vals.update(extra)
        return vals

    def test_can_finish_intermediate_wo_before_all_done(self):
        self.assertFalse(self.production.all_workorders_done)
        proposal = self._create_proposal([self._line_vals(self.wo1, 10.0)])
        line = proposal.line_ids
        self.assertEqual(line.workorder_id, self.wo1)
        self.assertEqual(line.product_id, self.finished)
        self.assertEqual(line.workorder_qty, 50.0)

    def test_product_code_defaults_and_edits_without_changing_master(self):
        original_code = self.finished.x_product_code
        self.assertTrue(original_code)
        proposal = self._create_proposal([self._line_vals(self.wo1, 10.0)])
        line = proposal.line_ids
        self.assertEqual(line.x_product_code, original_code)
        line.x_product_code = "CUSTOM-FG"
        self.assertEqual(line.x_product_code, "CUSTOM-FG")
        self.assertEqual(self.finished.x_product_code, original_code)
        self.assertEqual(line.product_id, self.finished)

    def test_onchange_defaults_last_wo_with_remaining(self):
        proposal = self._create_proposal([self._line_vals(self.wo1, 10.0)])
        line = self.env["ps.mfg.proposal.finish.line"].new(
            {
                "proposal_id": proposal.id,
                "production_id": self.production.id,
                "dst_location_id": self.dest_good.id,
            }
        )
        line._onchange_production_id()
        self.assertEqual(line.product_id, self.finished)
        self.assertEqual(line.x_product_code, self.finished.x_product_code)
        self.assertEqual(line.workorder_id, self.wo2)
        self.assertEqual(line.dst_location_id, self.dest_good)
        self.assertAlmostEqual(line.finish_qty, 50.0, places=2)

    def test_split_qty_same_wo_and_remaining_across_proposals(self):
        proposal = self._create_proposal(
            [
                self._line_vals(self.wo1, 30.0, self.dest_good),
                self._line_vals(self.wo1, 20.0, self.dest_scrap),
            ]
        )
        self.assertEqual(len(proposal.line_ids), 2)
        self.assertEqual(sum(proposal.line_ids.mapped("finish_qty")), 50.0)
        with self.assertRaises(ValidationError):
            self._create_proposal([self._line_vals(self.wo1, 1.0)])
        with self.assertRaises(ValidationError):
            self._create_proposal(
                [
                    self._line_vals(self.wo2, 40.0),
                    self._line_vals(self.wo2, 11.0),
                ]
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

    def test_line_creates_move_from_production_without_picking(self):
        proposal = self._create_proposal(
            [self._line_vals(self.wo1, 5.0, x_product_code="FG-CODE")]
        )
        line = proposal.line_ids
        move = line.move_id
        self.assertTrue(move)
        # Nguồn là kho ảo Production nên Odoo reserve ngay (như finished move của mrp)
        self.assertIn(move.state, ("confirmed", "assigned"))
        self.assertFalse(move.picking_id)
        self.assertEqual(move.location_id.usage, "production")
        self.assertEqual(move.location_dest_id, self.dest_good)
        self.assertEqual(move.product_uom_qty, 5.0)
        self.assertEqual(move.description_picking, "FG-CODE")
        self.assertTrue(move.picking_type_id.ps_mfg_finish_type)
        self.assertTrue(move.picking_type_id.use_create_lots)
        self.assertEqual(move.reference, proposal.code)
        # Sửa dòng thì move đi theo
        line.write({"finish_qty": 7.0, "dst_location_id": self.dest_scrap.id})
        self.assertEqual(move.product_uom_qty, 7.0)
        self.assertEqual(move.location_dest_id, self.dest_scrap)
        # Xóa dòng thì move bị hủy
        line.unlink()
        self.assertFalse(move.exists())

    def test_lot_required_on_submit(self):
        self._enable_tracking(self.finished, "lot")
        proposal = self._create_proposal([self._line_vals(self.wo1, 5.0)])
        line = proposal.line_ids
        with self.assertRaises(UserError):
            proposal.action_submit_approval()
        self._set_lot_names(line, {"LOT-FG": 3.0})
        with self.assertRaises(UserError):
            proposal.action_submit_approval()
        self._set_lot_names(line, {"LOT-FG": 3.0, "LOT-FG-2": 2.0})
        self.assertEqual(line.lot_names, "LOT-FG, LOT-FG-2")
        proposal.action_submit_approval()
        self.assertEqual(proposal.state, "pending")

    def test_details_popup_is_odoo_move_operations(self):
        self._enable_tracking(self.finished, "serial")
        proposal = self._create_proposal([self._line_vals(self.wo2, 3.0)])
        line = proposal.line_ids
        action = line.action_show_lot_details()
        self.assertEqual(action["res_model"], "stock.move")
        self.assertEqual(action["res_id"], line.move_id.id)
        self.assertEqual(
            action["view_id"], self.env.ref("stock.view_stock_move_operations").id
        )
        self.assertTrue(line.move_id.display_assign_serial)
        self.assertTrue(line.move_id.show_lots_text)

    def test_generate_serials_and_approve(self):
        self._enable_tracking(self.finished, "serial")
        proposal = self._create_proposal([self._line_vals(self.wo2, 3.0)])
        move = proposal.line_ids.move_id
        # Như nút Generate Serials của popup Odoo
        move._generate_serial_numbers("SN-001", next_serial_count=3)
        proposal.action_approve()
        self.assertEqual(proposal.state, "approved")
        self.assertEqual(move.state, "done")
        self.assertEqual(
            sorted(move.move_line_ids.lot_id.mapped("name")),
            ["SN-001", "SN-002", "SN-003"],
        )
        self.assertEqual(proposal.line_ids.lot_ids, move.move_line_ids.lot_id)

    def test_approve_prices_receipt_with_operation_unit_cost(self):
        self.assertTrue(self.wo1.unit_cost)
        proposal = self._create_proposal([self._line_vals(self.wo1, 10.0)])
        proposal.action_approve()
        move = proposal.move_ids
        self.assertEqual(len(move), 1)
        self.assertAlmostEqual(move.price_unit, self.wo1.unit_cost, places=4)

    def test_approve_creates_done_moves_with_lots(self):
        self._enable_tracking(self.finished, "lot")
        proposal = self._create_proposal(
            [
                self._line_vals(
                    self.wo1, 30.0, self.dest_good, x_product_code="FG-GOOD"
                ),
                self._line_vals(
                    self.wo1, 20.0, self.dest_scrap, x_product_code="FG-SCRAP"
                ),
            ]
        )
        good, scrap = proposal.line_ids.sorted("id")
        self._set_lot_names(good, {"LOT-GOOD": 30.0})
        self._set_lot_names(scrap, {"LOT-SCRAP": 20.0})
        proposal.action_approve()
        self.assertEqual(proposal.state, "approved")
        self.assertFalse(proposal.picking_ids)
        moves = proposal.move_ids
        self.assertEqual(len(moves), 2)
        self.assertFalse(moves.picking_id)
        self.assertTrue(all(m.state == "done" for m in moves))
        self.assertEqual(moves.location_id.usage, "production")
        qty_by_dest = {m.location_dest_id: m.quantity for m in moves}
        self.assertEqual(qty_by_dest[self.dest_good], 30.0)
        self.assertEqual(qty_by_dest[self.dest_scrap], 20.0)
        lot_by_dest = {
            ml.location_dest_id: ml.lot_id.name for ml in moves.move_line_ids
        }
        self.assertEqual(lot_by_dest[self.dest_good], "LOT-GOOD")
        self.assertEqual(lot_by_dest[self.dest_scrap], "LOT-SCRAP")
        self.assertEqual(
            set(moves.mapped("description_picking")), {"FG-GOOD", "FG-SCRAP"}
        )
        # Lịch sử dịch chuyển: tham chiếu = mã phiếu, bấm dòng mở về phiếu
        for record in (moves[0], moves.move_line_ids[0]):
            self.assertEqual(record.reference, proposal.code)
            ref_action = record.action_open_reference()
            self.assertEqual(ref_action["res_model"], "ps.mfg.proposal.finish")
            self.assertEqual(ref_action["res_id"], proposal.id)
        action = proposal.action_view_stock_moves()
        self.assertEqual(action["res_model"], "stock.move.line")
        self.assertEqual(
            self.env["stock.move.line"].search(action["domain"]), moves.move_line_ids
        )
        # Complete lần 2 không làm gì
        proposal.action_approve()
        self.assertEqual(proposal.move_ids, moves)

    def test_reject_cancels_moves(self):
        proposal = self._create_proposal([self._line_vals(self.wo1, 5.0)])
        move = proposal.line_ids.move_id
        proposal.action_reject()
        self.assertEqual(move.state, "cancel")

    def test_wip_sums_finish_lines_and_splits_productions(self):
        other = self.env["ps.mfg.production"].create(
            {
                "bom_id": self.bom.id,
                "product_id": self.finished.id,
                "product_qty": 80.0,
                "workcenter_id": self.workcenter.id,
            }
        )
        other.action_confirm()
        other.action_start()
        create_received_component_request(self.env, other, 80.0, self.source_location)
        other_wo = other.workorder_ids.sorted("sequence")[0]
        self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": other.id,
                "to_workorder_id": other_wo.id,
                "move_qty": 80.0,
            }
        ).action_approve()

        first = self._create_proposal(
            [self._line_vals(self.wo1, 20.0)],
            transaction_date="2022-07-05",
            state="approved",
        )
        self._create_proposal(
            [self._line_vals(self.wo1, 10.0, self.dest_scrap)],
            transaction_date="2022-07-20",
            state="approved",
        )
        multi = self._create_proposal(
            [
                self._line_vals(self.wo2, 15.0),
                self._line_vals(other_wo, 40.0),
            ],
            transaction_date="2022-07-25",
            state="approved",
        )
        wip = self.env["ps.mfg.wip"].create(
            {
                "account_id": self.env["account.account"].search([], limit=1).id,
                "period_date": "2022-07-01",
                "date": "2022-07-31",
            }
        )
        wip.action_fetch_finished_mos()
        by_production = {line.production_id.id: line for line in wip.line_ids}
        self.assertEqual(len(wip.line_ids), 2)
        self.assertAlmostEqual(
            by_production[self.production.id].receipt_qty, 45.0, places=2
        )
        self.assertAlmostEqual(by_production[other.id].receipt_qty, 40.0, places=2)
        self.assertEqual(by_production[self.production.id].description, multi.code)
        self.assertEqual(by_production[other.id].description, multi.code)
        self.assertNotEqual(first.code, multi.code)
