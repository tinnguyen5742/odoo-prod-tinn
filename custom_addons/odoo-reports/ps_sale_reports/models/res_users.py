from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    ps_sales_code = fields.Char("Mã NV Sales", copy=False)
