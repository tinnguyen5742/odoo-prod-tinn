# -*- coding: utf-8 -*-
import logging
from . import models


_logger = logging.getLogger(__name__)


# Tự động đồng bộ các danh mục từ Acumatica API sau khi cài đặt module
def post_init_hook(env):
    for model_name, method_name in [
        ('ps.sale.order.type', 'sync_from_acumatica'),
        ('ps.sale.item.unit', 'sync_from_acumatica'),
        ('ps.sale.tax', 'sync_from_acumatica'),
        ('ps.sale.inventory', 'sync_from_acumatica'),
    ]:
        try:
            env[model_name].sync_from_acumatica()
        except Exception as e:
            _logger.warning('Không thể đồng bộ %s khi init module: %s', model_name, e)
