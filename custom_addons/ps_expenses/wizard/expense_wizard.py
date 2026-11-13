from odoo import fields, models, _
from odoo.exceptions import ValidationError


class PsTeExpenseWizard(models.TransientModel):
    _name = 'ps.te.expense.wizard'
    _description = 'Expense Operation'

    report_id = fields.Many2one('ps.te.expense.report', required=True, readonly=True)
    currency_id = fields.Many2one(related='report_id.currency_id')
    expected_revision = fields.Integer(required=True, readonly=True)
    operation = fields.Selection([
        ('add', 'Add Expense'), ('edit', 'Edit Expense'), ('upload', 'Upload Proof'),
        ('submit', 'Submit Report'), ('accepted', 'Accept Expense'),
        ('refused', 'Refuse Expense'), ('returned', 'Return Expense for Correction'),
        ('revise', 'Withdraw Report for Revision'), ('supersede', 'Supersede Proof'),
        ('zero_declare', 'Declare No Expenses After Cancellation'),
        ('zero_accept', 'Confirm Zero Expenses'), ('zero_return', 'Return Zero Declaration for Correction'),
        ('reuse', 'Link Previous Expense Proof'), ('supersede_link', 'Supersede Linked Proof'),
    ], required=True)
    line_id = fields.Many2one('ps.te.expense.line')
    evidence_id = fields.Many2one('ps.te.expense.evidence')
    source_evidence_id = fields.Many2one('ps.te.expense.evidence')
    proof_link_id = fields.Many2one('ps.te.expense.proof.link')
    description = fields.Char()
    amount = fields.Monetary()
    expense_date = fields.Date(default=fields.Date.context_today)
    reason = fields.Text()
    filename = fields.Char()
    file_data = fields.Binary(attachment=False)

    def action_apply(self):
        self.ensure_one()
        report = self.report_id
        if self.line_id and self.line_id.report_id != report:
            raise ValidationError(_('Select an expense line from this report.'))
        if self.evidence_id and self.evidence_id.report_id != report:
            raise ValidationError(_('Select proof from this report.'))
        if self.operation == 'reuse':
            report.action_reuse_evidence(self.line_id.id, self.source_evidence_id.id, self.expected_revision)
        elif self.operation == 'supersede_link':
            if not self.proof_link_id or self.proof_link_id.report_id != report:
                raise ValidationError(_('Select proof from this report.'))
            self.proof_link_id.action_supersede(self.reason, self.expected_revision)
        elif self.operation == 'add':
            report.action_add_line(self.description, self.amount, self.expense_date, self.expected_revision)
        elif self.operation == 'zero_declare':
            report.action_declare_zero_expenses(self.reason, self.expected_revision)
        elif self.operation in ('zero_accept', 'zero_return'):
            report.action_review_zero_expenses('accepted' if self.operation == 'zero_accept' else 'returned', self.reason, self.expected_revision)
        elif self.operation == 'edit':
            report.action_edit_line(self.line_id.id, self.description, self.amount, self.expense_date, self.expected_revision)
        elif self.operation == 'upload':
            report.action_upload_evidence(self.line_id.id, self.filename, self.file_data, self.expected_revision)
        elif self.operation == 'submit':
            report.action_submit(self.expected_revision)
        elif self.operation in ('accepted', 'refused', 'returned'):
            report.action_review_line(self.line_id.id, self.operation, self.reason, self.amount, self.expected_revision)
        elif self.operation == 'revise':
            report.action_revise(self.reason, self.expected_revision)
        elif self.operation == 'supersede':
            if not self.evidence_id:
                raise ValidationError(_('Select proof to supersede.'))
            report._assert_actor('owner')
            self.evidence_id.action_supersede(self.reason, self.expected_revision)
        else:
            raise ValidationError(_('Unsupported expense operation.'))
        return {'type': 'ir.actions.act_window_close'}
