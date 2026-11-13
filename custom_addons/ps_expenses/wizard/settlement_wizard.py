from odoo import fields, models, _
from odoo.exceptions import ValidationError


class PsTeSettlementWizard(models.TransientModel):
    _name = 'ps.te.settlement.wizard'
    _description = 'Settlement Operation'

    settlement_id = fields.Many2one('ps.te.settlement', required=True, readonly=True)
    currency_id = fields.Many2one(related='settlement_id.currency_id')
    expected_revision = fields.Integer(required=True, readonly=True)
    operation = fields.Selection([
        ('refresh', 'Refresh Prepared Bases'), ('none', 'Confirm No Advance Payment'),
        ('submit', 'Submit for Review'), ('approve', 'Approve Exact Settlement'),
        ('return', 'Return Before Cash Execution'), ('start', 'Prepare External Cash'),
        ('not_executed', 'Confirm Cash Not Executed'), ('record', 'Record External Cash'),
        ('close', 'Close Recorded Workflow'),
    ], required=True)
    amount = fields.Monetary()
    reference = fields.Char()
    execution_date = fields.Date(default=fields.Date.context_today)
    reason = fields.Text()

    def action_apply(self):
        self.ensure_one()
        record, rev = self.settlement_id, self.expected_revision
        if self.operation == 'refresh':
            record.action_refresh(self.reason, rev)
        elif self.operation == 'none':
            record.action_confirm_no_funding(self.reference, self.reason, rev)
        elif self.operation == 'submit':
            record.action_submit(rev)
        elif self.operation == 'approve':
            record.action_approve(self.reason, rev)
        elif self.operation == 'return':
            record.action_return(self.reason, rev)
        elif self.operation == 'start':
            record.action_start_cash(self.reference, self.reason, rev)
        elif self.operation == 'not_executed':
            record.action_confirm_cash_not_executed(self.reference, self.reason, rev)
        elif self.operation == 'record':
            record.action_record_cash(self.amount, self.reference, self.execution_date, rev)
        elif self.operation == 'close':
            record.action_close(self.reason, rev)
        else:
            raise ValidationError(_('Unsupported settlement operation.'))
        return {'type': 'ir.actions.act_window_close'}
