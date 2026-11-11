from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tinhthanhpho_api_key = fields.Char(
        string='Tinhthanhpho API Key',
        config_parameter='ps_vn_address.tinhthanhpho_api_key',
        help='API key used to convert addresses according to the administrative merger decision.',
    )