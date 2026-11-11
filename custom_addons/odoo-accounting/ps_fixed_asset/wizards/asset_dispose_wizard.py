from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from markupsafe import Markup

class PSAssetDisposeWizard(models.TransientModel):
    _name = 'ps.asset.dispose.wizard'
    _description = 'Asset Dispose Wizard'

    asset_id = fields.Many2one('account.asset.asset', string='Asset', required=True)
    ps_code = fields.Char(string='Asset Code', related='asset_id.ps_code', readonly=True)
    name = fields.Char(string='Asset Name', related='asset_id.name', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', related='asset_id.department_id', readonly=True)
    
    dispose_date = fields.Date(string='Transaction Date', default=fields.Date.context_today, required=True)
    receipt_number = fields.Char(string='Receipt Number')
    invoice_number = fields.Char(string='Invoice Number')
    notes = fields.Char(string='Notes')
    
    # 1. Đổi tên theo yêu cầu Excel
    change_type = fields.Selection([
        ('dispose', 'Dispose'),
        ('cancel', 'Cancel'),
        ('sell', 'Sell')
    ], string='Change Type', default='dispose', required=True)
    
    status = fields.Selection([
        ('unapproved', 'Unapproved'),
        ('approved', 'Approved')
    ], string='Status', default='unapproved', required=True)
    
    counterpart_account_id = fields.Many2one('account.account', string='Cancel / Dispose / Sell Account')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        asset_id = res.get('asset_id') or self.env.context.get('default_asset_id')
        if asset_id:
            asset = self.env['account.asset.asset'].browse(asset_id)
            res.update({
                'receipt_number': asset.receipt_number,
                'invoice_number': asset.invoice_number,
                'notes': asset.notes,
                # 2. Tự động mồi sẵn TK Chi phí khác
                'counterpart_account_id': asset.ps_account_other_expense_id.id if asset.ps_account_other_expense_id else False,
            })
        return res

    @api.onchange('change_type', 'asset_id')
    def _onchange_change_type(self):
        for record in self:
            if record.asset_id and record.asset_id.ps_account_other_expense_id:
                record.counterpart_account_id = record.asset_id.ps_account_other_expense_id.id

    def action_confirm(self):
        self.ensure_one()
        
        # --- Ràng buộc Validate ---
        if self.status == 'unapproved':
            raise ValidationError(_("Please change the Status to 'Approved' to process the disposal."))
            
        if not self.counterpart_account_id:
            raise ValidationError(_("Please select a 'Cancel / Dispose / Sell Account'."))
            
        asset = self.asset_id
        
        asset_account_id = asset.ps_account_asset_id.id
        depreciation_account_id = asset.ps_account_depreciation_id.id
        expense_account_id = self.counterpart_account_id.id
        
        if not asset_account_id or not depreciation_account_id:
            raise ValidationError(_("The asset is missing 'Asset Account' or 'Depreciation Account' configuration."))
            
        # --- 3. Tính toán số tiền ---
        posted_lines = asset.depreciation_line_ids.filtered(lambda l: l.move_check)
        accumulated_depr = sum(posted_lines.mapped('amount'))
        gross_value = asset.value
        residual_value = gross_value - accumulated_depr
        
        # --- 4. Tạo Bút toán Nháp ---
        move_vals = {
            'date': self.dispose_date,
            'journal_id': asset.category_id.journal_id.id,
            'ref': f"{dict(self._fields['change_type'].selection).get(self.change_type)}: {asset.name}",
            'state': 'draft',
            'line_ids': []
        }
        
        if accumulated_depr > 0:
            move_vals['line_ids'].append((0, 0, {
                'account_id': depreciation_account_id,
                'debit': accumulated_depr,
                'credit': 0.0,
                'name': _('Accumulated Depreciation (Disposal)')
            }))
            
        if residual_value > 0:
            move_vals['line_ids'].append((0, 0, {
                'account_id': expense_account_id,
                'debit': residual_value,
                'credit': 0.0,
                'name': _('Residual Value (Disposal)')
            }))
            
        if gross_value > 0:
            move_vals['line_ids'].append((0, 0, {
                'account_id': asset_account_id,
                'debit': 0.0,
                'credit': gross_value,
                'name': _('Asset Gross Value (Disposal)')
            }))
            
        self.env['account.move'].create(move_vals)
        
        # --- 5. Cập nhật Tài sản & Xóa Khấu hao tương lai ---
        unposted_lines = asset.depreciation_line_ids.filtered(lambda l: not l.move_check)
        unposted_lines.unlink() # Xóa dòng chưa vào sổ
        
        asset.write({
            'state': 'close', # Chuyển trạng thái gốc sang Đóng/Thanh lý
            'receipt_number': self.receipt_number,
            'invoice_number': self.invoice_number,
            'notes': self.notes
        })
        
        change_type_label = dict(self._fields['change_type'].selection).get(self.change_type)
        log_message = f"""
            <div style="margin-bottom: 5px;"><strong>Asset {change_type_label} Processed:</strong></div>
            <ul>
                <li><b>Date:</b> {self.dispose_date}</li>
                <li><b>Gross Value:</b> {gross_value:,.0f}</li>
                <li><b>Accumulated Depreciation:</b> {accumulated_depr:,.0f}</li>
                <li><b>Residual Value:</b> {residual_value:,.0f}</li>
                <li><b>Notes:</b> {self.notes or ''}</li>
            </ul>
        """
        asset.message_post(body=Markup(log_message))
        
        return {'type': 'ir.actions.act_window_close'}