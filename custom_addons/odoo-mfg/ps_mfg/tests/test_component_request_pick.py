from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import Form, TransactionCase, tagged

from .common import operation_line


@tagged("post_install", "-at_install")
class TestComponentRequestPick(TransactionCase):
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
        cls.source_loc_a = cls.env["stock.location"].create(
            {"name": "Pick Store A", "usage": "internal", "location_id": parent_loc.id}
        )
        cls.source_loc_b = cls.env["stock.location"].create(
            {"name": "Pick Store B", "usage": "internal", "location_id": parent_loc.id}
        )
        cls.workshop_loc = cls.env["stock.location"].create(
            {"name": "Pick Workshop", "usage": "internal", "location_id": parent_loc.id}
        )
        account = cls.env["account.account"].search([], limit=1)
        cls.product_finished = cls.env["product.product"].create(
            {"name": "Pick Table", "type": "consu", "uom_id": cls.uom_unit.id}
        )
        cls.raw_wood = cls.env["product.product"].create(
            {"name": "Pick Wood", "type": "consu", "uom_id": cls.uom_unit.id}
        )
        cls.raw_screw = cls.env["product.product"].create(
            {"name": "Pick Screw", "type": "consu", "uom_id": cls.uom_unit.id}
        )
        cls.wc = cls.env["ps.mfg.work.center"].create(
            {
                "name": "Pick WC",
                "code": "WC-PICK",
                "location_id": cls.workshop_loc.id,
                "expense_account_id": account.id,
                "wip_account_id": account.id,
                "mo_prefix": "MO/PICK/",
                "comp_request_prefix": "CR/PICK/",
                "receipt_request_prefix": "RC/PICK/",
            }
        )
        # 1 Table = 2 Wood + 4 Screw
        cls.bom = cls.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": cls.product_finished.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": cls.uom_unit.id,
                "operation_ids": [operation_line(cls.env, "Assembly", 1)],
            }
        )
        op = cls.bom.operation_ids[0]
        for product, qty in ((cls.raw_wood, 2.0), (cls.raw_screw, 4.0)):
            cls.env["ps.mfg.bom.line"].create(
                {
                    "bom_id": cls.bom.id,
                    "product_id": product.id,
                    "quantity": qty,
                    "product_uom_id": cls.uom_unit.id,
                    "operation_id": op.id,
                }
            )

    def _create_request(self, qty=10.0, approve=True):
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
                "location_id": self.source_loc_a.id,
            }
        )
        # Ốc vít lấy ở kho B
        self._line(req, self.raw_screw).location_id = self.source_loc_b
        if approve:
            req.action_submit_approval()
            req.action_approve()
        return req

    @staticmethod
    def _line(req, product):
        return req.component_line_ids.filtered(lambda line: line.product_id == product)

    @staticmethod
    def _validate(picking, qty_by_product=None):
        for move in picking.move_ids:
            move.quantity = (qty_by_product or {}).get(
                move.product_id, move.product_uom_qty
            )
            move.picked = True
        picking.with_context(
            skip_backorder=True, cancel_backorder=True
        ).button_validate()

    def test_same_product_lines_not_merged_on_pick(self):
        """2 dòng YCCP cùng NVL, cùng kho nguồn: mỗi dòng giữ move riêng sau khi pick."""
        req = self._create_request(approve=False)
        req.component_line_ids = [
            Command.create(
                {
                    "product_id": self.raw_wood.id,
                    "qty_planned": 5.0,
                    "qty_bom": 5.0,
                    "product_uom_id": self.uom_unit.id,
                }
            )
        ]
        req.action_submit_approval()
        req.action_approve()
        wood_lines = self._line(req, self.raw_wood)
        self.assertEqual(len(wood_lines), 2)
        wood_lines.action_create_pick_transfer()
        picking = wood_lines.move_ids.picking_id
        self.assertEqual(len(picking), 1)
        self.assertEqual(len(picking.move_ids), 2)
        self._validate(picking)
        for line in wood_lines:
            self.assertEqual(line.qty_transferred, line.qty_planned)

    def test_pick_groups_by_source_location(self):
        req = self._create_request()
        wood, screw = self._line(req, self.raw_wood), self._line(req, self.raw_screw)
        self.assertEqual(wood.qty_to_pick, 20.0)
        self.assertEqual(screw.qty_to_pick, 40.0)

        action = (wood | screw).action_create_pick_transfer()
        self.assertEqual(action["report_name"], "ps_mfg.report_component_pick_document")

        pickings = req.picking_ids
        self.assertEqual(len(pickings), 2)
        self.assertEqual(
            pickings.mapped("location_id"), self.source_loc_a | self.source_loc_b
        )
        self.assertTrue(all(p.location_dest_id == self.workshop_loc for p in pickings))
        self.assertTrue(all(p.state not in ("draft", "cancel") for p in pickings))
        self.assertEqual(wood.move_ids.picking_id.location_id, self.source_loc_a)
        self.assertEqual(wood.qty_open, 20.0)
        self.assertEqual(wood.qty_to_propose, 0.0)
        self.assertEqual(wood.qty_to_pick, 0.0)
        self.assertFalse(req.has_remaining)

    def test_pick_in_installments_until_done(self):
        req = self._create_request()
        wood, screw = self._line(req, self.raw_wood), self._line(req, self.raw_screw)

        # Đợt 1: chỉ lấy 5 gỗ (sửa SL được dù YCCP đã duyệt/khóa)
        wood.qty_to_pick = 5.0
        wood.action_create_pick_transfer()
        self._validate(wood.move_ids.picking_id)
        self.assertEqual(wood.qty_transferred, 5.0)
        self.assertEqual(wood.qty_open, 0.0)
        self.assertEqual(wood.qty_to_pick, 15.0)
        self.assertEqual(req.transfer_status, "partial")
        self.assertEqual(req.state, "approved")

        # Đợt 2: lấy nốt toàn bộ
        (wood | screw).action_create_pick_transfer()
        for picking in req.picking_ids.filtered(lambda p: p.state != "done"):
            self._validate(picking)
        self.assertEqual(req.transfer_status, "full")
        self.assertEqual(req.state, "done")

    def test_pick_quantity_exceeds_remaining(self):
        req = self._create_request()
        wood = self._line(req, self.raw_wood)
        wood.qty_to_pick = 25.0
        with self.assertRaises(UserError):
            wood.action_create_pick_transfer()

    def test_pick_requires_approved_request(self):
        req = self._create_request(approve=False)
        with self.assertRaises(UserError):
            req.component_line_ids.action_create_pick_transfer()

    def test_locked_line_only_allows_qty_to_pick(self):
        req = self._create_request()
        wood = self._line(req, self.raw_wood)
        wood.qty_to_pick = 3.0
        self.assertEqual(wood.qty_to_pick, 3.0)
        with self.assertRaises(UserError):
            wood.qty_planned = 30.0

    def test_cancelled_transfer_releases_quantity(self):
        req = self._create_request()
        wood = self._line(req, self.raw_wood)
        wood.action_create_pick_transfer()
        self.assertEqual(wood.qty_open, 20.0)
        wood.move_ids.picking_id.action_cancel()
        self.assertEqual(wood.qty_open, 0.0)
        self.assertEqual(wood.qty_to_propose, 20.0)
        self.assertEqual(wood.qty_to_pick, 20.0)
        self.assertTrue(req.has_remaining)

    def test_open_pick_lines_action(self):
        req = self._create_request()
        action = req.action_open_pick_lines()
        self.assertEqual(action["res_model"], "ps.mfg.component.request.line")
        self.assertEqual(action["domain"], [("request_id", "=", req.id)])
        self.assertTrue(action["context"]["search_default_group_location"])

    def test_unsaved_line_location_kept_on_confirm(self):
        """Đổi kho nguồn trên dòng (chưa save) rồi bấm Confirm: phải lưu kho mới."""
        req = self._create_request(approve=False)
        wood = self._line(req, self.raw_wood)
        self.assertEqual(wood.location_id, self.source_loc_a)
        # Mô phỏng web client: lưu thay đổi của form rồi gọi nút Confirm
        req.web_save(
            {
                "component_line_ids": [
                    [1, wood.id, {"location_id": self.source_loc_b.id}]
                ]
            },
            {},
        )
        self.assertEqual(wood.location_id, self.source_loc_b)
        req.action_submit_approval()
        self.assertEqual(wood.location_id, self.source_loc_b)
        self.assertEqual(req.state, "pending")

    def test_form_line_location_kept_on_confirm(self):
        """Qua form (onchange như web client): đổi kho dòng rồi save/Confirm phải giữ kho mới."""
        mo = self.env["ps.mfg.production"].create(
            {
                "bom_id": self.bom.id,
                "product_id": self.product_finished.id,
                "product_qty": 10.0,
                "workcenter_id": self.wc.id,
            }
        )
        mo.action_confirm()
        form = Form(self.env["ps.mfg.component.request"])
        form.production_id = mo
        form.location_id = self.source_loc_a
        with form.component_line_ids.edit(0) as line:
            line.location_id = self.source_loc_b
        req = form.save()
        self.assertEqual(req.component_line_ids[0].location_id, self.source_loc_b)
        # Dòng sinh từ BoM phải giữ cờ is_from_bom (ẩn nút xóa)
        self.assertTrue(all(req.component_line_ids.mapped("is_from_bom")))

        # Bản ghi đã lưu: sửa tiếp kho dòng 2 rồi save + Confirm
        form = Form(req)
        with form.component_line_ids.edit(1) as line:
            line.location_id = self.source_loc_b
        form.save()
        req.action_submit_approval()
        self.assertEqual(
            req.component_line_ids.mapped("location_id"), self.source_loc_b
        )

    def test_print_pick_request_again(self):
        req = self._create_request()
        wood, screw = self._line(req, self.raw_wood), self._line(req, self.raw_screw)
        lines = self.env["ps.mfg.component.request.line"]
        ctx = req.action_open_pick_lines()["context"]
        with self.assertRaises(UserError):
            lines.with_context(**ctx).action_print_pick_request()

        (wood | screw).action_create_pick_transfer()
        # Chọn dòng: chỉ in phiếu của dòng đó
        action = wood.action_print_pick_request()
        self.assertEqual(action["report_name"], "ps_mfg.report_component_pick_document")
        self.assertEqual(action["context"]["active_ids"], wood.move_ids.picking_id.ids)
        # Không chọn dòng, YCCP có 2 phiếu: mở danh sách phiếu để chọn
        action = lines.with_context(**ctx).action_print_pick_request()
        self.assertEqual(action["res_model"], "stock.picking")
        self.assertEqual(sorted(action["domain"][0][2]), sorted(req.picking_ids.ids))
        # Chọn phiếu trong danh sách → in phiếu đó
        action = wood.move_ids.picking_id.action_print_component_pick()
        self.assertEqual(action["report_name"], "ps_mfg.report_component_pick_document")
        # Phiếu đã hủy không in; còn 1 phiếu thì in luôn
        wood.move_ids.picking_id.action_cancel()
        action = lines.with_context(**ctx).action_print_pick_request()
        self.assertEqual(action["context"]["active_ids"], screw.move_ids.picking_id.ids)
