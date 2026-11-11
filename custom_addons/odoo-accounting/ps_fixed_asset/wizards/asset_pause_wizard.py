from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from markupsafe import Markup

class PSAssetPauseWizard(models.TransientModel):
    _name = 'ps.asset.pause.wizard'
    _description = 'Asset Pause and Resume Wizard'

    asset_id = fields.Many2one('account.asset.asset', string='Asset', required=True)
    
    ps_code = fields.Char(string='Asset Code', related='asset_id.ps_code', readonly=True)
    name = fields.Char(string='Asset Name', related='asset_id.name', readonly=True)
    transaction_date = fields.Date(string='Transaction Date', default=fields.Date.context_today, required=True)
    reference_document = fields.Char(string='Reference Document')
    notes = fields.Char(string='Notes')
    
    change_type = fields.Selection([
        ('pause', 'Pause Depreciation'),
        ('resume', 'Resume Depreciation')
    ], string='Change Type', default='pause', required=True)
    
    department_id = fields.Many2one('hr.department', string='Department', related='asset_id.department_id', readonly=True)
    
    status = fields.Selection([
        ('unapproved', 'Unapproved'),
        ('approved', 'Approved')
    ], string='Status', default='unapproved', required=True)

    def action_confirm(self):
        self.ensure_one()

        if self.status == 'unapproved':
            raise ValidationError(_("Please change the Status to 'Approved' to process."))
            
        if self.asset_id:
            asset = self.asset_id
  
            if self.change_type == 'pause':

                unposted_lines = asset.depreciation_line_ids.filtered(lambda l: not l.move_check)
                if not unposted_lines:
                    raise ValidationError(_("There are no future depreciation lines to pause."))

                unposted_lines.unlink()
                
            elif self.change_type == 'resume':
 
                asset.compute_depreciation_board()

            change_type_label = dict(self._fields['change_type'].selection).get(self.change_type)
            log_message = f"""
                <div style="margin-bottom: 5px;"><strong>Asset {change_type_label} Processed:</strong></div>
                <ul>
                    <li><b>Transaction Date:</b> {self.transaction_date}</li>
                    <li><b>Reference:</b> {self.reference_document or 'N/A'}</li>
                    <li><b>Notes:</b> {self.notes or ''}</li>
                </ul>
            """
            asset.message_post(body=Markup(log_message))
            
        return {'type': 'ir.actions.act_window_close'}