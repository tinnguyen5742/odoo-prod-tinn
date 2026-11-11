from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from .common import operation_line


@tagged("post_install", "-at_install")
class TestComponentRequestMultiTransfer(TransactionCase):
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
        cls.source_loc = cls.env["stock.location"].create(
            {
                "name": "Source Raw Material Storage",
                "usage": "internal",
                "location_id": parent_loc.id,
            }
        )
        cls.workshop_loc = cls.env["stock.location"].create(
            {
                "name": "Workshop Floor Loc",
                "usage": "internal",
                "location_id": parent_loc.id,
            }
        )
        account = cls.env["account.account"].search([], limit=1)
        cls.product_finished = cls.env["product.product"].create(
            {
                "name": "Finished Chair",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.raw_wood = cls.env["product.product"].create(
            {
                "name": "Raw Wood Plank",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.wc = cls.env["ps.mfg.work.center"].create(
            {
                "name": "Carpentry WC",
                "code": "WC-CARP",
                "location_id": cls.workshop_loc.id,
                "expense_account_id": account.id,
                "wip_account_id": account.id,
                "mo_prefix": "MO/TEST/",
                "comp_request_prefix": "CR/TEST/",
                "receipt_request_prefix": "RC/TEST/",
            }
        )
        # BoM: 1 Finished Chair needs 2 Wood Planks at Op 1
        cls.bom = cls.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": cls.product_finished.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": cls.uom_unit.id,
                "operation_ids": [operation_line(cls.env, "Cutting & Assembly", 1)],
            }
        )
        op1 = cls.bom.operation_ids[0]
        cls.env["ps.mfg.bom.line"].create(
            {
                "bom_id": cls.bom.id,
                "product_id": cls.raw_wood.id,
                "quantity": 2.0,
                "product_uom_id": cls.uom_unit.id,
                "operation_id": op1.id,
            }
        )

    def _create_mo_and_request(self, qty=10.0):
        # 10 Chairs -> needs 20 Wood Planks
        mo = self.env["ps.mfg.production"].create(
            {
                "bom_id": self.bom.id,
                "product_id": self.product_finished.id,
                "product_qty": qty,
                "workcenter_id": self.wc.id,
            }
        )
        mo.action_confirm()
        req = self.env["ps.mfg.component.request"].create(
            {
                "production_id": mo.id,
                "product_qty": qty,
                "location_id": self.source_loc.id,
            }
        )
        req.action_approve()
        return mo, req

    def test_multi_transfer_two_installments(self):
        """Kiểm tra xuất kho 2 đợt:
        - YCCP cần 20 gỗ.
        - Đợt 1: Đề xuất và xuất 12 gỗ -> YCCP partial, còn thiếu 8.
        - Đợt 2: Đề xuất và xuất 8 gỗ -> YCCP full và tự chuyển Done.
        """
        mo, req = self._create_mo_and_request(qty=10.0)
        req_line = req.component_line_ids[0]
        self.assertEqual(req_line.qty_planned, 20.0)
        self.assertEqual(req_line.qty_to_propose, 20.0)
        self.assertEqual(req.transfer_status, "none")
        self.assertTrue(req.has_remaining)

        # 1. Tạo Proposal đợt 1 xuất 12 cái
        prop1 = self.env["ps.mfg.proposal"].create(
            {
                "name": "Proposal Batch 1",
                "component_request_ids": [Command.set([req.id])],
                "source_location_id": self.source_loc.id,
            }
        )
        prop1_line = prop1.line_ids[0]
        self.assertEqual(prop1_line.qty_to_transfer, 20.0)  # Default all
        prop1_line.qty_to_transfer = 12.0  # Chỉnh xuất 12 cái

        # Submit -> qty_open = 12, req_line.qty_to_propose còn 8
        prop1.action_submit_approval()
        self.assertEqual(prop1_line.qty_open, 12.0)
        self.assertEqual(req_line.qty_to_propose, 8.0)

        # Approve proposal 1
        prop1.action_approve()
        picking1 = prop1.picking_ids
        self.assertEqual(len(picking1), 1)
        move1 = picking1.move_ids
        self.assertEqual(move1.component_request_line_id, req_line)
        self.assertEqual(move1.product_uom_qty, 12.0)

        # Validate picking 1
        picking1.action_confirm()
        move1.quantity = 12.0
        move1.picked = True
        picking1.button_validate()

        self.assertEqual(picking1.state, "done")
        self.assertEqual(req_line.qty_transferred, 12.0)
        self.assertEqual(req_line.qty_open, 0.0)
        self.assertEqual(req_line.qty_to_propose, 8.0)
        self.assertEqual(req.transfer_status, "partial")
        self.assertEqual(req.state, "approved")  # Chưa Done vì mới được 12/20
        self.assertTrue(req.has_remaining)

        # 2. Thử đề xuất vượt quá số còn lại (ví dụ 10 trong khi chỉ còn 8) -> Bị chặn
        with self.assertRaises(ValidationError):
            self.env["ps.mfg.proposal"].create(
                {
                    "name": "Invalid Over Proposal",
                    "component_request_ids": [Command.set([req.id])],
                    "source_location_id": self.source_loc.id,
                    "line_ids": [
                        Command.create(
                            {
                                "request_line_id": req_line.id,
                                "qty_to_transfer": 10.0,
                            }
                        )
                    ],
                }
            )

        # 3. Tạo Proposal đợt 2 xuất nốt 8 cái
        prop2 = self.env["ps.mfg.proposal"].create(
            {
                "name": "Proposal Batch 2",
                "component_request_ids": [Command.set([req.id])],
                "source_location_id": self.source_loc.id,
            }
        )
        prop2_line = prop2.line_ids[0]
        self.assertEqual(prop2_line.qty_to_transfer, 8.0)

        prop2.action_approve()
        picking2 = prop2.picking_ids
        picking2.action_confirm()
        picking2.move_ids.quantity = 8.0
        picking2.move_ids.picked = True
        picking2.button_validate()

        self.assertEqual(picking2.state, "done")
        self.assertEqual(req_line.qty_transferred, 20.0)
        self.assertEqual(req_line.qty_to_propose, 0.0)
        self.assertEqual(req.transfer_status, "full")
        self.assertEqual(req.state, "done")  # Tự động Done khi nhận đủ 100%
        self.assertFalse(req.has_remaining)

    def test_work_order_available_qty_limited_by_material(self):
        """Kiểm tra giới hạn sản lượng vào công đoạn (C):
        - MO 10 ghế, YCCP cần 20 gỗ.
        - Mới chuyển 10 gỗ (đạt 50% NVL) -> Công đoạn chỉ cho phép làm tối đa 5 ghế!
        """
        mo, req = self._create_mo_and_request(qty=10.0)
        req_line = req.component_line_ids[0]
        first_wo = mo.workorder_ids[0]

        # Ban đầu chưa nhận NVL nào -> producible_qty = 0
        self.assertEqual(req._get_producible_qty(first_wo), 0.0)

        # Cấp 10 gỗ (50%)
        prop = self.env["ps.mfg.proposal"].create(
            {
                "name": "Half Material Proposal",
                "component_request_ids": [Command.set([req.id])],
                "source_location_id": self.source_loc.id,
                "line_ids": [
                    Command.create(
                        {
                            "request_line_id": req_line.id,
                            "qty_to_transfer": 10.0,
                        }
                    )
                ],
            }
        )
        prop.action_approve()
        picking = prop.picking_ids
        picking.action_confirm()
        picking.move_ids.quantity = 10.0
        picking.move_ids.picked = True
        picking.button_validate()

        # Bây giờ đã nhận 10/20 gỗ -> sản lượng khả dụng là 5 ghế
        self.assertEqual(req._get_producible_qty(first_wo), 5.0)

        # Thử tạo giao ca công đoạn 1 với move_qty = 6 -> Bị ValidationError chặn lại
        with self.assertRaises(ValidationError):
            self.env["ps.mfg.workorder.move"].create(
                {
                    "production_id": mo.id,
                    "from_workorder_id": False,
                    "to_workorder_id": first_wo.id,
                    "shift": 1,
                    "move_qty": 6.0,
                }
            )

        # move_qty = 5.0 thì tạo thành công
        valid_move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": mo.id,
                "from_workorder_id": False,
                "to_workorder_id": first_wo.id,
                "shift": 1,
                "move_qty": 5.0,
            }
        )
        self.assertEqual(valid_move.move_qty, 5.0)

    def _receive_lines(self, lines):
        lines.action_create_pick_transfer()
        pickings = lines.move_ids.picking_id
        for move in pickings.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        pickings.button_validate()

    def test_unapproved_request_blocks_workorder_move(self):
        """YCCP chưa duyệt (draft/confirmed) chưa cấp NVL -> công đoạn không có SL khả dụng."""
        mo = self.env["ps.mfg.production"].create(
            {
                "bom_id": self.bom.id,
                "product_id": self.product_finished.id,
                "product_qty": 10.0,
                "workcenter_id": self.wc.id,
            }
        )
        mo.action_confirm()
        req = self.env["ps.mfg.component.request"].create(
            {
                "production_id": mo.id,
                "product_qty": 10.0,
                "location_id": self.source_loc.id,
            }
        )
        first_wo = mo.workorder_ids[0]
        self.assertEqual(req._get_producible_qty(first_wo), 0.0)
        req.action_submit_approval()
        self.assertEqual(req._get_producible_qty(first_wo), 0.0)
        with self.assertRaises(ValidationError):
            self.env["ps.mfg.workorder.move"].create(
                {
                    "production_id": mo.id,
                    "to_workorder_id": first_wo.id,
                    "move_qty": 1.0,
                }
            )

    def test_non_bom_line_ignored_in_producible_qty(self):
        """Dòng thêm ngoài BoM chưa nhận không chặn sản lượng công đoạn."""
        mo = self.env["ps.mfg.production"].create(
            {
                "bom_id": self.bom.id,
                "product_id": self.product_finished.id,
                "product_qty": 10.0,
                "workcenter_id": self.wc.id,
            }
        )
        mo.action_confirm()
        glue = self.env["product.product"].create(
            {"name": "Extra Glue", "type": "consu", "uom_id": self.uom_unit.id}
        )
        req = self.env["ps.mfg.component.request"].create(
            {
                "production_id": mo.id,
                "product_qty": 10.0,
                "location_id": self.source_loc.id,
            }
        )
        req.component_line_ids = [
            Command.create(
                {
                    "product_id": glue.id,
                    "qty_planned": 5.0,
                    "qty_bom": 5.0,
                    "product_uom_id": self.uom_unit.id,
                }
            )
        ]
        req.action_approve()
        bom_lines = req.component_line_ids.filtered("is_from_bom")
        self.assertEqual(len(req.component_line_ids - bom_lines), 1)
        self._receive_lines(bom_lines)
        self.assertEqual(req._get_producible_qty(mo.workorder_ids[0]), 10.0)

    def test_legacy_request_keeps_full_qty(self):
        mo, req = self._create_mo_and_request(qty=10.0)
        req.legacy_transfer = True
        self.assertEqual(req._get_producible_qty(mo.workorder_ids[0]), 10.0)

    def test_force_close_request(self):
        """Kiểm tra đóng YCCP thủ công khi chấp nhận thiếu hàng."""
        mo, req = self._create_mo_and_request(qty=10.0)
        req_line = req.component_line_ids[0]

        # Cấp 10/20 gỗ
        prop = self.env["ps.mfg.proposal"].create(
            {
                "name": "Partial Proposal",
                "component_request_ids": [Command.set([req.id])],
                "source_location_id": self.source_loc.id,
                "line_ids": [
                    Command.create(
                        {
                            "request_line_id": req_line.id,
                            "qty_to_transfer": 10.0,
                        }
                    )
                ],
            }
        )
        prop.action_approve()
        picking = prop.picking_ids
        picking.action_confirm()
        picking.move_ids.quantity = 10.0
        picking.move_ids.picked = True
        picking.button_validate()

        self.assertEqual(req.state, "approved")
        self.assertEqual(req.transfer_status, "partial")

        # Đóng thủ công
        req.action_force_done()
        self.assertEqual(req.state, "done")
        self.assertFalse(req.has_remaining)

    def test_protect_lines_recompute_and_qty_write(self):
        """Bảo vệ dòng NVL: Không cho sửa product_qty sau khi đã sinh đề xuất/phiếu chuyển."""
        mo, req = self._create_mo_and_request(qty=10.0)
        req_line = req.component_line_ids[0]

        prop = self.env["ps.mfg.proposal"].create(
            {
                "name": "Lock Test Proposal",
                "component_request_ids": [Command.set([req.id])],
                "source_location_id": self.source_loc.id,
            }
        )

        # Cố tình đổi product_qty của YCCP -> Phải bị chặn bằng UserError
        with self.assertRaises(UserError):
            req.write({"product_qty": 15.0})
