from odoo import fields, models


class BookingWindow(models.TransientModel):
    _inherit = 'booking.window'

    total_square_foot = fields.Float(string='Total Size(m²)')


class PropertyLine(models.TransientModel):
    _inherit = 'property.line'

    total_square_foot = fields.Float(string='Total Size(m²)')
