from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    asset_code_prefix = fields.Char(
        related='company_id.asset_code_prefix',
        readonly=False,
        string='Asset Code Prefix'
    )

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        
        for record in self:
            prefix = record.asset_code_prefix or ''
            company_id = record.company_id.id

            # 1. Tìm xem công ty hiện tại đã có bộ đếm riêng chưa
            sequence = self.env['ir.sequence'].sudo().search([
                ('code', '=', 'ps.asset.sequence'),
                ('company_id', '=', company_id)
            ], limit=1)

            if sequence:
                # 2. Nếu đã có, cập nhật
                sequence.sudo().write({
                    'prefix': prefix,
                    'padding': 4
                })
            else:
                # 3. Nếu chưa có, tự tạo mới cho công ty
                self.env['ir.sequence'].sudo().create({
                    'name': f'Fixed Asset Sequence ({record.company_id.name})',
                    'code': 'ps.asset.sequence',
                    'prefix': prefix,
                    'padding': 4,
                    'company_id': company_id,
                    'implementation': 'standard'
                })