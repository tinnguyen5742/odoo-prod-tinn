from odoo import fields, models


class AccountMove(models.Model):
    """Kế thừa account.move để thêm thông tin hóa đơn điện tử Việt Nam."""
    _inherit = "account.move"

    # Trạng thái xuất hóa đơn điện tử
    x_vn_einvoice_status = fields.Selection(
        selection=[
            ("not_issued", "Not Issued"),
            ("processing", "Processing"),
            ("issued", "Issued"),
            ("failed", "Failed"),
        ],
        string="E-Invoice Status",
        default="not_issued",
        tracking=True,
        copy=False,
        help="E-Invoice issuance status of the VAT invoice.",
    )
    # Ký hiệu hóa đơn
    x_vn_invoice_symbol = fields.Char(
        string="Invoice Symbol",
        tracking=True,
        copy=False,
    )
    # Tỷ giá hải quan
    x_vn_customs_rate = fields.Float(
        string="Customs Exchange Rate",
        digits=(12, 4),
        tracking=True,
        copy=False,
    )
    # Số tờ khai hải quan
    x_vn_declaration_no = fields.Char(
        string="Declaration Number",
        tracking=True,
        copy=False,
    )
