from odoo import models, fields, api


class HrContract(models.Model):
    _inherit = 'crm.lead'

    x_source_project_id = fields.Many2one('project.project', string='Project', ondelete='set null')
    x_discuss_channel_id = fields.Many2one(
        'discuss.channel',
        string='Discuss Channel',
        readonly=True,
        copy=False,
    )
    x_crm_member_ids = fields.Many2many(
        'res.users',
        'crm_lead_project_member_rel',
        'lead_id',
        'user_id',
        string='CRM Member',
    )
    x_customer_group_ids = fields.Many2many(related='partner_id.x_customer_group_ids', readonly=True)
    x_customer_type = fields.Selection(related='partner_id.x_customer_type', readonly=True)

    def action_open_source_project(self):
        self.ensure_one()
        if self.x_source_project_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'project.project',
                'res_id': self.x_source_project_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def action_create_crm_channel(self):
        self.ensure_one()
        channel_name = f"Opportunity - {self.name}"
        channel = self.env['discuss.channel'].create({
            'name': channel_name,
            'channel_type': 'channel',
        })
        partner_ids = set()
        # Nhân viên phụ trách (Salesperson)
        if self.user_id:
            partner_ids.add(self.user_id.partner_id.id)
        # Thành viên trong Sales Team
        if self.team_id:
            for member in self.team_id.member_ids:
                if member.partner_id:
                    partner_ids.add(member.partner_id.id)
        # Người đang theo dõi cơ hội (trừ khách hàng chính)
        for follower in self.message_partner_ids:
            if follower != self.partner_id:
                partner_ids.add(follower.id)
        # Thành viên dự án
        for member in self.x_crm_member_ids:
            if member.partner_id:
                partner_ids.add(member.partner_id.id)
        # User hiện tại
        partner_ids.add(self.env.user.partner_id.id)
        partner_ids = list(partner_ids)
        # Thêm member vào channel
        channel.add_members(partner_ids)
        self.x_discuss_channel_id = channel.id
        self.message_subscribe(partner_ids=partner_ids)
        return {
            'type': 'ir.actions.act_url',
            'url': f'/odoo/discuss?active_id=discuss.channel_{channel.id}',
            'target': 'self',
        }

    def message_subscribe(self, partner_ids=None, subtype_ids=None, **kwargs):
        res = super().message_subscribe(partner_ids=partner_ids, subtype_ids=subtype_ids, **kwargs)
        for record in self:
            if record.x_discuss_channel_id and partner_ids:
                # Không tự động add khách hàng chính vào channel
                filtered_partner_ids = [
                    pid for pid in partner_ids
                    if pid != record.partner_id.id
                ]
                if filtered_partner_ids:
                    record.x_discuss_channel_id.add_members(filtered_partner_ids)
        return res

    def write(self, vals):
        if 'x_crm_member_ids' in vals:
            old_members = {lead.id: lead.x_crm_member_ids.ids for lead in self}
        else:
            old_members = {}

        res = super().write(vals)

        if 'x_crm_member_ids' in vals:
            for lead in self:
                added_ids = set(lead.x_crm_member_ids.ids) - set(old_members.get(lead.id, []))
                if added_ids:
                    partners = self.env['res.users'].browse(list(added_ids)).mapped('partner_id')
                    partner_ids = [p.id for p in partners if p.id and p.id != lead.partner_id.id]
                    if partner_ids:
                        lead.message_subscribe(partner_ids=partner_ids)
                        if lead.x_discuss_channel_id:
                            lead.x_discuss_channel_id.add_members(partner_ids)

        return res

    def action_open_crm_channel(self):
        self.ensure_one()
        if self.x_discuss_channel_id:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/odoo/discuss?active_id=discuss.channel_{self.x_discuss_channel_id.id}',
                'target': 'self',
            }

