from odoo import models, fields, api

class PSAssetTransferWizard(models.TransientModel):
    _name = 'ps.asset.transfer.wizard'
    _description = 'Asset Transfer Wizard'

    asset_id = fields.Many2one('account.asset.asset', string='Asset', required=True)
    
    # --- COMMON INFO ---
    ps_code = fields.Char(string='Asset Code', related='asset_id.ps_code', readonly=True)
    name = fields.Char(string='Asset Name', related='asset_id.name', readonly=True)
    transfer_date = fields.Date(string='Transfer Date', default=fields.Date.context_today)
    receipt_number = fields.Char(string='Receipt Number')
    invoice_number = fields.Char(string='Invoice Number')
    notes = fields.Char(string='Notes')
    status = fields.Selection([
        ('unapproved', 'Unapproved'),
        ('approved', 'Approved')
    ], string='Status', default='approved')

    # --- OLD DEPARTMENT (Readonly) ---
    old_department_code = fields.Char(string='Department Code', related='asset_id.ps_department_code', readonly=True)
    old_department_id = fields.Many2one('hr.department', string='Department', related='asset_id.department_id', readonly=True)
    old_employee_id = fields.Many2one('hr.employee', string='User', related='asset_id.employee_id', readonly=True)
    old_machine_code = fields.Char(string='Machine Code', related='asset_id.ps_machine_equipment', readonly=True)
    old_expense_account_id = fields.Many2one('account.account', string='Expense Account', related='asset_id.ps_account_depreciation_expense_id', readonly=True)
    old_analytic_id = fields.Many2one('account.analytic.plan', string='Analytic Account', related='asset_id.ps_analytic_plan_id', readonly=True)

    # --- NEW DEPARTMENT (Input) ---
    new_department_code = fields.Char(string='Department Code')
    new_department_id = fields.Many2one('hr.department', string='Department', required=True)
    new_employee_id = fields.Many2one('hr.employee', string='User')
    new_machine_code = fields.Char(string='Machine Code')
    new_expense_account_id = fields.Many2one('account.account', string='Expense Account')
    new_analytic_id = fields.Many2one('account.analytic.plan', string='Analytic Account')   
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

    def action_confirm(self):
        for record in self:
            if record.asset_id:
                update_vals = {
                    'ps_department_code': record.new_department_code,
                    'department_id': record.new_department_id.id if record.new_department_id else False,
                    'employee_id': record.new_employee_id.id if record.new_employee_id else False,
                    'ps_machine_equipment': record.new_machine_code,
                    'ps_account_depreciation_expense_id': record.new_expense_account_id.id if record.new_expense_account_id else False,
                    'ps_analytic_plan_id': record.new_analytic_id.id if record.new_analytic_id else False,
                    'receipt_number': record.receipt_number,
                    'invoice_number': record.invoice_number,
                    'notes': record.notes,
                }
                record.asset_id.write(update_vals)
        return {'type': 'ir.actions.act_window_close'}