from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _match_all_variant_values(self, product_template_attribute_value_ids):
        # Ported from core mrp (mrp/models/product.py) so ps_mfg works
        # standalone as an mrp replacement without depending on mrp.
        # Checks that all variant values are in the product. If multiple
        # values are encoded for the same attribute line, only one of them
        # has to be found on the variant.
        self.ensure_one()
        return len(
            self.product_template_attribute_value_ids
            & product_template_attribute_value_ids
        ) == len(product_template_attribute_value_ids.attribute_id)
