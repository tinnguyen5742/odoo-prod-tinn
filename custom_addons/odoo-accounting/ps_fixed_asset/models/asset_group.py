from odoo import models, fields, api
from odoo.exceptions import ValidationError
class AccountAssetCategoryInherit(models.Model):
    _inherit = 'account.asset.category'

    # Group Code
    code = fields.Char(string='Group Code', tracking=True)

    # 3 Segment fields
    segment_01_id = fields.Many2one('ps.asset.segment.line', string='Segment 01', domain=[('segment_type_related', '=', 'Segment01')])
    segment_02_id = fields.Many2one('ps.asset.segment.line', string='Segment 02', domain=[('segment_type_related', '=', 'Segment02')])
    segment_03_id = fields.Many2one('ps.asset.segment.line', string='Segment 03', domain=[('segment_type_related', '=', 'Segment03')])

    # Additional fields
    account_other_income_id = fields.Many2one('account.account', string='Other Income Account')
    account_other_expense_id = fields.Many2one('account.account', string='Other Expense Account')
    analytic_plan_id = fields.Many2one('account.analytic.plan', string='Expense Item')
    ps_account_counterpart_id = fields.Many2one(
        'account.account', 
        string='Intermediate Account', 
        help='Intermediate account (e.g., 2119) used to record when purchasing an asset.'
    )
    ps_account_evaluation_id = fields.Many2one('account.account', string='Evaluation Account')
    # Auto-generate Group Code (code) and Asset Type (name) from Segments
    @api.onchange('segment_01_id', 'segment_02_id', 'segment_03_id')
    def _onchange_segments(self):
        codes = []
        names = []
        for seg in [self.segment_01_id, self.segment_02_id, self.segment_03_id]:
            if seg:
                codes.append(seg.code or '')
                names.append(seg.name or '')
        
        if codes:
            self.code = '.'.join([c for c in codes if c])
        
        if names:
            self.name = ', '.join([n for n in names if n])
            
    @api.constrains('code')
    def _check_unique_group_code(self):
        for record in self:
            if record.code:
                duplicate = self.search([
                    ('code', '=', record.code),
                    ('id', '!=', record.id)
                ], limit=1)
                
                if duplicate:
                    raise ValidationError("The Group Code '%s' already exists! Please enter a different code." % record.code)