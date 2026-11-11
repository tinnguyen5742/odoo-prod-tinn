from odoo import fields, models


class Facing(models.Model):
    _inherit = 'property.facing'

    name = fields.Char(translate=True)
