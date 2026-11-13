from odoo import models, fields

class FieldServiceArea(models.Model):
    _name = 'field.service.area'
    _description = 'Khu vực dịch vụ'

    name = fields.Char(string='Tên khu vực', required=True)
    code = fields.Char(string='Mã khu vực')