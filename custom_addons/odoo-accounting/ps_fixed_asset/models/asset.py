from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class AccountAssetAsset(models.Model):
    _inherit = 'account.asset.asset'

    ps_code = fields.Char(string='Asset Code', required=True, default='New', copy=False, tracking=True)
    technical_spec = fields.Char(string='Technical Specs')
    manufacturer = fields.Char(string='Manufacturer')
    manufacture_year = fields.Char(string='Manufacture Year')
    made_in = fields.Char(string='Made In')
    ps_department_code = fields.Char(string='Department Code')
    department_id = fields.Many2one('hr.department', string='Department')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    is_opening = fields.Boolean(string='Opening Balance')
    receipt_number = fields.Char(string='Receipt Number')
    invoice_number = fields.Char(string='Invoice Number')
    notes = fields.Text(string='Notes')

    ps_account_asset_id = fields.Many2one('account.account', string='Asset Account')
    ps_account_counterpart_id = fields.Many2one('account.account', string='Counterpart Account')
    ps_account_depreciation_expense_id = fields.Many2one('account.account', string='Expense Account')
    ps_account_depreciation_id = fields.Many2one('account.account', string='Depreciation Account')
    ps_analytic_plan_id = fields.Many2one('account.analytic.plan', string='Expense Item')
    ps_account_evaluation_id = fields.Many2one('account.account', string='Evaluation Account')
    ps_account_other_income_id = fields.Many2one('account.account', string='Other Income Account')
    ps_account_other_expense_id = fields.Many2one('account.account', string='Other Expense Account')
    ps_machine_equipment = fields.Char(string='Machine/Equipment')
    accessory_line_ids = fields.One2many('ps.asset.accessory', 'asset_id', string='Accessories')

    # THÊM LOGIC ĐIỀU KIỆN ẨN NÚT SET TO DRAFT
    ps_capitalization_move_id = fields.Many2one('account.move', string='Capitalization Move', copy=False)
    ps_hide_draft_btn = fields.Boolean(compute='_compute_ps_hide_draft_btn')

    @api.depends('ps_capitalization_move_id.state', 'ps_capitalization_move_id.posted_before', 'depreciation_line_ids.move_check')
    def _compute_ps_hide_draft_btn(self):
        for asset in self:
            has_depr_moves = any(line.move_check for line in asset.depreciation_line_ids)

            hide_cap = False
            cap_move = asset.ps_capitalization_move_id
            
            if not cap_move:
                cap_move = self.env['account.move'].search([
                    ('ref', '=', f'Asset Capitalization: {asset.name}')
                ], limit=1)
                
            if cap_move:
                if cap_move.state == 'posted' or cap_move.posted_before:
                    hide_cap = True
                    
            asset.ps_hide_draft_btn = bool(hide_cap or has_depr_moves)
            
    def compute_depreciation_board(self):
        res = super(AccountAssetAsset, self).compute_depreciation_board()
        for asset in self:
            if asset.prorata and asset.method_number > 0:
                lines = asset.depreciation_line_ids.sorted(key=lambda l: l.depreciation_date)
                if len(lines) == asset.method_number + 1:
                    last_line = lines[-1]         
                    second_last_line = lines[-2]   
                    if not last_line.move_check and not second_last_line.move_check:
                        new_amount = second_last_line.amount + last_line.amount
                        new_cumulative = second_last_line.depreciated_value + last_line.amount
                        second_last_line.write({
                            'amount': new_amount,
                            'depreciated_value': new_cumulative,
                            'remaining_value': 0.0  
                        })
                        last_line.unlink()
        return res
    
    def validate(self):
        res = super(AccountAssetAsset, self).validate()
        for asset in self:
            if not asset.is_opening:
                if not asset.ps_account_asset_id or not asset.ps_account_counterpart_id:
                    raise ValidationError(_("Please configure both 'Asset Account' and 'Intermediate Account' to create the asset capitalization journal entry!"))
                if not asset.category_id.journal_id:
                    raise ValidationError(_("Please configure the Journal on the Asset Category!"))
                
                move_vals = {
                    'date': asset.date,
                    'journal_id': asset.category_id.journal_id.id,
                    'ref': _("Asset Capitalization: %s") % asset.name,
                    'line_ids': [
                        (0, 0, {
                            'account_id': asset.ps_account_asset_id.id,
                            'debit': asset.value,
                            'credit': 0.0,
                            'name': asset.name,
                        }),
                        (0, 0, {
                            'account_id': asset.ps_account_counterpart_id.id,
                            'debit': 0.0,
                            'credit': asset.value,
                            'name': asset.name,
                        })
                    ]
                }
                move = self.env['account.move'].create(move_vals)
                # Gắn liên kết bút toán để tính toán khóa nút Set to draft
                asset.ps_capitalization_move_id = move.id 
        return res

    @api.onchange('category_id')
    def _onchange_ps_category_id(self):
        for record in self:
            if record.category_id:
                record.ps_account_asset_id = record.category_id.account_asset_id
                record.ps_account_depreciation_id = record.category_id.account_depreciation_id
                record.ps_account_depreciation_expense_id = record.category_id.account_depreciation_expense_id
                record.ps_account_other_income_id = record.category_id.account_other_income_id
                record.ps_account_other_expense_id = record.category_id.account_other_expense_id
                record.ps_analytic_plan_id = record.category_id.analytic_plan_id
                record.ps_account_counterpart_id = record.category_id.ps_account_counterpart_id
                record.ps_account_evaluation_id = record.category_id.ps_account_evaluation_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('ps_code') or vals.get('ps_code') == 'New':
                company_id = vals.get('company_id', self.env.company.id)
                company = self.env['res.company'].browse(company_id)
                prefix = company.asset_code_prefix or 'TS'
                seq_code = 'ps.asset.auto.sequence'
                sequence = self.env['ir.sequence'].sudo().search([('code', '=', seq_code)], limit=1)
                if not sequence:
                    sequence = self.env['ir.sequence'].sudo().create({
                        'name': 'Asset Code Sequence',
                        'code': seq_code,
                        'padding': 4,
                    })
                next_num = sequence.next_by_id()
                vals['ps_code'] = f"{prefix}{next_num}"
        return super(AccountAssetAsset, self).create(vals_list)

class PSAssetFunding(models.Model):
    _name = 'ps.asset.funding'
    _description = 'Asset Funding Line'
    company_id = fields.Many2one('res.company', related='asset_id.company_id', store=True, index=True)
    asset_id = fields.Many2one('account.asset.asset', string='Asset', ondelete='cascade')
    funding_code = fields.Char(string='Funding Code')
    funding_name = fields.Char(string='Funding Name')
    value = fields.Float(string='Value')
    depreciation_value = fields.Float(string='Depreciation Value')

class PSAssetAccessory(models.Model):
    _name = 'ps.asset.accessory'
    _description = 'Asset Accessory Line'
    company_id = fields.Many2one('res.company', related='asset_id.company_id', store=True, index=True)
    asset_id = fields.Many2one('account.asset.asset', string='Asset', ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    description = fields.Char(string='Description', required=True)
    quantity = fields.Float(string='Quantity', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='UoM')
    notes = fields.Char(string='Notes')

class AssetDepreciationConfirmationWizardInherit(models.TransientModel):
    _inherit = 'asset.depreciation.confirmation.wizard'
    def asset_compute(self):
        self.ensure_one()
        account_date = self.date
        return super(AssetDepreciationConfirmationWizardInherit, self.with_context(forced_account_date=account_date)).asset_compute()


class AccountAssetDepreciationLineInherit(models.Model):
    _inherit = 'account.asset.depreciation.line'

    move_posted_check = fields.Boolean(
        string='Posted',
        compute='_compute_move_posted_check_fix',
        store=True
    )

    @api.depends('move_id.state')
    def _compute_move_posted_check_fix(self):
        for line in self:
            line.move_posted_check = bool(line.move_id and line.move_id.state == 'posted')

    def create_move(self, *args, **kwargs):
        kwargs['post_move'] = False 
        forced_date = self.env.context.get('forced_account_date')
        if forced_date:
            created_moves = super(AccountAssetDepreciationLineInherit, self).create_move(*args, **kwargs)
            if created_moves:
                moves = self.env['account.move'].browse(created_moves) if isinstance(created_moves, (list, tuple)) else created_moves
                moves.write({'date': forced_date})
            return created_moves
        else:
            return super(AccountAssetDepreciationLineInherit, self).create_move(*args, **kwargs)


class AccountMoveInherit(models.Model):
    _inherit = 'account.move'

    ps_depreciation_line_ids = fields.One2many(
        'account.asset.depreciation.line', 
        'move_id', 
        string='Depreciation Lines'
    )

    def write(self, vals):
        res = super(AccountMoveInherit, self).write(vals)
        if 'state' in vals:
            for move in self:
                if move.ps_depreciation_line_ids:
                    is_posted = True if vals['state'] == 'posted' else False
                    self.env.cr.execute(
                        "UPDATE account_asset_depreciation_line SET move_posted_check=%s WHERE move_id=%s",
                        (is_posted, move.id)
                    )
                    move.ps_depreciation_line_ids.invalidate_recordset(['move_posted_check'])
        return res
    
   