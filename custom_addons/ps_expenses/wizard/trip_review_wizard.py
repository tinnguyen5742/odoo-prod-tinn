from odoo import fields, models


class PsTeTripReviewWizard(models.TransientModel):
    _name = 'ps.te.trip.review.wizard'
    _description = 'Review Trip Request'

    request_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True)
    expected_revision = fields.Integer(required=True, readonly=True)
    decision = fields.Selection([
        ('approved', 'Approve'), ('refused', 'Refuse'),
        ('returned', 'Return for Correction'),
    ], required=True)
    reason = fields.Text(required=True)

    def action_apply(self):
        self.ensure_one()
        self.request_id.action_review(
            self.decision, self.reason, self.expected_revision,
        )
        return {'type': 'ir.actions.act_window_close'}
