from odoo import models, fields
# Mục tiêu cá nhân

class CrmTeamMember(models.Model):
    _inherit = 'crm.team.member'

    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    x_personal_goal = fields.Monetary(
        string='Personal Goal',
        digits=(16, 0),
        currency_field='currency_id',
        help='Monthly personal goal amount for this sales team member.'
    )
