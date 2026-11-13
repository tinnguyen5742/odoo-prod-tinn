from odoo import fields, models


class TripCancellationWizard(models.TransientModel):
    _name = 'ps.te.trip.cancellation.wizard'
    _description = 'Trip Cancellation'

    trip_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True)
    expected_revision = fields.Integer(required=True, readonly=True)
    expected_cancellation_revision = fields.Integer(required=True, readonly=True)
    operation = fields.Selection([
        ('request', 'Request Trip Cancellation'), ('approved', 'Approve Trip Cancellation'),
        ('refused', 'Refuse Trip Cancellation'), ('withdraw', 'Withdraw Cancellation Request'),
    ], required=True)
    reason = fields.Text(required=True)

    def action_apply(self):
        self.ensure_one()
        if self.operation == 'request':
            self.trip_id.action_request_cancellation(self.reason, self.expected_revision, self.expected_cancellation_revision)
        elif self.operation == 'withdraw':
            self.trip_id.action_withdraw_cancellation(self.reason, self.expected_cancellation_revision)
        else:
            self.trip_id.action_decide_cancellation(self.operation, self.reason, self.expected_cancellation_revision)
        return {'type': 'ir.actions.act_window_close'}
