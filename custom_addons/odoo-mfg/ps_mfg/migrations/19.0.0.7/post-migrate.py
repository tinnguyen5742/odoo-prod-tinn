"""Mark existing component requests as legacy_transfer.

Existing requests that already had proposals linked to pickings before multi-transfer
was implemented have no move-level component_request_line_id links.
Setting legacy_transfer = TRUE ensures they do not reappear in proposal domains
and preserve their existing behavior.
"""


def migrate(cr, version):
    cr.execute("SELECT to_regclass('public.ps_mfg_component_request')")
    if not cr.fetchone()[0]:
        return

    # Check if table has legacy_transfer column
    cr.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'ps_mfg_component_request' AND column_name = 'legacy_transfer'"
    )
    if cr.fetchone():
        cr.execute("""
            UPDATE ps_mfg_component_request req
            SET legacy_transfer = TRUE
            WHERE EXISTS (
                SELECT 1 FROM ps_mfg_proposal_request_rel rel
                JOIN ps_mfg_proposal_picking_rel prel ON prel.proposal_id = rel.proposal_id
                WHERE rel.request_id = req.id
            )
        """)
