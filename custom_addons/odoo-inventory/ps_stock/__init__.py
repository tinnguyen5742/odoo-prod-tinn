from . import models

import logging

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Enforce only group-based settings at install time.
_REQUIRED_INSTALL_SETTINGS = {
    'group_stock_tracking_lot': True,
    'group_stock_reception_report': True,
    'group_product_variant': True,
    'group_uom': True,
    'group_stock_production_lot': True,
    'group_stock_tracking_owner': True,
    'group_stock_multi_locations': True,
}


def post_init_hook(env):
    settings_model = env['res.config.settings'].sudo()

    missing_fields = [fname for fname in _REQUIRED_INSTALL_SETTINGS if fname not in settings_model._fields]

    if missing_fields:
        raise UserError(
            _('Cannot initialize PS Inventory required stock settings.\n')
            + _('Missing settings fields: %s') % ', '.join(sorted(missing_fields))
        )

    settings = settings_model.create({})
    updates = {
        field_name: True
        for field_name, target_value in _REQUIRED_INSTALL_SETTINGS.items()
        if target_value and not bool(settings[field_name])
    }

    if not updates:
        _logger.info('ps_inventory post-init: required stock settings are already enabled.')
    else:
        settings.write(updates)
        settings.set_values()
        _logger.info(
            'ps_inventory post-init: enabled required stock settings: %s',
            ', '.join(sorted(updates)),
        )

    _backfill_missing_product_codes(env)


def _backfill_missing_product_codes(env):
    """Assign x_product_code to pre-existing products after ps_stock install."""
    try:
        assigned = env['product.product'].sudo()._action_assign_missing_product_codes()
        _logger.info('ps_inventory post-init: backfilled x_product_code on %s product(s).', assigned)
    except Exception as exc:
        _logger.exception('ps_inventory post-init: failed to backfill x_product_code: %s', exc)
