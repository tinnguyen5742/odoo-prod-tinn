from odoo import fields, models


class CorrectionWizard(models.TransientModel):
    _name = 'ps.te.correction.wizard'
    _description = 'Correction Case'

    trip_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True)
    correction_id = fields.Many2one('ps.te.correction', readonly=True)
    expected_revision = fields.Integer(required=True, readonly=True)
    operation = fields.Selection([
        ('create', 'Open Correction Case'), ('refresh', 'Refresh Source Snapshot'),
        ('return', 'Return Unexecuted Sources for Revision'), ('external', 'Require External Resolution'),
        ('propose', 'Propose No Source Change'), ('confirm', 'Confirm Unchanged Cash Facts'),
        ('resolve', 'Resolve No-Change Investigation'),
        ('adjust', 'Create Financial Adjustment Version'),
    ], required=True)
    category = fields.Selection([('basis', 'Expense or Settlement Basis'), ('funding', 'Funding Record'),
                                 ('authority', 'Policy or Authority')])
    reason = fields.Text(required=True)
    reference = fields.Char()

    def action_apply(self):
        self.ensure_one()
        record, revision = self.correction_id, self.expected_revision
        if self.operation == 'create':
            record = self.env['ps.te.correction'].create({'trip_id': self.trip_id.id, 'category': self.category,
                                                        'description': self.reason, 'expected_revision': revision})
            return {'type': 'ir.actions.act_window', 'res_model': record._name, 'res_id': record.id, 'view_mode': 'form'}
        if self.operation == 'adjust':
            return record.action_create_adjustment(self.reason, revision)
        if self.operation == 'refresh':
            record.action_refresh(self.reason, revision)
        elif self.operation == 'return':
            record.action_return_for_revision(self.reason, revision)
        elif self.operation == 'external':
            record.action_require_external(self.reference, self.reason, revision)
        elif self.operation == 'propose':
            record.action_propose_no_change(self.reference, self.reason, revision)
        elif self.operation == 'confirm':
            record.action_confirm_no_change(self.reference, self.reason, revision)
        elif self.operation == 'resolve':
            record.action_resolve_no_change(self.reason, revision)
        return {'type': 'ir.actions.act_window_close'}
