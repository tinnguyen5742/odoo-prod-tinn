"""Backfill is_from_bom on existing component request lines.

A line is considered generated from the BoM when its product belongs to the
BoM lines of the request's Manufacturing Order BoM.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE ps_mfg_component_request_line line
        SET is_from_bom = TRUE
        FROM ps_mfg_component_request req
        JOIN ps_mfg_production mo ON mo.id = req.production_id
        WHERE line.request_id = req.id
          AND mo.bom_id IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM ps_mfg_bom_line bl
              WHERE bl.bom_id = mo.bom_id
                AND bl.product_id = line.product_id
          )
    """)
