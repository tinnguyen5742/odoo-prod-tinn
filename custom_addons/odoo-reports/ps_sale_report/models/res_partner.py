from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    ps_sale_credit_note = fields.Text(
        "Ghi chú công nợ bán ra", company_dependent=True,
        groups="account.group_account_invoice,account.group_account_readonly",
        help="Ghi chú riêng theo công ty, dùng trong Bảng kê thời hạn công nợ bán ra.",
    )
