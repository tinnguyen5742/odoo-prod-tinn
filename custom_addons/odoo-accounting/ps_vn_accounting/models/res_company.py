from odoo import api, fields, models

from odoo.addons.account.models.product import ACCOUNT_DOMAIN


class ResCompany(models.Model):
    _inherit = "res.company"

    sales_return_debit_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Sales Return Debit Account",
        check_company=True,
        domain=ACCOUNT_DOMAIN,
        help="Debit account used when recording a customer goods return (typically 521).",
    )
    sales_return_credit_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Sales Return Credit Account",
        check_company=True,
        domain="[('account_type', '=', 'asset_receivable')]",
        help="Credit account used when recording a customer goods return (typically 131).",
    )
    customer_income_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Customer Income Account",
        check_company=True,
        domain=ACCOUNT_DOMAIN,
        help="Default income account used on customer sales (typically 511).",
    )

    def _search_account_by_code(self, code):
        """Find an account by exact code, then by prefix (521 / 5211)."""
        self.ensure_one()
        Account = self.env["account.account"].with_company(self)
        domain = [
            *Account._check_company_domain(self),
            ("active", "=", True),
        ]
        account = Account.search(domain + [("code", "=", code)], limit=1)
        if account:
            return account
        return Account.search(
            domain + [("code", "=like", f"{code}%")],
            order="code",
            limit=1,
        )

    def _ps_vn_set_sales_return_default_accounts(self):
        """Fill empty return accounts with 521 (debit) and 131 (credit)."""
        for company in self:
            vals = {}
            if not company.sales_return_debit_account_id:
                debit = company._search_account_by_code("521")
                if debit:
                    vals["sales_return_debit_account_id"] = debit.id
            if not company.sales_return_credit_account_id:
                credit = company._search_account_by_code("131")
                if credit:
                    vals["sales_return_credit_account_id"] = credit.id
            if vals:
                company.write(vals)

    def _get_sales_return_debit_account(self):
        self.ensure_one()
        return self.sales_return_debit_account_id or self._search_account_by_code("521")

    def _get_sales_return_credit_account(self):
        self.ensure_one()
        return self.sales_return_credit_account_id or self._search_account_by_code("131")

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._ps_vn_set_sales_return_default_accounts()
        return companies
