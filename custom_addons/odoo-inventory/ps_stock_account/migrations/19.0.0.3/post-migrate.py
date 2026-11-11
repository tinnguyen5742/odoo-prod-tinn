import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api
    from odoo.modules.registry import Registry

    registry = Registry(cr.dbname)
    with registry.cursor() as env_cr:
        env = api.Environment(env_cr, 2, {})
        env['res.company']._ps_set_average_cost_method_defaults()
        _logger.info('ps_stock_account 19.0.0.3: set default cost_method to average on company and warehouse.')
        env_cr.commit()
