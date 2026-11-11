from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    # NOTE: In Odoo ORM, Many2one fields have copy=True by default.
    # We intentionally keep copy=True so that when a picking is partially validated
    # and Odoo splits the move into a backorder move (_split_move / copy),
    # the backorder move automatically retains the link to component_request_line_id
    # and proposal_line_id.
    component_request_line_id = fields.Many2one(
        "ps.mfg.component.request.line",
        string="Component Request Line",
        index=True,
        ondelete="set null",
        help="Reference to the originating MFG Component Request Line.",
    )

    proposal_line_id = fields.Many2one(
        "ps.mfg.proposal.line",
        string="Proposal Line",
        index=True,
        ondelete="set null",
        help="Reference to the originating MFG Proposal Line that planned this transfer.",
    )

    ps_workorder_move_id = fields.Many2one(
        "ps.mfg.workorder.move",
        string="Workorder Move",
        index=True,
        ondelete="set null",
        copy=False,
        help="Shift whose Complete consumed this component (workshop → Production).",
    )

    ps_finish_line_id = fields.Many2one(
        "ps.mfg.proposal.finish.line",
        string="Finished Goods Receipt Line",
        index=True,
        ondelete="set null",
        copy=False,
        help="Finished goods receipt line that receives this product (Production → stock).",
    )

    def _ps_mfg_source_document(self):
        """Chứng từ MFG sinh ra move không picking (ca giao công đoạn / phiếu nhập TP)."""
        self.ensure_one()
        return self.ps_workorder_move_id or self.ps_finish_line_id.proposal_id

    @api.depends("ps_workorder_move_id", "ps_finish_line_id.proposal_id.code")
    def _compute_reference(self):
        # Move MFG không có phiếu: core để trống reference (lấy từ picking).
        # Ca: MO/Mã công đoạn/Ca; nhập TP: mã phiếu nhập TP.
        mfg_moves = self.filtered(
            lambda m: m.ps_workorder_move_id or m.ps_finish_line_id
        )
        super(StockMove, self - mfg_moves)._compute_reference()
        for move in mfg_moves:
            if move.ps_workorder_move_id:
                move.reference = move.ps_workorder_move_id._consumption_origin()
            else:
                move.reference = move.ps_finish_line_id.proposal_id.code

    def action_open_reference(self):
        # Move MFG không có phiếu: mở chứng từ MFG sinh ra nó
        self.ensure_one()
        document = self._ps_mfg_source_document()
        if document and document.has_access("read"):
            return {
                "res_model": document._name,
                "type": "ir.actions.act_window",
                "views": [[False, "form"]],
                "res_id": document.id,
            }
        return super().action_open_reference()

    def _should_be_assigned(self):
        # Như mrp: move MFG không bao giờ bị gom vào picking dù có picking_type
        res = super()._should_be_assigned()
        return bool(res and not (self.ps_workorder_move_id or self.ps_finish_line_id))

    def _prepare_merge_moves_distinct_fields(self):
        # Không gộp move của các dòng YCCP khác nhau (cùng NVL, khác công đoạn):
        # gộp sẽ làm mất liên kết dòng → qty_transferred của dòng bị gộp = 0.
        return super()._prepare_merge_moves_distinct_fields() + [
            "component_request_line_id",
            "proposal_line_id",
            "ps_workorder_move_id",
            "ps_finish_line_id",
        ]
