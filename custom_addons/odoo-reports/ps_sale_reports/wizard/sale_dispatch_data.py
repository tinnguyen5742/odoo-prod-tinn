from datetime import datetime, timedelta

import pytz

from odoo import fields, models
from odoo.exceptions import UserError, ValidationError


class SaleDispatchData(models.TransientModel):
    _inherit = "ps.sale.history.wizard"

    def _get_dispatch_quantities(self, date_from, date_to, line_filters=()):
        """Completed customer movements valued by the originating SO line.

        Kits use native delivered-kit deltas per day, rather than adding the
        quantities of components. Their documents are listed together when
        components for one kit are spread over multiple pickings that day.
        """
        self.ensure_one()
        self.check_access("read")
        if self.company_id not in self.env.companies:
            raise ValidationError("Bạn không có quyền truy cập công ty đã chọn.")
        tz = pytz.timezone(self.env.context.get("tz") or self.env.user.tz or "UTC")
        start = tz.localize(datetime.combine(date_from, datetime.min.time()))
        end = tz.localize(datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
        domain = [
            ("company_id", "=", self.company_id.id), ("state", "=", "done"),
            ("date", ">=", start.astimezone(pytz.UTC).replace(tzinfo=None)),
            ("date", "<", end.astimezone(pytz.UTC).replace(tzinfo=None)),
            "|", ("location_id.usage", "=", "customer"), ("location_dest_id.usage", "=", "customer"),
        ]
        line_domain = [
            ("display_type", "=", False), ("company_id", "=", self.company_id.id),
            ("product_id.type", "=", "consu"), ("move_ids", "any", domain),
        ] + list(line_filters)
        if self.salesperson_id:
            line_domain.append(("order_id.user_id", "=", self.salesperson_id.id))
        # Stock users may read more SOLs than SOs; apply SO rules explicitly.
        orders = self.env["sale.order"].search([
            ("company_id", "=", self.company_id.id), ("order_line", "any", line_domain),
        ], limit=10001)
        lines = self.env["sale.order.line"].with_context(accrual_entry_date=False).search(
            line_domain + [("order_id", "in", orders.ids)], limit=10001,
        )
        moves = self.env["stock.move"].search(
            domain + [("sale_line_id", "in", lines.ids)], order="date, id", limit=10001,
        ) if lines else self.env["stock.move"]
        if max(len(orders), len(lines), len(moves)) > 10000:
            raise UserError("Có hơn 10.000 SO, dòng SO hoặc dịch chuyển. Thu hẹp thời gian hoặc bộ lọc trước khi xuất.")
        by_line = {}
        for move in moves:
            by_line.setdefault(move.sale_line_id.id, self.env["stock.move"])
            by_line[move.sale_line_id.id] |= move
        boms = self.env["mrp.bom"]._bom_find(
            lines.product_id, company_id=self.company_id.id, bom_type="phantom",
        ) if lines else {}
        result = []
        for line in lines:
            events = by_line.get(line.id, self.env["stock.move"])
            used_boms = line.move_ids.bom_line_id.bom_id.filtered(
                lambda bom: bom.type == "phantom" and (bom.product_id == line.product_id
                or (not bom.product_id and bom.product_tmpl_id == line.product_id.product_tmpl_id))
            )
            groups = {}
            if used_boms or boms.get(line.product_id):
                for day in sorted({fields.Datetime.context_timestamp(self, m.date).date() for m in events}):
                    today = line.with_context(accrual_entry_date=fields.Date.to_string(day))
                    prior = line.with_context(accrual_entry_date=fields.Date.to_string(day - timedelta(days=1)))
                    quantity = (today._prepare_qty_delivered().get(today, 0.0)
                                - prior._prepare_qty_delivered().get(prior, 0.0))
                    day_moves = events.filtered(lambda m: fields.Datetime.context_timestamp(self, m.date).date() == day)
                    if quantity:
                        result.append({"line": line, "day": day, "quantity": quantity, "moves": day_moves})
            else:
                outgoing, incoming = line._get_outgoing_incoming_moves()
                for sign, candidates in [(1, outgoing & events), (-1, incoming & events)]:
                    for move in candidates:
                        if sign == -1 and (not move.origin_returned_move_id
                            and not move.location_id._is_outgoing() and line.product_uom_qty > 0
                            and not move.picking_id.return_id):
                            continue
                        day = fields.Datetime.context_timestamp(self, move.date).date()
                        key = (day, move.picking_id.id or -move.id)
                        group = groups.setdefault(key, {"line": line, "day": day, "quantity": 0.0,
                                                        "moves": self.env["stock.move"]})
                        group["quantity"] += sign * move.product_uom._compute_quantity(
                            move.quantity, line.product_uom_id, round=False,
                        )
                        group["moves"] |= move
                result.extend(groups.values())
        for event in result:
            if not event["line"].product_uom_qty:
                raise UserError(f"Dòng SO {event['line'].order_id.name} / {event['line'].product_id.display_name} có số đặt bằng 0. Kiểm tra trước khi tính giá xuất bán.")
        return result
