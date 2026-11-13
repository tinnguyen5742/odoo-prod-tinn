from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    service_area_id = fields.Many2one('field.service.area', string='Khu vực phụ trách kỹ thuật')