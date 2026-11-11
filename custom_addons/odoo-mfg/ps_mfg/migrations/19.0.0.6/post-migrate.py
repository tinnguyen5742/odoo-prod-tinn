"""Backfill finish lines and picking M2M from the old header columns."""


def migrate(cr, version):
    cr.execute("SELECT to_regclass('public.ps_mfg_proposal_finish')")
    if not cr.fetchone()[0]:
        return
    cr.execute("SELECT to_regclass('public.ps_mfg_proposal_finish_line')")
    if not cr.fetchone()[0]:
        return

    cr.execute(
        """
        CREATE TABLE IF NOT EXISTS ps_mfg_proposal_finish_picking_rel (
            proposal_id INTEGER NOT NULL REFERENCES ps_mfg_proposal_finish(id) ON DELETE CASCADE,
            picking_id INTEGER NOT NULL REFERENCES stock_picking(id) ON DELETE CASCADE,
            PRIMARY KEY (proposal_id, picking_id)
        )
        """
    )
    cr.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'ps_mfg_proposal_finish' AND column_name = 'picking_id'"
    )
    if cr.fetchone():
        cr.execute(
            """
            INSERT INTO ps_mfg_proposal_finish_picking_rel (proposal_id, picking_id)
            SELECT id, picking_id FROM ps_mfg_proposal_finish
            WHERE picking_id IS NOT NULL
            ON CONFLICT DO NOTHING
            """
        )

    cr.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'ps_mfg_proposal_finish' AND column_name = 'production_id'"
    )
    if not cr.fetchone():
        return

    cr.execute(
        """
        INSERT INTO ps_mfg_proposal_finish_line (
            proposal_id, production_id, workorder_id, product_id, product_uom_id,
            finish_qty, dst_location_id, x_product_code, sequence, company_id,
            create_uid, create_date, write_uid, write_date
        )
        SELECT
            f.id,
            f.production_id,
            (
                SELECT w.id FROM ps_mfg_workorder w
                WHERE w.production_id = f.production_id
                ORDER BY w.sequence DESC, w.id DESC
                LIMIT 1
            ),
            COALESCE(f.product_id, p.product_id),
            COALESCE(f.product_uom_id, p.product_uom_id),
            COALESCE(NULLIF(f.finish_qty, 0), 0.001),
            COALESCE(f.dst_location_id, (
                SELECT sl.id FROM stock_location sl
                WHERE sl.usage = 'internal'
                LIMIT 1
            )),
            pp.x_product_code,
            10,
            f.company_id,
            f.create_uid,
            f.create_date,
            f.write_uid,
            NOW() AT TIME ZONE 'UTC'
        FROM ps_mfg_proposal_finish f
        LEFT JOIN ps_mfg_production p ON p.id = f.production_id
        LEFT JOIN product_product pp ON pp.id = COALESCE(f.product_id, p.product_id)
        WHERE f.production_id IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM ps_mfg_workorder w WHERE w.production_id = f.production_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM ps_mfg_proposal_finish_line l WHERE l.proposal_id = f.id
          )
        """
    )
