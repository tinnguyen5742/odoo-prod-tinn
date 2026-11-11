from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from .common import (
    create_received_component_request,
    get_component_source_location,
    operation_line,
)


@tagged("post_install", "-at_install")
class TestMfgWip(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.finished = cls.env["product.product"].create(
            {
                "name": "WIP Finished",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.workcenter = cls.env["ps.mfg.work.center"].create(
            {
                "name": "WC WIP Test",
                "code": "WC-WIP-T",
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
                "mo_prefix": "MO/W/",
                "comp_request_prefix": "CR/W/",
                "receipt_request_prefix": "RC/W/",
            }
        )
        cls.production = cls.env["ps.mfg.production"].create(
            {
                "product_id": cls.finished.id,
                "product_qty": 20000.0,
                "workcenter_id": cls.workcenter.id,
            }
        )
        cls.account = cls.env["account.account"].search([], limit=1)

    def test_wip_value_formula(self):
        wip = self.env["ps.mfg.wip"].create(
            {
                "account_id": self.account.id,
                "period_date": "2021-12-01",
                "date": "2021-12-31",
                "beginning_value": 15376794.556,
                "total_debit": 56715284.503,
                "total_credit": 58742924.942,
                "allocated_value": 3470930.645,
            }
        )
        self.assertAlmostEqual(wip.wip_value, 9878223.472, places=3)
        self.assertTrue(wip.code and wip.code != "New")

    def test_line_unit_cost_actual(self):
        wip = self.env["ps.mfg.wip"].create(
            {
                "account_id": self.account.id,
                "period_date": "2021-12-01",
                "date": "2021-12-31",
            }
        )
        line = self.env["ps.mfg.wip.line"].create(
            {
                "wip_id": wip.id,
                "production_id": self.production.id,
                "discrete_qty": 20000.0,
                "receipt_qty": 10992.0,
                "receipt_tran_cost": 65973.775,
                "estimated_cost": 6.002,
                "in_progress_cost": 5424.890,
            }
        )
        self.assertAlmostEqual(line.unit_cost_actual, 6495.5117, places=3)
        self.assertEqual(line.product_id, self.finished)

    def test_complete_blocks_negative_wip(self):
        wip = self.env["ps.mfg.wip"].create(
            {
                "account_id": self.account.id,
                "period_date": "2021-11-01",
                "date": "2021-11-30",
                "beginning_value": 0.0,
                "total_debit": 0.0,
                "total_credit": 100.0,
                "allocated_value": 0.0,
            }
        )
        with self.assertRaises(Exception):
            wip.action_complete()

    def test_period_unique(self):
        self.env["ps.mfg.wip"].create(
            {
                "account_id": self.account.id,
                "period_date": "2021-10-01",
                "date": "2021-10-31",
            }
        )
        with self.assertRaises(IntegrityError):
            self.env["ps.mfg.wip"].create(
                {
                    "account_id": self.account.id,
                    "period_date": "2021-10-01",
                    "date": "2021-10-31",
                }
            )

    def _make_finished_proposal(
        self,
        mo_qty,
        finish_qty=None,
        comp_qty=2.0,
        comp_price=10.0,
        transaction_date="2022-01-15",
    ):
        finish_qty = mo_qty if finish_qty is None else finish_qty
        product = self.env["product.product"].create(
            {
                "name": "WIP Fetch Product",
                "type": "consu",
                "uom_id": self.uom_unit.id,
            }
        )
        component = self.env["product.product"].create(
            {
                "name": "WIP Fetch Component",
                "type": "consu",
                "uom_id": self.uom_unit.id,
                "standard_price": comp_price,
            }
        )
        bom = self.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "product_qty": 1.0,
                "product_uom_id": self.uom_unit.id,
                "operation_ids": [operation_line(self.env, "Op 1", 1)],
            }
        )
        operation = bom.operation_ids[0]
        self.env["ps.mfg.bom.line"].create(
            {
                "bom_id": bom.id,
                "product_id": component.id,
                "quantity": comp_qty,
                "product_uom_id": self.uom_unit.id,
                "operation_id": operation.id,
            }
        )
        production = self.env["ps.mfg.production"].create(
            {
                "product_id": product.id,
                "product_qty": mo_qty,
                "workcenter_id": self.workcenter.id,
                "bom_id": bom.id,
            }
        )
        production.action_confirm()
        production.action_start()
        create_received_component_request(
            self.env,
            production,
            mo_qty,
            get_component_source_location(self.env, self.workcenter.location_id),
        )
        workorder = production.workorder_ids.sorted("sequence")[0]
        self.env["ps.mfg.workorder.move"].create(
            {
                "production_id": production.id,
                "to_workorder_id": workorder.id,
                "move_qty": mo_qty,
            }
        ).action_approve()
        location = self.env["stock.location"].search(
            [
                ("usage", "=", "internal"),
                ("company_id", "in", (False, self.env.company.id)),
            ],
            limit=1,
        )
        return self.env["ps.mfg.proposal.finish"].create(
            {
                "dst_location_id": location.id,
                "transaction_date": transaction_date,
                "state": "approved",
                "line_ids": [
                    Command.create(
                        {
                            "production_id": production.id,
                            "workorder_id": workorder.id,
                            "finish_qty": finish_qty,
                            "dst_location_id": location.id,
                        }
                    )
                ],
            }
        )

    def test_fetch_pulls_approved_proposal(self):
        proposal = self._make_finished_proposal(100.0)
        wip = self.env["ps.mfg.wip"].create(
            {
                "account_id": self.account.id,
                "period_date": "2022-01-01",
                "date": "2022-01-31",
            }
        )
        wip.action_fetch_finished_mos()
        self.assertEqual(len(wip.line_ids), 1)
        line = wip.line_ids[0]
        self.assertEqual(line.production_id, proposal.line_ids.production_id)
        self.assertEqual(line.discrete_qty, 100.0)
        self.assertEqual(line.receipt_qty, 100.0)
        self.assertEqual(line.description, proposal.code)
        # 100 MO x 2 comp x 10.0 price; fully received -> no allocation.
        self.assertAlmostEqual(line.receipt_tran_cost, 2000.0, places=2)
        self.assertAlmostEqual(line.estimated_cost, 20.0, places=2)
        self.assertAlmostEqual(line.in_progress_cost, 0.0, places=2)

    def test_fetch_excludes_production_on_other_wip_and_refills(self):
        proposal_a = self._make_finished_proposal(100.0, transaction_date="2022-01-10")
        wip1 = self.env["ps.mfg.wip"].create(
            {
                "account_id": self.account.id,
                "period_date": "2022-01-01",
                "date": "2022-01-31",
            }
        )
        wip1.action_fetch_finished_mos()
        self.assertEqual(wip1.line_ids.production_id, proposal_a.line_ids.production_id)
        proposal_b = self._make_finished_proposal(50.0, transaction_date="2022-02-05")
        wip2 = self.env["ps.mfg.wip"].create(
            {
                "account_id": self.account.id,
                "period_date": "2022-02-01",
                "date": "2022-02-28",
            }
        )
        # Manual line with an already-closed production is wiped by refill.
        self.env["ps.mfg.wip.line"].create(
            {
                "wip_id": wip2.id,
                "production_id": proposal_a.line_ids.production_id.id,
                "receipt_qty": 10.0,
            }
        )
        wip2.action_fetch_finished_mos()
        self.assertEqual(len(wip2.line_ids), 1)
        self.assertEqual(wip2.line_ids.production_id, proposal_b.line_ids.production_id)

    def test_fetch_cutoff_includes_backlog_excludes_future(self):
        old = self._make_finished_proposal(100.0, transaction_date="2021-12-20")
        self._make_finished_proposal(100.0, transaction_date="2022-03-10")
        wip = self.env["ps.mfg.wip"].create(
            {
                "account_id": self.account.id,
                "period_date": "2022-02-01",
                "date": "2022-02-28",
            }
        )
        wip.action_fetch_finished_mos()
        self.assertEqual(len(wip.line_ids), 1)
        self.assertEqual(wip.line_ids.production_id, old.line_ids.production_id)

    def test_fetch_fills_costs_and_allocates_single_line(self):
        self._make_finished_proposal(
            mo_qty=200.0, finish_qty=100.0, transaction_date="2022-04-10"
        )
        wip = self.env["ps.mfg.wip"].create(
            {
                "account_id": self.account.id,
                "period_date": "2022-04-01",
                "date": "2022-04-30",
                "beginning_value": 5000.0,
            }
        )
        wip.action_fetch_finished_mos()
        line = wip.line_ids[0]
        self.assertAlmostEqual(line.receipt_tran_cost, 4000.0, places=2)
        self.assertAlmostEqual(line.estimated_cost, 20.0, places=2)
        self.assertAlmostEqual(line.in_progress_cost, 5000.0, places=2)
        self.assertAlmostEqual(line.unit_cost_actual, 90.0, places=2)

    def test_allocate_distributes_by_remaining_weight(self):
        proposal_a = self._make_finished_proposal(
            mo_qty=101.0, finish_qty=100.0, transaction_date="2022-05-10"
        )
        proposal_b = self._make_finished_proposal(
            mo_qty=102.0, finish_qty=100.0, transaction_date="2022-05-11"
        )
        wip = self.env["ps.mfg.wip"].create(
            {
                "account_id": self.account.id,
                "period_date": "2022-05-01",
                "date": "2022-05-31",
                "beginning_value": 100.0,
            }
        )
        wip.action_fetch_finished_mos()
        by_production = {l.production_id.id: l for l in wip.line_ids}
        line_a = by_production[proposal_a.line_ids.production_id.id]
        line_b = by_production[proposal_b.line_ids.production_id.id]
        # Weights 1x20=20 vs 2x20=40 -> 33.33 / 66.67.
        self.assertAlmostEqual(line_a.in_progress_cost, 33.33, places=2)
        self.assertAlmostEqual(line_b.in_progress_cost, 66.67, places=2)
        self.assertAlmostEqual(
            line_a.in_progress_cost + line_b.in_progress_cost, 100.0, places=2
        )
        # Re-allocate after header edit keeps receipt/estimated, rewrites split.
        line_a.receipt_tran_cost = 999.0
        wip.beginning_value = 200.0
        wip.action_allocate_in_progress()
        self.assertAlmostEqual(line_a.receipt_tran_cost, 999.0, places=2)
        self.assertAlmostEqual(line_a.in_progress_cost, 66.67, places=2)
        self.assertAlmostEqual(line_b.in_progress_cost, 133.33, places=2)

    def test_allocate_blocked_when_complete(self):
        wip = self.env["ps.mfg.wip"].create(
            {
                "account_id": self.account.id,
                "period_date": "2022-06-01",
                "date": "2022-06-30",
            }
        )
        wip.action_complete()
        with self.assertRaises(UserError):
            wip.action_allocate_in_progress()

    def test_fetch_blocked_when_complete(self):
        wip = self.env["ps.mfg.wip"].create(
            {
                "account_id": self.account.id,
                "period_date": "2022-03-01",
                "date": "2022-03-31",
            }
        )
        wip.action_complete()
        with self.assertRaises(UserError):
            wip.action_fetch_finished_mos()

    def test_onchange_period_normalizes_to_first(self):
        wip = self.env["ps.mfg.wip"].new(
            {
                "account_id": self.account.id,
                "period_date": "2022-03-15",
                "date": "2022-03-31",
            }
        )
        wip._onchange_period_date()
        self.assertEqual(wip.period_date.strftime("%Y-%m-%d"), "2022-03-01")
