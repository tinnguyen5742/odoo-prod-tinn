from odoo import fields, models


class AreaMeasurement(models.Model):
    _inherit = 'property.area.measurement'

    length = fields.Float(string='Length(m)')
    width = fields.Float(string='Width(m)')
    height = fields.Float(string='Height(m)')
    carpet_area = fields.Float(string='Carpet Area(m²)')
