"""Backfill per-unit resource cost on draft work order moves.

``ps.mfg.workorder.move.resource.unit_cost`` is new: actual/planned cost now
default to ``unit_cost x move_qty``. Approved moves keep their recorded cost;
draft moves get the unit cost of the matching work order resource.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ps_mfg_workorder_move_resource mr
           SET unit_cost = wr.unit_cost
          FROM ps_mfg_workorder_move m
          JOIN ps_mfg_workorder_resource wr ON wr.workorder_id = m.to_workorder_id
         WHERE mr.workorder_move_id = m.id
           AND m.state != 'approved'
           AND wr.resource_id = mr.resource_id
        """
    )
