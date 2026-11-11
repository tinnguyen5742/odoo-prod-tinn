from odoo import api, models
from odoo.exceptions import ValidationError


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    @api.constrains("sale_line_id", "company_id", "product_id")
    def _check_tracking_sale_line(self):
        for production in self:
            line = production.sale_line_id
            if line and (line.company_id != production.company_id or line.product_id != production.product_id):
                raise ValidationError("Dòng SO của lệnh sản xuất phải cùng công ty và cùng sản phẩm.")
