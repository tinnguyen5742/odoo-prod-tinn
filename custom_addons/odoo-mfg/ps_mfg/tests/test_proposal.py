from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from .common import operation_line


@tagged("post_install", "-at_install")
class TestMfgProposal(TransactionCase):
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
                "name": "Proposal Component Storage",
                "usage": "internal",
                "location_id": parent_loc.id,
            }
        )
        cls.dest_a = cls.env["stock.location"].create(
            {
                "name": "Proposal WC A Loc",
                "usage": "internal",
                "location_id": parent_loc.id,
            }
        )
        cls.dest_b = cls.env["stock.location"].create(
            {
                "name": "Proposal WC B Loc",
                "usage": "internal",
                "location_id": parent_loc.id,
            }
        )
        account = cls.env["account.account"].search([], limit=1)
        cls.finished = cls.env["product.product"].create(
            {
                "name": "Proposal Finished",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.comp = cls.env["product.product"].create(
            {
                "name": "Proposal Component",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.wc_a = cls.env["ps.mfg.work.center"].create(
            {
                "name": "WC Proposal A",
                "code": "WC-PROP-A",
                "location_id": cls.dest_a.id,
                "expense_account_id": account.id,
                "wip_account_id": account.id,
                "mo_prefix": "MO/PA/",
                "comp_request_prefix": "CR/PA/",
                "receipt_request_prefix": "RC/PA/",
            }
        )
        cls.wc_b = cls.env["ps.mfg.work.center"].create(
            {
                "name": "WC Proposal B",
                "code": "WC-PROP-B",
                "location_id": cls.dest_b.id,
                "expense_account_id": account.id,
                "wip_account_id": account.id,
                "mo_prefix": "MO/PB/",
                "comp_request_prefix": "CR/PB/",
                "receipt_request_prefix": "RC/PB/",
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

    def _make_request(self, workcenter, qty=10.0):
        production = self.env["ps.mfg.production"].create(
            {
                "bom_id": self.bom.id,
                "product_id": self.finished.id,
                "product_qty": qty,
                "workcenter_id": workcenter.id,
            }
        )
        return self.env["ps.mfg.component.request"].create(
            {
                "production_id": production.id,
                "product_qty": qty,
                "location_id": self.source_loc.id,
            }
        )

    def test_adding_requests_loads_components(self):
        req_a = self._make_request(self.wc_a, qty=10.0)
        req_b = self._make_request(self.wc_b, qty=5.0)
        proposal = self.env["ps.mfg.proposal"].create(
            {
                "name": "Multi Request",
                "component_request_ids": [Command.set([req_a.id, req_b.id])],
                "source_location_id": self.source_loc.id,
            }
        )
        self.assertEqual(len(proposal.component_line_ids), 2)
        self.assertEqual(
            set(proposal.component_line_ids.mapped("request_id").ids),
            {req_a.id, req_b.id},
        )
        qty_by_request = {
            line.request_id.id: line.qty_planned for line in proposal.component_line_ids
        }
        self.assertEqual(qty_by_request[req_a.id], 20.0)
        self.assertEqual(qty_by_request[req_b.id], 10.0)

    def test_approve_creates_picking_per_workcenter_dest(self):
        req_a = self._make_request(self.wc_a, qty=10.0)
        req_b = self._make_request(self.wc_b, qty=5.0)
        proposal = self.env["ps.mfg.proposal"].create(
            {
                "name": "Split Dest",
                "component_request_ids": [Command.set([req_a.id, req_b.id])],
                "source_location_id": self.source_loc.id,
            }
        )
        proposal.action_approve()
        self.assertEqual(proposal.state, "approved")
        # Proposal tracks transfer status
        self.assertEqual(proposal.transfer_state, "waiting")
        # Component requests are marked approved (not done until pickings validate)
        self.assertEqual(req_a.state, "approved")
        self.assertEqual(req_b.state, "approved")
        self.assertEqual(len(proposal.picking_ids), 2)
        dests = set(proposal.picking_ids.mapped("location_dest_id").ids)
        self.assertEqual(dests, {self.dest_a.id, self.dest_b.id})
        for picking in proposal.picking_ids:
            self.assertEqual(picking.location_id, self.source_loc)
            self.assertEqual(len(picking.move_ids), 1)
            self.assertEqual(
                picking.move_ids.location_dest_id, picking.location_dest_id
            )
            if picking.location_dest_id == self.dest_a:
                self.assertEqual(picking.move_ids.product_uom_qty, 20.0)
            else:
                self.assertEqual(picking.move_ids.product_uom_qty, 10.0)
        action = proposal.action_view_picking()
        self.assertEqual(action["view_mode"], "list,form")
        self.assertEqual(action["domain"], [("id", "in", proposal.picking_ids.ids)])

        # When pickings complete, proposal transfer_state becomes done and requests become done
        for picking in proposal.picking_ids:
            picking.action_confirm()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.button_validate()
        self.assertEqual(proposal.transfer_state, "done")
        self.assertEqual(req_a.state, "done")
        self.assertEqual(req_b.state, "done")

    def test_approve_same_dest_one_picking(self):
        req_a = self._make_request(self.wc_a, qty=10.0)
        req_b = self._make_request(self.wc_a, qty=5.0)
        proposal = self.env["ps.mfg.proposal"].create(
            {
                "name": "Same Dest",
                "component_request_ids": [Command.set([req_a.id, req_b.id])],
                "source_location_id": self.source_loc.id,
            }
        )
        proposal.action_approve()
        self.assertEqual(len(proposal.picking_ids), 1)
        picking = proposal.picking_ids
        self.assertEqual(picking.location_dest_id, self.dest_a)
        self.assertEqual(len(picking.move_ids), 2)
        self.assertEqual(sum(picking.move_ids.mapped("product_uom_qty")), 30.0)
        action = proposal.action_view_picking()
        self.assertEqual(action["view_mode"], "form")
        self.assertEqual(action["res_id"], picking.id)

    def test_approve_requires_requests(self):
        proposal = self.env["ps.mfg.proposal"].create(
            {
                "name": "Empty",
                "source_location_id": self.source_loc.id,
            }
        )
        with self.assertRaises(UserError):
            proposal.action_approve()

    def test_action_create_proposal_prefills_request(self):
        req = self._make_request(self.wc_a)
        action = req.action_create_proposal()
        self.assertEqual(action["res_model"], "ps.mfg.proposal")
        self.assertEqual(
            action["context"]["default_component_request_ids"],
            [Command.set([req.id])],
        )

    def test_picking_cancel_updates_transfer_state(self):
        req = self._make_request(self.wc_a)
        proposal = self.env["ps.mfg.proposal"].create(
            {
                "name": "Cancel Test",
                "component_request_ids": [Command.set([req.id])],
                "source_location_id": self.source_loc.id,
            }
        )
        proposal.action_approve()
        self.assertEqual(proposal.transfer_state, "waiting")
        proposal.picking_ids.action_cancel()
        self.assertEqual(proposal.transfer_state, "cancelled")
