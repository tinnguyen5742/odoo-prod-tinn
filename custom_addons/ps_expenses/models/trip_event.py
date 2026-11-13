from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class PsTeTripEvent(models.Model):
    _name = 'ps.te.trip.event'
    _description = 'PS T&E Trip History'
    _order = 'id desc'
    _rec_name = 'event_type'

    request_id = fields.Many2one(
        'ps.te.trip.request', required=True, readonly=True, ondelete='restrict',
        index=True,
    )
    owner_id = fields.Many2one('res.users', required=True, readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True)
    actor_id = fields.Many2one('res.users', required=True, readonly=True)
    occurred_at = fields.Datetime(required=True, readonly=True)
    event_type = fields.Selection([
        ('submitted', 'Submitted'), ('approved', 'Approved'),
        ('refused', 'Refused'), ('returned', 'Returned for Correction'),
        ('advance_not_requested', 'No Advance Requested'),
        ('cancellation_requested', 'Cancellation Requested'), ('cancellation_approved', 'Cancellation Approved'),
        ('cancellation_refused', 'Cancellation Refused'), ('cancellation_withdrawn', 'Cancellation Withdrawn'),
        ('financial_amendment_applied', 'Manager Amendment Applied After Finance Review'),
    ], required=True, readonly=True)
    revision = fields.Integer(required=True, readonly=True)
    reason = fields.Text(readonly=True)
    receipt = fields.Char(readonly=True)
    purpose = fields.Char(readonly=True)
    destination = fields.Char(readonly=True)
    start_date = fields.Date(readonly=True)
    end_date = fields.Date(readonly=True)
    cancellation_revision = fields.Integer(readonly=True)
    cancellation_snapshot = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Trip history is created only by workflow actions.'))

    @api.model
    def _append(self, vals):
        # Private ORM helper: no RPC exposure or caller-controlled context bypass.
        safe = self.with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
        return super(PsTeTripEvent, safe).create(vals)

    def write(self, vals):
        raise AccessError(_('Trip history cannot be changed.'))

    def unlink(self):
        raise AccessError(_('Trip history cannot be deleted.'))
