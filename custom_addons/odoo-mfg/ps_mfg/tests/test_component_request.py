from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from .common import create_received_component_request, operation_line


@tagged("post_install", "-at_install")
class TestMfgComponentRequest(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.finished = cls.env["product.product"].create(
            {
                "name": "CR Finished",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.comp = cls.env["product.product"].create(
            {
                "name": "CR Component",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.raw_location = cls.env["stock.location"].create(
            {
                "name": "Test Raw Location",
                "usage": "internal",
            }
        )
        cls.workshop_location = cls.env["stock.location"].create(
            {
                "name": "Test Workshop Location",
                "usage": "internal",
            }
        )
        cls.workcenter = cls.env["ps.mfg.work.center"].create(
            {
                "name": "WC CR Test",
                "code": "WC-CR-T",
                "location_id": cls.workshop_location.id,
                "expense_account_id": cls.env["account.account"].search([], limit=1).id,
                "wip_account_id": cls.env["account.account"].search([], limit=1).id,
                "mo_prefix": "MO/CR/",
                "comp_request_prefix": "CR/CR/",
                "receipt_request_prefix": "RC/CR/",
            }
        )
        cls.bom = cls.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": cls.finished.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": cls.uom_unit.id,
                "operation_ids": [operation_line(cls.env, "Op 1", 1)],
            }
        )
        op1 = cls.bom.operation_ids.filtered(lambda o: o.name == "Op 1")
        cls.env["ps.mfg.bom.line"].create(
            {
                "bom_id": cls.bom.id,
                "product_id": cls.comp.id,
                "quantity": 2.0,
                "product_uom_id": cls.uom_unit.id,
                "operation_id": op1.id,
            }
        )
        cls.production = cls.env["ps.mfg.production"].create(
            {
                "bom_id": cls.bom.id,
                "product_id": cls.finished.id,
                "product_qty": 50.0,
                "workcenter_id": cls.workcenter.id,
            }
        )

    def _confirmed_mo(self):
        self.production.action_confirm()
        self.production.invalidate_recordset()
        return self.production

    def _create_request(self, mo, **kwargs):
        vals = {
            "production_id": mo.id,
            "product_qty": kwargs.pop("product_qty", 50.0),
            "location_id": kwargs.pop("location_id", self.raw_location.id),
        }
        vals.update(kwargs)
        return self.env["ps.mfg.component.request"].create(vals)

    def test_action_returns_prefilled_form(self):
        mo = self._confirmed_mo()
        action = mo.action_create_component_request()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "ps.mfg.component.request")
        self.assertEqual(action["context"]["default_production_id"], mo.id)
        self.assertEqual(action["context"]["default_product_qty"], 50.0)
        # Simulate user opening the form, selecting location_id then saving: lines precomputed from BoM.
        req = self._create_request(
            mo,
            product_qty=action["context"]["default_product_qty"],
        )
        self.assertEqual(len(req.component_line_ids), 1)
        line = req.component_line_ids[0]
        self.assertEqual(line.product_id, self.comp)
        self.assertEqual(line.qty_planned, 100.0)  # 2.0 x 50
        self.assertEqual(line.location_id, self.raw_location)

    def test_action_blocked_when_not_confirmed(self):
        self.assertEqual(self.production.state, "draft")
        with self.assertRaises(UserError):
            self.production.action_create_component_request()

    def test_action_blocked_when_request_exists(self):
        mo = self._confirmed_mo()
        self._create_request(mo, product_qty=50.0)
        mo.invalidate_recordset()
        self.assertTrue(mo.has_component_request)
        with self.assertRaises(UserError):
            mo.action_create_component_request()

    def test_unique_effective_request(self):
        mo = self._confirmed_mo()
        req1 = self._create_request(mo, product_qty=50.0)
        with self.assertRaises(ValidationError):
            self._create_request(mo, product_qty=60.0)
        # Cancel rồi thì được tạo mới.
        req1.state = "cancelled"
        mo.invalidate_recordset()
        self.assertFalse(mo.has_component_request)
        req2 = self._create_request(mo, product_qty=60.0)
        mo.invalidate_recordset()
        self.assertTrue(mo.has_component_request)
        self.assertEqual(req2.product_qty, 60.0)
        # Cancel xong nút tạo lại mở được form.
        req2.state = "cancelled"
        mo.invalidate_recordset()
        action = mo.action_create_component_request()
        self.assertEqual(action["res_model"], "ps.mfg.component.request")

    def test_move_uses_effective_request_not_cancelled(self):
        mo = self._confirmed_mo()
        wo = mo.workorder_ids.sorted("sequence")[0]
        old_req = self._create_request(mo, product_qty=100.0)
        old_req.state = "cancelled"
        create_received_component_request(self.env, mo, 60.0, self.raw_location)
        move = self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": mo.id,
                "to_workorder_id": wo.id,
                "move_qty": 10.0,
            }
        )
        # CĐ đầu lấy available từ YCCP hiệu lực (60), bỏ qua cái đã cancel (100).
        self.assertEqual(move._get_available_qty(), 60.0)

    def test_smart_button_navigates_to_effective_request(self):
        mo = self._confirmed_mo()
        self.assertEqual(mo.component_request_count, 0)
        req = self._create_request(mo, product_qty=50.0)
        mo.invalidate_recordset()
        self.assertEqual(mo.component_request_count, 1)
        # 1 YCCP hiệu lực → mở thẳng form.
        action = mo.action_view_component_requests()
        self.assertEqual(action["res_model"], "ps.mfg.component.request")
        self.assertEqual(action["view_mode"], "form")
        self.assertEqual(action["res_id"], req.id)
        # Cancel → count về 0, nút ẩn (fallback list rỗng).
        req.state = "cancelled"
        mo.invalidate_recordset()
        self.assertEqual(mo.component_request_count, 0)
        action = mo.action_view_component_requests()
        self.assertEqual(action["view_mode"], "list,form")
        self.assertEqual(action["domain"], [("id", "in", [])])

    def test_line_location_default_from_header_and_override(self):
        mo = self._confirmed_mo()
        custom_loc = self.env["stock.location"].create(
            {
                "name": "Custom Component Store",
                "usage": "internal",
            }
        )

        req = self._create_request(
            mo,
            product_qty=50.0,
            location_id=self.raw_location.id,
        )
        self.assertEqual(len(req.component_line_ids), 1)
        line = req.component_line_ids[0]
        # Line inherits location_id from header
        self.assertEqual(line.location_id, self.raw_location)

        # Allow selecting/overriding a different location at line level
        line.location_id = custom_loc
        self.assertEqual(line.location_id, custom_loc)

        # Modifying line quantity does not reset line location_id
        line.qty_planned = 80.0
        self.assertEqual(line.location_id, custom_loc)

    def test_source_and_destination_cannot_be_same(self):
        mo = self._confirmed_mo()
        # Header source cannot be the same as workshop destination
        with self.assertRaises(ValidationError):
            self.env["ps.mfg.component.request"].create(
                {
                    "production_id": mo.id,
                    "product_qty": 50.0,
                    "location_id": self.workshop_location.id,
                }
            )

        # Line source cannot be the same as workshop destination
        req = self._create_request(mo, product_qty=50.0)
        line = req.component_line_ids[0]
        with self.assertRaises(ValidationError):
            line.location_id = self.workshop_location

    def test_confirm_and_cancel_workflow(self):
        mo = self._confirmed_mo()
        req = self._create_request(mo, product_qty=50.0)
        self.assertEqual(req.state, "draft")
        req.action_submit_approval()
        self.assertEqual(req.state, "pending")
        with self.assertRaises(UserError):
            req.action_submit_approval()
        # Confirmed request can still be edited and cancelled
        req.product_qty = 40.0
        req.action_cancel()
        self.assertEqual(req.state, "cancelled")

        # Draft request can be cancelled directly
        req2 = self._create_request(mo, product_qty=50.0)
        req2.action_cancel()
        self.assertEqual(req2.state, "cancelled")

    def test_approved_request_cannot_be_cancelled(self):
        mo = self._confirmed_mo()
        req = self._create_request(mo, product_qty=50.0)
        req.action_submit_approval()
        req.action_approve()
        with self.assertRaises(UserError):
            req.action_cancel()
        with self.assertRaises(UserError):
            req.write({"state": "cancelled"})
        with self.assertRaises(UserError):
            req.unlink()
        self.assertEqual(req.state, "approved")

    def test_approved_request_is_locked(self):
        mo = self._confirmed_mo()
        req = self._create_request(mo, product_qty=50.0)
        req.action_approve()
        self.assertTrue(req.is_readonly)
        custom_loc = self.env["stock.location"].create(
            {"name": "Locked Test Store", "usage": "internal"}
        )
        with self.assertRaises(UserError):
            req.product_qty = 10.0
        with self.assertRaises(UserError):
            req.location_id = custom_loc
        line = req.component_line_ids[0]
        with self.assertRaises(UserError):
            line.qty_planned = 1.0
        with self.assertRaises(UserError):
            line.unlink()
        with self.assertRaises(UserError):
            self.env["ps.mfg.component.request.line"].create(
                {
                    "request_id": req.id,
                    "product_id": self.comp.id,
                    "qty_planned": 1.0,
                }
            )
        # Internal state transitions and chatter keep working
        req.message_post(body="Still allowed")
        req.action_force_done()
        self.assertEqual(req.state, "done")
