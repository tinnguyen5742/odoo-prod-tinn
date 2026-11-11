from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from markupsafe import Markup

class PSAssetUpgradeWizard(models.TransientModel):
    _name = 'ps.asset.upgrade.wizard'
    _description = 'Asset Upgrade and Evaluation Wizard'

    asset_id = fields.Many2one('account.asset.asset', string='Asset', required=True)
    
    ps_code = fields.Char(string='Asset Code', related='asset_id.ps_code', readonly=True)
    name = fields.Char(string='Asset Name', related='asset_id.name', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', related='asset_id.department_id', readonly=True)
    
    old_gross_value = fields.Float(string='Old Gross Value', compute='_compute_old_data')
    old_depreciation_count = fields.Integer(string='Old Depreciation Count', related='asset_id.method_number', readonly=True)
    old_monthly_depreciation_amount = fields.Float(string='Old Monthly Depreciation', compute='_compute_old_data')
    
    status = fields.Selection([
        ('unapproved', 'Unapproved'),
        ('approved', 'Approved')
    ], string='Status', default='unapproved', required=True)

    upgrade_date = fields.Date(string='Upgrade Date', default=fields.Date.context_today)
    receipt_number = fields.Char(string='Receipt Number')
    invoice_number = fields.Char(string='Invoice Number')
    notes = fields.Char(string='Notes')
    
    change_type = fields.Selection([
        ('upgrade', 'Upgrade'),
        ('evaluation', 'Evaluation')
    ], string='Change Type', default='upgrade', required=True)
    
    counterpart_account_id = fields.Many2one('account.account', string='Upgrade / Evaluation Account')
    
    new_gross_value = fields.Float(string='New Gross Value')
    new_depreciation_count = fields.Integer(string='New Depreciation Count')
    
    new_monthly_depreciation_amount = fields.Float(
        string='New Monthly Depreciation', 
        compute='_compute_new_monthly_depreciation',
        readonly=False,
        store=True
    )

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
            })
        return res

    @api.onchange('change_type', 'asset_id')
    def _onchange_change_type_for_account(self):
        for record in self:
            if record.asset_id:
                if record.change_type == 'evaluation':
                    record.counterpart_account_id = record.asset_id.ps_account_evaluation_id
                elif record.change_type == 'upgrade':
                    record.counterpart_account_id = record.asset_id.ps_account_counterpart_id

    @api.depends('asset_id')
    def _compute_old_data(self):
        for record in self:
            if record.asset_id:
                record.old_gross_value = float(record.asset_id.value)
                if record.asset_id.method_number and record.asset_id.method_number > 0:
                    record.old_monthly_depreciation_amount = record.old_gross_value / record.asset_id.method_number
                else:
                    record.old_monthly_depreciation_amount = 0.0
            else:
                record.old_gross_value = 0.0
                record.old_monthly_depreciation_amount = 0.0

    @api.depends('new_gross_value', 'new_depreciation_count', 'old_gross_value', 'old_depreciation_count', 'asset_id', 'change_type')
    def _compute_new_monthly_depreciation(self):
        for record in self:
            if record.new_gross_value > 0 and record.new_depreciation_count > 0 and record.asset_id:
                
                posted_lines = record.asset_id.depreciation_line_ids.filtered(lambda l: l.move_check)
                old_accum_depr = sum(posted_lines.mapped('amount'))
   
                if record.change_type == 'evaluation':
                    if record.old_gross_value > 0:
                        new_accum_depr = record.new_gross_value * (old_accum_depr / record.old_gross_value)
                    else:
                        new_accum_depr = 0.0
                else:
                    new_accum_depr = old_accum_depr

                new_residual_value = record.new_gross_value - new_accum_depr
                if record.new_gross_value > 0:
                    remaining_count_precise = record.new_depreciation_count * (new_residual_value / record.new_gross_value)
                else:
                    remaining_count_precise = 0

                if remaining_count_precise > 0:
                    record.new_monthly_depreciation_amount = new_residual_value / remaining_count_precise
                else:
                    record.new_monthly_depreciation_amount = 0.0
            else:
                record.new_monthly_depreciation_amount = 0.0

    def action_confirm(self):
        for record in self:
            if record.status == 'unapproved':
                raise ValidationError(_("Please change the Status to 'Approved' to process the calculation."))
                
            if not record.new_gross_value or not record.new_depreciation_count:
                raise ValidationError(_("Please enter both 'New Gross Value' and 'New Depreciation Count' before confirming."))

            if record.asset_id:
                asset = record.asset_id
                
                asset_account_id = asset.ps_account_asset_id.id
                depreciation_account_id = asset.ps_account_depreciation_id.id
                upgrade_eval_account_id = record.counterpart_account_id.id
                
                if not asset_account_id:
                    raise ValidationError(_("The asset is not configured with an 'Asset Account'."))
                if not upgrade_eval_account_id:
                    raise ValidationError(_("Please select an 'Upgrade / Evaluation Account'."))

                diff_gross = record.new_gross_value - record.old_gross_value
                
                if diff_gross != 0:
                    move_vals = {
                        'date': record.upgrade_date,
                        'journal_id': asset.category_id.journal_id.id,
                        'ref': f"{dict(self._fields['change_type'].selection).get(record.change_type)}: {asset.name}",
                        'state': 'draft',
                        'line_ids': []
                    }

                    if record.change_type == 'upgrade':
                        if diff_gross > 0:
                            move_vals['line_ids'] = [
                                (0, 0, {'account_id': asset_account_id, 'debit': diff_gross, 'credit': 0.0, 'name': _('Asset Gross Value Increase')}),
                                (0, 0, {'account_id': upgrade_eval_account_id, 'debit': 0.0, 'credit': diff_gross, 'name': _('Incurred Upgrade Cost')}),
                            ]
                        else:
                            raise ValidationError(_("The Upgrade Cost (New Gross Value) must be greater than the current Gross Value."))

                    elif record.change_type == 'evaluation':
                        if not depreciation_account_id:
                            raise ValidationError(_("The asset is not configured with a 'Depreciation Account' to calculate the difference."))
                        
                        old_accum_depr = record.old_gross_value - asset.value_residual
                        if record.old_gross_value > 0:
                            new_accum_depr = record.new_gross_value * (old_accum_depr / record.old_gross_value)
                        else:
                            new_accum_depr = 0.0
                            
                        diff_depr = new_accum_depr - old_accum_depr
                        diff_residual = abs(diff_gross) - abs(diff_depr)
                        
                        if diff_gross > 0:
                            move_vals['line_ids'] = [
                                (0, 0, {'account_id': asset_account_id, 'debit': diff_gross, 'credit': 0.0, 'name': _('Gross Value Increase (Evaluation)')}),
                                (0, 0, {'account_id': depreciation_account_id, 'debit': 0.0, 'credit': abs(diff_depr), 'name': _('Accumulated Depreciation Increase (Evaluation)')}),
                                (0, 0, {'account_id': upgrade_eval_account_id, 'debit': 0.0, 'credit': diff_residual, 'name': _('Evaluation Surplus')}),
                            ]
                        else:
                            move_vals['line_ids'] = [
                                (0, 0, {'account_id': depreciation_account_id, 'debit': abs(diff_depr), 'credit': 0.0, 'name': _('Accumulated Depreciation Decrease (Evaluation)')}),
                                (0, 0, {'account_id': upgrade_eval_account_id, 'debit': diff_residual, 'credit': 0.0, 'name': _('Evaluation Deficit')}),
                                (0, 0, {'account_id': asset_account_id, 'debit': 0.0, 'credit': abs(diff_gross), 'name': _('Gross Value Decrease (Evaluation)')}),
                            ]

                    self.env['account.move'].create(move_vals)

                update_vals = {}
                if record.new_gross_value > 0:
                    update_vals['value'] = record.new_gross_value
                if record.new_depreciation_count > 0:
                    update_vals['method_number'] = record.new_depreciation_count
                
                update_vals['receipt_number'] = record.receipt_number
                update_vals['invoice_number'] = record.invoice_number
                update_vals['notes'] = record.notes
                
                if update_vals:
                    change_type_label = dict(self._fields['change_type'].selection).get(record.change_type)
                    log_message = f"""
                        <div style="margin-bottom: 5px;"><strong>Asset Upgrade / Evaluation History:</strong></div>
                        <ul>
                            <li><b>Change Type:</b> {change_type_label}</li>
                            <li><b>Date:</b> {record.upgrade_date}</li>
                            <li><b>Gross Value:</b> {record.old_gross_value:,.0f} ➔ <b style="color: #017e84;">{record.new_gross_value:,.0f}</b></li>
                            <li><b>Depreciation Count:</b> {record.old_depreciation_count} ➔ <b style="color: #017e84;">{record.new_depreciation_count}</b></li>
                            <li><b>Notes:</b> {record.notes or ''}</li>
                        </ul>
                    """
                    
                    record.asset_id.write(update_vals)
                    
                    posted_lines = record.asset_id.depreciation_line_ids.filtered(lambda l: l.move_check)
                    for line in posted_lines:
                        new_residual = record.asset_id.value - line.depreciated_value
                        line.write({'remaining_value': new_residual})
                        
                    record.asset_id.compute_depreciation_board()
                    record.asset_id.message_post(body=Markup(log_message))
                    
        return {'type': 'ir.actions.act_window_close'}