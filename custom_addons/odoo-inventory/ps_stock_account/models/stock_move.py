from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_valuation_warehouse(self):
        """Warehouse on the valued side of the move: dest for IN, source for OUT."""
        self.ensure_one()
        if self.is_in or self._is_in():
            return self.location_dest_id.warehouse_id
        if self.is_out or self._is_out():
            return self.location_id.warehouse_id
        return (
            self.location_dest_id.warehouse_id
            or self.location_id.warehouse_id
            or self.picking_type_id.warehouse_id
        )

    def _get_warehouse_cost_method(self):
        self.ensure_one()
        warehouse = self._get_valuation_warehouse()
        if not warehouse:
            return False
        return warehouse.with_company(self.company_id).x_property_cost_method or False

    def _set_value(self, correction_quantity=None):
        for method, moves in self.grouped(lambda move: move._get_warehouse_cost_method()).items():
            if method:
                moves = moves.with_context(force_cost_method=method)
            super(StockMove, moves)._set_value(correction_quantity)
        self._ps_recompute_onhand()

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        moves_out = moves.filtered(lambda move: move.is_out)
        for method, group in moves_out.grouped(lambda move: move._get_warehouse_cost_method()).items():
            products = group.product_id
            if method:
                products = products.with_context(force_cost_method=method)
            products.filtered(
                lambda product: product.cost_method == 'fifo'
                or (product.cost_method == 'average' and product.lot_valuated)
            )._update_standard_price()
        moves._ps_recompute_onhand()
        return moves

    def _ps_recompute_onhand(self):
        done = self.filtered(lambda move: move.state == 'done')
        if done:
            self.env['ps.stock.onhand']._recompute_buckets(done)
