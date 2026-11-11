from odoo import models, fields, api


class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

    certificate_url = fields.Char(
        string='Certificate URL',
        compute='_compute_certificate_url',
    )
    
    cert_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Công ty cấp chứng nhận',
        compute='_compute_cert_company',
    )

    x_channel_id = fields.Many2one(
        'slide.channel',
        string='Evaluated Course',
        index=True,
        copy=False,
        help='Course this evaluation survey response was submitted for.',
    )

    @api.depends('partner_id', 'partner_id.company_id', 'partner_id.user_ids.company_id')
    def _compute_cert_company(self):
        for record in self:
            company = (
                record.partner_id.company_id
                or (record.partner_id.user_ids[:1].company_id if record.partner_id.user_ids else record.env.company)
                or record.env.company
            )
            record.cert_company_id = company

    @api.depends('survey_id.access_token', 'access_token', 'scoring_success', 'state')
    def _compute_certificate_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            if (record.survey_id.access_token and record.access_token
                    and record.scoring_success and record.state == 'done'):
                record.certificate_url = (
                    '%s/survey/%s/%s/certificate_inline'
                    % (base_url or '',
                       record.survey_id.access_token,
                       record.access_token)
                )
            else:
                record.certificate_url = False
    
    def write(self, vals):
        res = super().write(vals)
        if vals.get('state') == 'done':
            for record in self.filtered(lambda r: r.x_channel_id and r.partner_id):
                self.env['slide.channel.partner'].sudo().search([
                    ('channel_id', '=', record.x_channel_id.id),
                    ('partner_id', '=', record.partner_id.id),
                    ('member_status', '!=', 'completed'),
                ])._complete_after_evaluation()
        return res
