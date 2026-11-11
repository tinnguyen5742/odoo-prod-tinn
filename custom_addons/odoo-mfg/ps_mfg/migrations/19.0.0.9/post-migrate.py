"""Backfill cumulative operation costing.

- ``ps.mfg.workorder`` totals now read resource cost from shifts, so stored
  totals must be recomputed.
- ``transferred_in_unit_cost`` of existing shifts is taken from the current
  unit cost of the upstream work order. Work orders are processed in routing
  order so the upstream cost is final before downstream shifts read it.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Move = env["ps.mfg.workorder.move"]
    workorders = env["ps.mfg.workorder"].search([], order="production_id, sequence, id")
    for workorder in workorders:
        inbound = Move.search(
            [("to_workorder_id", "=", workorder.id), ("from_workorder_id", "!=", False)]
        )
        for move in inbound:
            unit_cost = move.from_workorder_id.unit_cost or 0.0
            # SQL để không vướng khóa write() của ca đã approved
            cr.execute(
                "UPDATE ps_mfg_workorder_move SET transferred_in_unit_cost = %s WHERE id = %s",
                (unit_cost, move.id),
            )
        inbound.invalidate_recordset(["transferred_in_unit_cost"])
        _recompute(env, inbound, ["transferred_in_cost", "total_cost", "unit_cost"])
        _recompute(
            env,
            workorder,
            [
                "total_qty",
                "material_amount",
                "resource_amount",
                "total_amount",
                "stage_unit_cost",
                "transferred_in_cost",
                "total_cost",
                "unit_cost",
            ],
        )


def _recompute(env, records, fnames):
    if not records:
        return
    for fname in fnames:
        env.add_to_compute(records._fields[fname], records)
    records._recompute_recordset(fnames)
    records.flush_recordset()
