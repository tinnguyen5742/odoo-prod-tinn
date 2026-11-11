"""Rename ps.mfg.production.workorder -> ps.mfg.workorder preserving data.

HEAD (19.0.0.0) defined the work-order model as ``ps.mfg.production.workorder``
(table ``ps_mfg_production_workorder``). It was renamed to ``ps.mfg.workorder``
(table ``ps_mfg_workorder``, new required ``code`` field). Without this script
the upgrader tries to drop the vanished model while
``ps.mfg.production.component.workorder_id`` still references its rows, which
aborts the upgrade with "Another model is using the record you are trying to
delete".
"""


def migrate(cr, version):
    cr.execute(
        "SELECT to_regclass('public.ps_mfg_production_workorder'), "
        "to_regclass('public.ps_mfg_workorder')"
    )
    old_table, new_table = cr.fetchone()

    if old_table and not new_table:
        cr.execute("ALTER TABLE ps_mfg_production_workorder RENAME TO ps_mfg_workorder")

    cr.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'ps_mfg_workorder' AND column_name = 'code'"
    )
    if cr.fetchone() is None:
        cr.execute("ALTER TABLE ps_mfg_workorder ADD COLUMN code VARCHAR")
        # Backfill unique-per-production codes from the operation name.
        cr.execute(
            """
            UPDATE ps_mfg_workorder wo SET code = sub.code FROM (
                SELECT id,
                       name || CASE WHEN rn > 1 THEN '-' || rn ELSE '' END AS code
                FROM (
                    SELECT id, COALESCE(NULLIF(TRIM(name), ''), 'OP') AS name,
                           ROW_NUMBER() OVER (
                               PARTITION BY production_id,
                                            COALESCE(NULLIF(TRIM(name), ''), 'OP')
                               ORDER BY id
                           ) AS rn
                    FROM ps_mfg_workorder
                ) s
            ) sub WHERE sub.id = wo.id
            """
        )
    else:
        # Fill any NULL codes left by a previously aborted upgrade.
        cr.execute(
            """
            UPDATE ps_mfg_workorder wo SET code = sub.code FROM (
                SELECT id,
                       name || CASE WHEN rn > 1 THEN '-' || rn ELSE '' END AS code
                FROM (
                    SELECT id, COALESCE(NULLIF(TRIM(name), ''), 'OP') AS name,
                           ROW_NUMBER() OVER (
                               PARTITION BY production_id,
                                            COALESCE(NULLIF(TRIM(name), ''), 'OP')
                               ORDER BY id
                           ) AS rn
                    FROM ps_mfg_workorder
                    WHERE code IS NULL
                ) s
            ) sub WHERE sub.id = wo.id
            """
        )

    # Re-point model metadata at the new name so the registry reuses the
    # existing ir.model row instead of dropping the old one.
    cr.execute(
        "UPDATE ir_model SET model = 'ps.mfg.workorder' "
        "WHERE model = 'ps.mfg.production.workorder'"
    )
    cr.execute(
        "UPDATE ir_model_fields SET model = 'ps.mfg.workorder' "
        "WHERE model = 'ps.mfg.production.workorder'"
    )
    cr.execute(
        "UPDATE ir_model_fields SET relation = 'ps.mfg.workorder' "
        "WHERE relation = 'ps.mfg.production.workorder'"
    )
    cr.execute(
        "UPDATE ir_model_data SET name = 'model_ps_mfg_workorder' "
        "WHERE module = 'ps_mfg' AND name = 'model_ps_mfg_production_workorder'"
    )
    cr.execute(
        "UPDATE ir_model_data "
        "SET name = REPLACE(name, 'field_ps_mfg_production_workorder__', "
        "'field_ps_mfg_workorder__') "
        "WHERE module = 'ps_mfg' "
        "AND name LIKE 'field_ps_mfg_production_workorder__%%'"
    )
