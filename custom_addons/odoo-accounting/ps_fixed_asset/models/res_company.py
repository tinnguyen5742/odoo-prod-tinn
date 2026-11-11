from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    asset_code_prefix = fields.Char(string='Asset Code Prefix', default='TS')