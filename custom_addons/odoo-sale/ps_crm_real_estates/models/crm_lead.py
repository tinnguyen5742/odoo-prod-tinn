from odoo import api, fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    consultation_call_ids = fields.One2many(
        'crm.lead.consultation.call', 'lead_id', string='Consultation Calls',
    )
    latest_consultation_call_id = fields.Many2one(
        'crm.lead.consultation.call', string='Latest Consultation Call',
        compute='_compute_latest_consultation_call', store=True,
    )
    consultation_owner_id = fields.Many2one(
        related='property_id.owner_partner_id', string='Owner',
    )
    latest_consultation_result_id = fields.Many2one(
        related='latest_consultation_call_id.result_id', string='Result',
    )
    latest_consultation_start_date = fields.Datetime(
        related='latest_consultation_call_id.start_date', string='Start Date',
        store=True, index=True,
    )
    consultation_status = fields.Selection(
        [('done', 'Completed')], string='Status',
        compute='_compute_consultation_status',
    )

    @api.depends('consultation_call_ids.start_date')
    def _compute_latest_consultation_call(self):
        for lead in self:
            dated_calls = lead.consultation_call_ids.filtered('start_date')
            lead.latest_consultation_call_id = max(
                dated_calls,
                key=lambda call: (call.start_date, call.id or 0),
                default=False,
            )

    def _compute_consultation_status(self):
        for lead in self:
            lead.consultation_status = 'done'
