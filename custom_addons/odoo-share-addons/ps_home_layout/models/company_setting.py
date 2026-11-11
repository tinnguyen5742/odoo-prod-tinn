import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)

class ResCompany(models.Model):
    _inherit = 'res.company'

    theme_primary_color = fields.Char(
        string='Theme Primary Color',
        default='#7c7bad',
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    theme_primary_color = fields.Char(
        string="Theme Primary Color",
        related='company_id.theme_primary_color',
        readonly=False,
    )

    def set_values(self):
        super().set_values()
        for record in self:
            # Đảm bảo lấy đúng company_id đang được chọn cấu hình
            target_company = record.company_id or self.env.company
            if target_company and record.theme_primary_color:
                target_company.sudo().write({
                    'theme_primary_color': record.theme_primary_color
                })