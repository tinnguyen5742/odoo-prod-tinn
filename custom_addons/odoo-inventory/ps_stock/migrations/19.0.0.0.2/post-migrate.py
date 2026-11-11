def migrate(cr, version):
    """Backfill x_product_code on historical products that predate the field.

    Runs in its own cursor so the backfill commits independently of the module
    upgrade transaction, even if subsequent steps of the upgrade fail.
    """
    from odoo import api
    from odoo.modules.registry import Registry

    registry = Registry(cr.dbname)
    with registry.cursor() as env_cr:
        env = api.Environment(env_cr, 2, {})
        env['product.product'].sudo()._action_assign_missing_product_codes()
        env_cr.commit()
