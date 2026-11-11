"""Fix draft work order move resource lines saved without ``unit_cost``.

``unit_cost`` was a plain field only set by onchange, so saves from a client
that did not send it left NULL (and ``planned_cost`` 0). It is now computed
from the target work order resource. Backfill draft moves; ``actual_cost`` is
left alone (it may have been edited by hand) and approved moves are untouched.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ps_mfg_workorder_move_resource mr
           SET unit_cost = wr.unit_cost,
               planned_cost = wr.unit_cost * COALESCE(m.move_qty, 0)
          FROM ps_mfg_workorder_move m
          JOIN ps_mfg_workorder_resource wr ON wr.workorder_id = m.to_workorder_id
         WHERE mr.workorder_move_id = m.id
           AND m.state != 'approved'
           AND wr.resource_id = mr.resource_id
        """
    )
