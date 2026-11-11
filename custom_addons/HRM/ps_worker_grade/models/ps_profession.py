# Worker profession catalog
from odoo import fields, models


class PsWorkerProfession(models.Model):
    # Danh mục ngành nghề
    _name = 'ps.worker.profession'
    _description = 'Worker Profession'
    _rec_name = 'x_name'
    _order = 'x_sequence, x_name'

    x_code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        help='Unique profession code, e.g. BLOW',
    )
    x_name = fields.Char(
        string='Profession Name',
        required=True,
        help='Profession name',
    )
    x_sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    x_active = fields.Boolean(
        string='Active',
        default=True,
    )
    x_note = fields.Text(
        string='Notes',
    )

    _profession_code_unique = models.Constraint(
        "UNIQUE(x_code)",
        "Profession code already exists!",
    )
