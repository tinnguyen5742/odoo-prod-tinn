from odoo import models, fields


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    x_property_cost_method = fields.Selection(
        string="Costing Method",
        selection=[
            ('average', "Average Cost (AVCO)"),
            ('standard', "Standard Price"),
        ],
        company_dependent=True, copy=True,
        default='average',
        help="""Average Cost (AVCO): The products are valued at weighted average cost.
        Standard Price: The products are valued at their standard cost defined on the product.
        """,
        tracking=True,
    )

