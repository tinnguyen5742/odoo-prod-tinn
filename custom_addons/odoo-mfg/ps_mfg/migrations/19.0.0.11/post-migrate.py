"""Finished goods receipts now use picking-less stock moves.

Draft/submitted receipt lines get their Production → destination move. The
legacy single ``lot_id`` of a tracked line becomes the move line lot. Approved
receipts keep their legacy draft ``picking_ids``.
"""

from odoo import SUPERUSER_ID, api
from odoo.fields import Command


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    lines = env["ps.mfg.proposal.finish.line"].search(
        [
            ("proposal_id.state", "in", ("draft", "submitted")),
            ("proposal_id.picking_ids", "=", False),
            ("move_id", "=", False),
        ]
    )
    lines._sync_finish_move()
    for line in lines.filtered(lambda l: l.move_id and l.lot_id):
        move = line.move_id
        # Move từ Production đã được reserve sẵn 1 move line chưa có lot: thay bằng lot cũ
        move.move_line_ids.unlink()
        move.move_line_ids = [
            Command.create(
                {
                    "lot_id": line.lot_id.id,
                    "quantity": line.finish_qty,
                    "product_id": move.product_id.id,
                    "product_uom_id": move.product_uom.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                }
            )
        ]
