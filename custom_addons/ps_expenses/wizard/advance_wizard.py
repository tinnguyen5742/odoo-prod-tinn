from odoo import fields, models, _
from odoo.exceptions import ValidationError


class PsTeAdvanceWizard(models.TransientModel):
    _name = 'ps.te.advance.wizard'
    _description = 'Advance Operation'

    advance_id = fields.Many2one('ps.te.trip.advance', readonly=True)
    trip_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True)
    currency_id = fields.Many2one(related='trip_id.company_id.currency_id', readonly=True)
    expected_revision = fields.Integer(readonly=True)
    operation = fields.Selection([
        ('create', 'Create Advance Draft'), ('edit', 'Edit Draft'),
        ('submit', 'Submit for Finance Review'), ('approved', 'Approve Amount'),
        ('refused', 'Refuse'), ('returned', 'Return for Correction'),
        ('cancel', 'Cancel Before Disbursement'), ('revise', 'Withdraw/Reopen for Revision'),
        ('disburse', 'Record External Disbursement'),
        ('start', 'Prepare External Disbursement'), ('not_executed', 'Confirm Prepared Payment Not Executed'),
    ], required=True)
    amount = fields.Monetary()
    purpose = fields.Text()
    reason = fields.Text()
    external_reference = fields.Char()
    execution_date = fields.Date(default=fields.Date.context_today)

    def action_apply(self):
        self.ensure_one()
        if self.operation == 'create':
            if self.advance_id:
                raise ValidationError(_('Open the existing advance instead of creating another one.'))
            advance = self.env['ps.te.trip.advance'].create({
                'trip_id': self.trip_id.id, 'requested_amount': self.amount, 'purpose': self.purpose,
            })
            return {'type': 'ir.actions.act_window', 'res_model': advance._name,
                    'res_id': advance.id, 'view_mode': 'form', 'target': 'current'}
        advance = self.advance_id
        if not advance or advance.trip_id != self.trip_id:
            raise ValidationError(_('Select the exact advance and trip.'))
        if self.operation == 'edit':
            advance.action_edit(self.amount, self.purpose, self.expected_revision)
        elif self.operation == 'submit':
            advance.action_submit(self.expected_revision)
        elif self.operation in ('approved', 'refused', 'returned'):
            advance.action_review(self.operation, self.reason, self.expected_revision, self.amount)
        elif self.operation == 'cancel':
            advance.action_cancel(self.reason, self.expected_revision)
        elif self.operation == 'revise':
            advance.action_revise(self.reason, self.expected_revision)
        elif self.operation == 'disburse':
            advance.action_record_disbursement(
                self.amount, self.external_reference, self.execution_date, self.expected_revision,
            )
        elif self.operation == 'start':
            advance.action_start_disbursement(self.external_reference, self.reason, self.expected_revision)
        elif self.operation == 'not_executed':
            advance.action_confirm_no_payment(self.external_reference, self.reason, self.expected_revision)
        else:
            raise ValidationError(_('Unsupported advance operation.'))
        return {'type': 'ir.actions.act_window_close'}
