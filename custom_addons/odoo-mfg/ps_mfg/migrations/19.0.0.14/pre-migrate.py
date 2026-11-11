"""Align approval-document states with the ``ps_approval`` vocabulary.

``ps_approval`` (``ps.approval.mixin.approval_state``) names the "sent for
approval" step ``pending``. ``ps_mfg`` predates it and used ``submitted`` on
the shift, transfer proposal and finished-goods receipt, and ``confirmed`` on
the component request. Rename the stored keys so the selection change does not
hit rows with a removed value (Odoo refuses to drop a selection value still in
use). Runs before the registry loads; idempotent.
"""

_RENAMES = (
    ("ps_mfg_workorder_move", "submitted"),
    ("ps_mfg_proposal", "submitted"),
    ("ps_mfg_proposal_finish", "submitted"),
    ("ps_mfg_component_request", "confirmed"),
)


def migrate(cr, version):
    for table, old_state in _RENAMES:
        cr.execute("SELECT to_regclass(%s)", (f"public.{table}",))
        if not cr.fetchone()[0]:
            continue
        cr.execute(
            f"UPDATE {table} SET state = 'pending' WHERE state = %s",  # noqa: S608
            (old_state,),
        )
