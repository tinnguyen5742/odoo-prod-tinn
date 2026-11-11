from odoo import models, fields, api
from odoo.addons.mail.tools.discuss import Store
# Tạo CRM channel từ cơ hội

class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    x_is_crm_channel = fields.Boolean(
        string='CRM Channel',
        compute='_compute_x_is_crm_channel',
    )

    def _compute_x_is_crm_channel(self):
        leads = self.env['crm.lead'].sudo().search([
            ('x_discuss_channel_id', 'in', self.ids)
        ])
        crm_channel_ids = set(leads.mapped('x_discuss_channel_id').ids)
        for channel in self:
            channel.x_is_crm_channel = channel.id in crm_channel_ids

    def _to_store_defaults(self, target):
        res = super()._to_store_defaults(target)
        res.append('x_is_crm_channel')
        return res

    def _sync_field_names(self):
        res = super()._sync_field_names()
        res[None].append('x_is_crm_channel')
        return res

    def action_open_linked_crm(self):
        self.ensure_one()
        lead = self.env['crm.lead'].sudo().search(
            [('x_discuss_channel_id', '=', self.id)], limit=1)
        if lead:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'crm.lead',
                'res_id': lead.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
            }
        return {'type': 'ir.actions.act_window_close'}
