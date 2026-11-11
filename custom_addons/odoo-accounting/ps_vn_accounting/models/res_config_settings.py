from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    sales_return_debit_account_id = fields.Many2one(
        related="company_id.sales_return_debit_account_id",
        readonly=False,
        check_company=True,
    )
    sales_return_credit_account_id = fields.Many2one(
        related="company_id.sales_return_credit_account_id",
        readonly=False,
        check_company=True,
    )
    account_default_receivable_id = fields.Many2one(
        comodel_name="account.account",
        string="Account Receivable",
        compute="_compute_account_default_receivable_id",
        inverse="_inverse_account_default_receivable_id",
        readonly=False,
        check_company=True,
        domain="[('account_type', '=', 'asset_receivable')]",
        help="Default receivable account set on new customers (typically 131).",
    )
    customer_income_account_id = fields.Many2one(
        related="company_id.customer_income_account_id",
        readonly=False,
        check_company=True,
    )

    @api.model
    def default_get(self, fields_list):
        self.env.company._ps_vn_set_sales_return_default_accounts()
        return super().default_get(fields_list)

    @api.depends("company_id")
    def _compute_account_default_receivable_id(self):
        IrDefault = self.env["ir.default"]
        for setting in self:
            setting.account_default_receivable_id = IrDefault._get(
                "res.partner",
                "property_account_receivable_id",
                company_id=setting.company_id.id,
            )

    def _inverse_account_default_receivable_id(self):
        for setting in self:
            self.env["ir.default"].set(
                "res.partner",
                "property_account_receivable_id",
                setting.account_default_receivable_id.id or False,
                company_id=setting.company_id.id,
            )
