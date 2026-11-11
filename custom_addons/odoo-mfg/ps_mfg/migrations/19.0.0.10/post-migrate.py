"""Recompute ``stock.move.reference`` of existing shift consumption moves.

Before this version the consumption moves (no picking) had an empty
reference; they now show the shift code ``MO/WO code/shift``.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    moves = env["stock.move"].search([("ps_workorder_move_id", "!=", False)])
    if not moves:
        return
    env.add_to_compute(moves._fields["reference"], moves)
    moves._recompute_recordset(["reference"])
    moves.flush_recordset()
