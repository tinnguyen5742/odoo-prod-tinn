"""Copy single request/picking FKs onto Many2many rel tables.

ps.mfg.proposal.component_request_id and picking_id are replaced by
component_request_ids and picking_ids. Pre-migrate fills the rel tables
while the old columns still exist.
"""


def migrate(cr, version):
    cr.execute("SELECT to_regclass('public.ps_mfg_proposal')")
    if not cr.fetchone()[0]:
        return

    cr.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'ps_mfg_proposal' AND column_name = 'component_request_id'"
    )
    if cr.fetchone():
        cr.execute(
            """
            CREATE TABLE IF NOT EXISTS ps_mfg_proposal_request_rel (
                proposal_id INTEGER NOT NULL REFERENCES ps_mfg_proposal(id) ON DELETE CASCADE,
                request_id INTEGER NOT NULL REFERENCES ps_mfg_component_request(id) ON DELETE CASCADE,
                PRIMARY KEY (proposal_id, request_id)
            )
            """
        )
        cr.execute(
            """
            INSERT INTO ps_mfg_proposal_request_rel (proposal_id, request_id)
            SELECT id, component_request_id FROM ps_mfg_proposal
            WHERE component_request_id IS NOT NULL
            ON CONFLICT DO NOTHING
            """
        )

    cr.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'ps_mfg_proposal' AND column_name = 'picking_id'"
    )
    if cr.fetchone():
        cr.execute(
            """
            CREATE TABLE IF NOT EXISTS ps_mfg_proposal_picking_rel (
                proposal_id INTEGER NOT NULL REFERENCES ps_mfg_proposal(id) ON DELETE CASCADE,
                picking_id INTEGER NOT NULL REFERENCES stock_picking(id) ON DELETE CASCADE,
                PRIMARY KEY (proposal_id, picking_id)
            )
            """
        )
        cr.execute(
            """
            INSERT INTO ps_mfg_proposal_picking_rel (proposal_id, picking_id)
            SELECT id, picking_id FROM ps_mfg_proposal
            WHERE picking_id IS NOT NULL
            ON CONFLICT DO NOTHING
            """
        )
