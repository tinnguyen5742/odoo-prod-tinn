"""Extract per-BoM routings into the shared ``ps.mfg.operation`` master.

* One operation per distinct ``(name, company_id)`` of ``ps_mfg_routing``,
  code ``OP001``, ``OP002``... per company.
* ``ps_mfg_routing.operation_id`` is backfilled; ``name`` stays as the stored
  related column.
* Resources move to the operation: those of the representative routing
  (lowest id among routings having resources) are kept, the others are
  deleted. A warning lists the operations whose BoMs had different resource
  sets. Existing work orders keep their own snapshot, so they are unaffected.
* Old FK ``ps_mfg_routing_resource.routing_id`` and the
  ``UNIQUE(bom_id, name)`` constraint are dropped.
"""

import logging

_logger = logging.getLogger(__name__)


def _column_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    cr.execute("SELECT to_regclass('public.ps_mfg_routing')")
    if not cr.fetchone()[0]:
        return

    cr.execute(
        """
        CREATE TABLE IF NOT EXISTS ps_mfg_operation (
            id SERIAL PRIMARY KEY,
            code VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            company_id INTEGER,
            enabled BOOLEAN DEFAULT TRUE,
            create_uid INTEGER,
            create_date TIMESTAMP WITHOUT TIME ZONE,
            write_uid INTEGER,
            write_date TIMESTAMP WITHOUT TIME ZONE
        )
        """
    )

    # 1. One shared operation per (name, company).
    cr.execute(
        """
        INSERT INTO ps_mfg_operation
            (code, name, company_id, enabled,
             create_uid, create_date, write_uid, write_date)
        SELECT 'OP' || lpad(
                   (row_number() OVER (PARTITION BY g.company_id
                                       ORDER BY g.first_id))::text, 3, '0'),
               g.name, g.company_id, TRUE,
               1, now() AT TIME ZONE 'UTC', 1, now() AT TIME ZONE 'UTC'
          FROM (SELECT name, company_id, MIN(id) AS first_id
                  FROM ps_mfg_routing
                 GROUP BY name, company_id) g
         WHERE NOT EXISTS (
               SELECT 1 FROM ps_mfg_operation o
                WHERE o.name = g.name
                  AND o.company_id IS NOT DISTINCT FROM g.company_id)
        """
    )
    _logger.info("ps_mfg: created %s shared operations", cr.rowcount)

    # 2. Link BoM routings to their operation.
    if not _column_exists(cr, "ps_mfg_routing", "operation_id"):
        cr.execute("ALTER TABLE ps_mfg_routing ADD COLUMN operation_id INTEGER")
    cr.execute(
        """
        UPDATE ps_mfg_routing r
           SET operation_id = o.id
          FROM ps_mfg_operation o
         WHERE r.operation_id IS NULL
           AND o.name = r.name
           AND o.company_id IS NOT DISTINCT FROM r.company_id
        """
    )

    # 3. Move resources onto the operation.
    if not _column_exists(cr, "ps_mfg_routing_resource", "routing_id"):
        return
    if not _column_exists(cr, "ps_mfg_routing_resource", "operation_id"):
        cr.execute(
            "ALTER TABLE ps_mfg_routing_resource ADD COLUMN operation_id INTEGER"
        )

    # Warn when BoMs sharing an operation had different resource sets.
    cr.execute(
        """
        WITH sig AS (
            SELECT r.operation_id, r.id AS routing_id,
                   string_agg(rr.resource_id || ':' || COALESCE(rr.resource_cost, 0),
                              ',' ORDER BY rr.resource_id, rr.resource_cost) AS s
              FROM ps_mfg_routing r
              JOIN ps_mfg_routing_resource rr ON rr.routing_id = r.id
             GROUP BY r.operation_id, r.id
        )
        SELECT o.code, o.name, COUNT(DISTINCT sig.s)
          FROM sig JOIN ps_mfg_operation o ON o.id = sig.operation_id
         GROUP BY o.code, o.name
        HAVING COUNT(DISTINCT sig.s) > 1
        """
    )
    for code, name, count in cr.fetchall():
        _logger.warning(
            "ps_mfg: operation [%s] %s had %s different resource sets across "
            "BoMs; kept the one of the oldest routing. Please review its costs.",
            code,
            name,
            count,
        )

    cr.execute(
        """
        UPDATE ps_mfg_routing_resource rr
           SET operation_id = rep.operation_id
          FROM (SELECT r.operation_id, MIN(r.id) AS routing_id
                  FROM ps_mfg_routing r
                 WHERE EXISTS (SELECT 1 FROM ps_mfg_routing_resource x
                                WHERE x.routing_id = r.id)
                 GROUP BY r.operation_id) rep
         WHERE rr.routing_id = rep.routing_id
        """
    )
    cr.execute("DELETE FROM ps_mfg_routing_resource WHERE operation_id IS NULL")
    _logger.info("ps_mfg: dropped %s duplicated routing resources", cr.rowcount)
    cr.execute("ALTER TABLE ps_mfg_routing_resource DROP COLUMN routing_id")

    # 4. Replace UNIQUE(bom_id, name) by UNIQUE(bom_id, operation_id) (ORM).
    cr.execute(
        "ALTER TABLE ps_mfg_routing "
        "DROP CONSTRAINT IF EXISTS ps_mfg_routing_ps_mfg_routing_name_unique"
    )
    cr.execute(
        "DELETE FROM ir_model_constraint "
        "WHERE name = 'ps_mfg_routing_ps_mfg_routing_name_unique'"
    )
