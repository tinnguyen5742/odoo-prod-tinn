from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.depends_context('company', 'force_cost_method')
    @api.depends('categ_id.property_cost_method')
    def _compute_cost_method(self):
        forced = self.env.context.get('force_cost_method')
        if forced:
            self.cost_method = forced
            return
        super()._compute_cost_method()
