import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Backfill x_product_code on products that still lack one.

    Handles DBs that never ran the 19.0.0.0.2 backfill (fresh install of an
    older version then upgrade straight to 19.0.0.0.3) as well as DBs that
    have new products created without a code in the meantime.

    Runs in its own cursor so the backfill commits independently of the
    module upgrade transaction.
    """
    from odoo import api
    from odoo.modules.registry import Registry

    registry = Registry(cr.dbname)
    with registry.cursor() as env_cr:
        env = api.Environment(env_cr, 2, {})
        assigned = env['product.product'].sudo()._action_assign_missing_product_codes()
        _logger.info('ps_stock 19.0.0.0.3 migration: backfilled x_product_code on %s product(s).', assigned)
        env_cr.commit()
