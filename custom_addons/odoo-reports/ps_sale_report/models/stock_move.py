from odoo import api, fields, models
from odoo.exceptions import ValidationError


class StockMove(models.Model):
    _inherit = "stock.move"

    ps_execution_request_ref = fields.Char("Số đề nghị xuất", copy=False)
    ps_execution_request_qty = fields.Float(
        "SL đề nghị xuất", digits="Product Unit", copy=False,
        help="Phần số lượng đề nghị phân bổ cho dòng này, theo ĐVT của dịch chuyển kho.",
    )

    @api.constrains("ps_execution_request_ref", "ps_execution_request_qty")
    def _check_execution_request(self):
        for move in self:
            reference = (move.ps_execution_request_ref or "").strip()
            quantity = move.ps_execution_request_qty
            if quantity < 0:
                raise ValidationError("Số lượng đề nghị không được âm.")
            if reference and quantity <= 0:
                raise ValidationError("Có số đề nghị thì phải nhập số lượng đề nghị lớn hơn 0.")
            if quantity > 0 and not reference:
                raise ValidationError("Hãy nhập số đề nghị xuất.")

    def _prepare_merge_moves_distinct_fields(self):
        return super()._prepare_merge_moves_distinct_fields() + ["ps_execution_request_ref"]

    def _merge_moves_fields(self):
        values = super()._merge_moves_fields()
        # Never discard allocated request quantities when stock merges same-ref moves.
        values["ps_execution_request_qty"] = sum(self.mapped("ps_execution_request_qty"))
        return values
