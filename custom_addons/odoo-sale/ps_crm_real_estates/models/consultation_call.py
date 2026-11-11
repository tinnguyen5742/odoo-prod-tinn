from odoo import fields, models


class ConsultationCall(models.Model):
    _name = 'crm.lead.consultation.call'
    _description = 'Consultation Call'
    _rec_name = 'result_id'
    _order = 'start_date desc, id desc'

    lead_id = fields.Many2one(
        'crm.lead', string='Lead', required=True, ondelete='cascade', index=True,
    )
    start_date = fields.Datetime(string='Start Date')
    result_id = fields.Many2one(
        'crm.lead.consultation.result', string='Result', ondelete='restrict',
    )
    notes = fields.Text(string='Notes')


class ConsultationResult(models.Model):
    _name = 'crm.lead.consultation.result'
    _description = 'Consultation Call Result'
    _order = 'id'

    name = fields.Char(string='Result Name', required=True, translate=True)
