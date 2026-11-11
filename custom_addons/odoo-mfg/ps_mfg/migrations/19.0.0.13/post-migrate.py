"""Move the operation sequence past the codes created by pre-migrate.

The 19.0.0.12 pre-migrate numbers the extracted operations ``OP001``, ``OP002``... The
``ps.mfg.operation`` sequence is only loaded afterwards (data file), so it
starts at 1; bump ``number_next`` to the highest ``OPnnn`` + 1.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    cr.execute(
        """
        SELECT COALESCE(MAX(substring(code FROM '^OP([0-9]+)$')::int), 0)
          FROM ps_mfg_operation
        """
    )
    highest = cr.fetchone()[0]
    if not highest:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    sequence = env.ref("ps_mfg.seq_ps_mfg_operation", raise_if_not_found=False)
    if sequence and sequence.number_next_actual <= highest:
        sequence.number_next = highest + 1
