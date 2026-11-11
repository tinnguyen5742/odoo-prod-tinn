from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    cost_method = fields.Selection(default='average')

    @api.model
    def _ps_set_average_cost_method_defaults(self):
        """Apply AVCO as default on existing companies, warehouses, and category ir.default."""
        companies = self.search([('cost_method', '!=', 'average')])
        if companies:
            companies.write({'cost_method': 'average'})

        IrDefault = self.env['ir.default'].sudo()
        IrDefault.set('product.category', 'property_cost_method', 'average')
        for company in self.search([]):
            IrDefault.set(
                'product.category',
                'property_cost_method',
                'average',
                company_id=company.id,
            )

        warehouses = self.env['stock.warehouse'].search([])
        for warehouse in warehouses:
            warehouse = warehouse.with_company(warehouse.company_id)
            if warehouse.x_property_cost_method != 'average':
                warehouse.x_property_cost_method = 'average'
