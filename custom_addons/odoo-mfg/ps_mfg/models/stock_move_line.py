from odoo import api, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    @api.depends("move_id.picking_type_id")
    def _compute_picking_type_id(self):
        # Move nhập thành phẩm không có picking: lấy operation type từ move
        # (giống mrp) để popup Detailed Operations nhận đúng use_create_lots.
        finish_lines = self.filtered(
            lambda ml: not ml.picking_id and ml.move_id.ps_finish_line_id
        )
        for line in finish_lines:
            line.picking_type_id = line.move_id.picking_type_id
        return super(StockMoveLine, self - finish_lines)._compute_picking_type_id()
