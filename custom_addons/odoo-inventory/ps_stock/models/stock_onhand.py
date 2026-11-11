from collections import defaultdict
from datetime import datetime

import pytz

from odoo import api, fields, models, _


class PsStockOnhand(models.Model):
    """Yearly on-hand ledger: one row per company, location, product, and year.

    A rebuild rewrites the year's movement and leaves the opening balance
    alone. Closing is derived, never stored from a move:

        base_qty       = opening_qty + received_qty
        base_amount    = opening_amount + received_amount
        issued_amount  = base_amount * issued_qty / base_qty   (0 if base_qty is 0)
        closing_qty    = base_qty - issued_qty
        closing_amount = base_amount - issued_amount

    Received quantity and amount come from incoming valued move lines
    (``stock.move._get_in_move_lines`` in ``stock_account``) and from internal
    transfers into the location. Issued quantity comes from outgoing valued
    lines (``_get_out_move_lines``) and from internal transfers out. Issued
    amount is that period average, not ``stock.move.value``.

    An internal transfer is a picked line whose source and destination are
    both valued, so ``is_in``, ``is_out``, and ``move.value`` stay false / 0.
    Quantity leaves the source and enters the destination. The amount is the
    source location's period average, split across destinations by quantity.
    The last destination takes the remainder, so those amounts still add up
    to the value that left the source. Locations that send stock to each
    other in the same year are solved together: each unit cost depends on
    the unit cost of whoever shipped in.

    Example: opening 10 / 100, received 10 / 300, issue 4. The out move may
    be valued at 120 by Odoo, but this row stores issued amount 80
    (400 * 4 / 20) and closing 16 / 320. Transferring those 4 to an empty
    shelf stores received 4 / 80 there. A later receipt in the same year
    changes the average, so every issue and every transfer of that year
    changes with it. One dirty move therefore rebuilds the whole
    (company, product, year).

    ``warehouse_id`` is only a stored related for reporting; a transit
    location with no warehouse still gets a row.
    """

    _name = 'ps.stock.onhand'
    _description = 'Stock Onhand'
    _order = 'year desc, product_id'
    _check_company_auto = True

    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company)
    location_id = fields.Many2one('stock.location', 'Location', required=True, check_company=True)
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        related='location_id.warehouse_id',
        store=True,
        readonly=True,
        check_company=True,
    )
    # Calendar year in the company partner's timezone, not the UTC year of move.date.
    year = fields.Integer(string='Year', required=True)
    # Grain stays the year: issued amount is an average over the whole year.
    # month = fields.Integer(string='Month', required=True)
    product_id = fields.Many2one('product.product', 'Product', required=True)
    # Not recomputed. Carried from the previous year or typed by hand, and
    # kept when the year's movement is rebuilt.
    opening_quantity = fields.Float(string='Opening Quantity', required=True, default=0.0)
    opening_amount = fields.Float(string='Opening Amount', required=True, default=0.0)
    # Incoming valued lines of this year. Amount is move.value split onto
    # each destination location.
    received_quantity = fields.Float(string='Received Quantity', required=True, default=0.0)
    received_amount = fields.Float(string='Received Amount', required=True, default=0.0)
    # Outgoing valued lines. Amount is the period average, not the out move's value.
    issued_quantity = fields.Float(string='Issued Quantity', required=True, default=0.0)
    issued_amount = fields.Float(string='Issued Amount', required=True, default=0.0)
    closing_quantity = fields.Float(string='Closing Quantity', required=True, default=0.0)
    closing_amount = fields.Float(string='Closing Amount', required=True, default=0.0)

    _stock_onhand_location_unique = models.Constraint(
        'unique(company_id, location_id, product_id, year)',
        _('Product, location, and year must be unique per company.'),
    )

    @api.model
    def _recompute_buckets(self, moves):
        """Mark (company, product, year) periods dirty and rebuild each one.

        ``moves`` only names the periods. The figures come from every done
        move of that product in that year, because issued amount depends on
        the year's receipts and issues together. A value correction
        (``_set_value``) and a backdated done move dirty a period the same way.

        Done moves of storable products count when they enter valued stock,
        leave it, or move between two valued locations. An internal transfer
        is neither ``is_in`` nor ``is_out``; it still names the period.
        """
        moves = moves.filtered(lambda move: self._counts_for_onhand(move))
        if not moves:
            return self.browse()

        periods = {
            (move.company_id.id, move.product_id.id, self._move_year(move))
            for move in moves
        }
        rows = self.browse()
        Company = self.env['res.company']
        Product = self.env['product.product']
        for company_id, product_id, year in periods:
            company = Company.browse(company_id)
            product = Product.browse(product_id)
            rows |= self._recompute_period(company, product, year)
        return rows

    @api.model
    def _recompute_period(self, company, product, year):
        """Rebuild every location row of one company, product, and year.

        The search is every done move in the company-timezone year, not the
        moves that triggered the recompute. Locations that no longer have a
        receipt, issue, or internal transfer are zeroed but kept, so an
        opening balance survives a cancelled, redated, or revalued move.
        """
        start, end = self._period_bounds(company, year)
        candidates = self.env['stock.move'].sudo().search([
            ('state', '=', 'done'),
            ('company_id', '=', company.id),
            ('product_id', '=', product.id),
            ('date', '>=', start),
            ('date', '<', end),
        ])
        # location -> [received_qty, received_amount, issued_qty]
        # Issued amount is not accumulated here; it is the period average.
        buckets = defaultdict(lambda: [0.0, 0.0, 0.0])
        # (source location id, destination location id) -> quantity
        internal_qty = defaultdict(float)
        internal_locations = {}
        for move in candidates:
            if move.is_in:
                for location, qty, amount in self._split_received(move):
                    bucket = buckets[location]
                    bucket[0] += qty
                    bucket[1] += amount
            if move.is_out:
                for location, qty in self._iter_issued(move):
                    buckets[location][2] += qty
            for source, dest, qty in self._iter_internal(move):
                internal_locations[source.id] = source
                internal_locations[dest.id] = dest
                internal_qty[(source.id, dest.id)] += qty

        # Validation may run without stock-manager rights. with_company makes
        # currency rounding use this company's currency.
        Onhand = self.sudo().with_company(company)
        existing = Onhand.search([
            ('company_id', '=', company.id),
            ('product_id', '=', product.id),
            ('year', '=', year),
        ])
        existing_by_location = {row.location_id.id: row for row in existing}
        if internal_qty:
            openings = {
                row.location_id.id: (row.opening_quantity, row.opening_amount)
                for row in existing
            }
            self._apply_internal_transfers(
                company, product, buckets, internal_qty, internal_locations, openings,
            )
        touched = Onhand.browse()
        seen_location_ids = set()
        for location, (received_qty, received_amount, issued_qty) in buckets.items():
            seen_location_ids.add(location.id)
            row = existing_by_location.get(location.id)
            opening_qty = row.opening_quantity if row else 0.0
            opening_amount = row.opening_amount if row else 0.0
            vals = self._movement_vals(
                company, product, opening_qty, opening_amount,
                received_qty, received_amount, issued_qty,
            )
            if row:
                row.write(vals)
                touched |= row
                continue
            # Nothing moved and no row yet: do not create an empty line.
            if self._movement_is_zero(company, product, vals):
                continue
            touched |= Onhand.create({
                'company_id': company.id,
                'location_id': location.id,
                'product_id': product.id,
                'year': year,
                'opening_quantity': 0.0,
                'opening_amount': 0.0,
                **vals,
            })

        # Had a row, but no in/out line landed here this year. Drop the stale
        # movement and keep the opening balance.
        for row in existing:
            if row.location_id.id in seen_location_ids:
                continue
            row.write(self._movement_vals(
                company, product, row.opening_quantity, row.opening_amount, 0.0, 0.0, 0.0,
            ))
            touched |= row
        return touched

    @api.model
    def _split_received(self, move):
        """Split one incoming move's value across its destination locations.

        ``_get_in_move_lines`` (``stock_account``) returns the picked lines
        whose source location is not valued and whose destination is.
        ``move.value`` is a single amount on the move, while those lines can
        land in different destinations, so the amount is shared by quantity.

        Each share is currency-rounded. The last line takes whatever remains,
        so the location amounts still add up to ``move.value``.
        """
        lines = move._get_in_move_lines()
        quantities = [
            (line, line.quantity_product_uom)
            for line in lines
            if not move.product_id.uom_id.is_zero(line.quantity_product_uom)
        ]
        total_qty = sum(qty for _line, qty in quantities)
        if move.product_id.uom_id.is_zero(total_qty):
            return []
        currency = move.company_id.currency_id
        remaining = move.value
        last = len(quantities) - 1
        allocated = []
        for index, (line, qty) in enumerate(quantities):
            if index == last:
                amount = currency.round(remaining)
            else:
                amount = currency.round(move.value * qty / total_qty)
                remaining -= amount
            allocated.append((line.location_dest_id, qty, amount))
        return allocated

    @api.model
    def _iter_issued(self, move):
        """Yield (source location, quantity) for each outgoing valued line.

        ``_get_out_move_lines`` is the mirror of ``_get_in_move_lines``: picked
        lines that leave a valued location. Only the quantity is kept. The
        issued amount is the location's period average, computed once the
        whole year has been summed.
        """
        for line in move._get_out_move_lines():
            qty = line.quantity_product_uom
            if move.product_id.uom_id.is_zero(qty):
                continue
            yield line.location_id, qty

    @api.model
    def _counts_for_onhand(self, move):
        """True when a done move should dirty its on-hand period."""
        if move.state != 'done' or not move.product_id.is_storable:
            return False
        if move.is_in or move.is_out:
            return True
        for _source, _dest, _qty in self._iter_internal(move):
            return True
        return False

    @api.model
    def _iter_internal(self, move):
        """Yield (source, destination, quantity) for each internal valued line.

        Both locations pass ``stock.location._should_be_valued`` (company set,
        usage internal or transit). Consignment lines, whose owner is not the
        company partner, are skipped the same way as incoming and outgoing
        valuation. ``move.value`` is not used: it is zero for these lines.
        """
        if move.state != 'done' or not move.product_id.is_storable:
            return
        uom = move.product_id.uom_id
        for line in move.move_line_ids:
            if not line.picked or line._should_exclude_for_valuation():
                continue
            source = line.location_id
            dest = line.location_dest_id
            if source == dest:
                continue
            if not (source._should_be_valued() and dest._should_be_valued()):
                continue
            qty = line.quantity_product_uom
            if uom.is_zero(qty):
                continue
            yield source, dest, qty

    @api.model
    def _apply_internal_transfers(self, company, product, buckets, internal_qty, locations, openings):
        """Add internal-transfer quantity and amount onto ``buckets``.

        ``internal_qty`` maps ``(source_id, dest_id)`` to a quantity.
        ``buckets`` still holds only external receipts and issues. Amounts
        are priced from each source's period average, in an order where a
        location is priced after the locations that ship to it.
        """
        uom = product.uom_id
        edges = {
            key: qty
            for key, qty in internal_qty.items()
            if not uom.is_zero(qty)
        }
        if not edges:
            return

        external = {}
        records = {}
        for location, (received_qty, received_amount, issued_qty) in buckets.items():
            external[location.id] = (received_qty, received_amount, issued_qty)
            records[location.id] = location
        for location in locations.values():
            records.setdefault(location.id, location)

        edge_amount = self._internal_transfer_amounts(
            company, product, edges, external, openings,
        )
        merged = defaultdict(lambda: [0.0, 0.0, 0.0])
        for location_id, (received_qty, received_amount, issued_qty) in external.items():
            bucket = merged[location_id]
            bucket[0] += received_qty
            bucket[1] += received_amount
            bucket[2] += issued_qty
        for (source_id, dest_id), qty in edges.items():
            merged[dest_id][0] += qty
            merged[source_id][2] += qty
        for (_source_id, dest_id), amount in edge_amount.items():
            merged[dest_id][1] += amount

        buckets.clear()
        for location_id, vals in merged.items():
            buckets[records[location_id]] = vals

    @api.model
    def _internal_transfer_amounts(self, company, product, edges, external, openings):
        """Return ``{(source_id, dest_id): amount}`` for one product-year.

        Value flows along transfer edges. Strongly connected components are
        priced source-first. Inside a component the unit costs solve

            base_qty * unit − Σ incoming_qty * source_unit
                = opening_amount + external_received_amount + outside_transfer_amount

        so a two-way transfer in the same year has one average. Each source
        then splits its transfer share of ``issued_amount`` across destinations
        by quantity. The last destination (highest location id) keeps the
        rounding remainder.
        """
        incoming = defaultdict(list)
        outgoing = defaultdict(list)
        for (source_id, dest_id), qty in edges.items():
            incoming[dest_id].append((source_id, qty))
            outgoing[source_id].append((dest_id, qty))
        for source_id in outgoing:
            outgoing[source_id].sort(key=lambda item: item[0])

        successors = {
            source_id: [dest_id for dest_id, _qty in dests]
            for source_id, dests in outgoing.items()
        }
        nodes = set(incoming) | set(outgoing)
        # Tarjan emits sinks first. Pricing needs the source component first.
        components = reversed(self._strongly_connected_components(nodes, successors))

        edge_amount = {}
        for component in components:
            self._price_transfer_component(
                company, product, component, incoming, outgoing,
                external, openings, edge_amount,
            )
        return edge_amount

    @api.model
    def _price_transfer_component(
        self, company, product, component, incoming, outgoing,
        external, openings, edge_amount,
    ):
        """Write this component's outgoing edge amounts into ``edge_amount``.

        Inflows from earlier components are already in ``edge_amount``. The
        linear seed handles cycles; the following passes replace each seed
        with a currency-rounded split of the source's issued amount. A pass
        that changes nothing is the fixed point. The iteration cap keeps a
        one-unit rounding cycle from running on.
        """
        units = self._transfer_component_units(
            product, component, incoming, external, openings, edge_amount,
        )
        for source_id in component:
            unit = units.get(source_id, 0.0)
            for dest_id, qty in outgoing.get(source_id, ()):
                edge_amount[(source_id, dest_id)] = qty * unit

        currency = company.currency_id
        for _step in range(len(component) + 2):
            snapshot = dict(edge_amount)
            updates = {}
            for source_id in sorted(component):
                received_extra = 0.0
                for pred_id, _qty in incoming.get(source_id, ()):
                    received_extra += snapshot.get((pred_id, source_id), 0.0)
                opening_qty, opening_amount = openings.get(source_id, (0.0, 0.0))
                received_qty, received_amount, issued_external = external.get(source_id, (0.0, 0.0, 0.0))
                transfer_in_qty = sum(qty for _pred, qty in incoming.get(source_id, ()))
                transfer_out = outgoing.get(source_id, ())
                transfer_out_qty = sum(qty for _dest, qty in transfer_out)
                vals = self._movement_vals(
                    company, product, opening_qty, opening_amount,
                    received_qty + transfer_in_qty,
                    received_amount + received_extra,
                    issued_external + transfer_out_qty,
                )
                amounts = self._split_transfer_amount(
                    company, product, vals['issued_amount'],
                    issued_external + transfer_out_qty,
                    [qty for _dest, qty in transfer_out],
                )
                for (dest_id, _qty), amount in zip(transfer_out, amounts):
                    updates[(source_id, dest_id)] = amount
            if all(
                currency.compare_amounts(amount, snapshot.get(key, 0.0)) == 0
                for key, amount in updates.items()
            ):
                edge_amount.update(updates)
                break
            edge_amount.update(updates)

    @api.model
    def _transfer_component_units(self, product, component, incoming, external, openings, edge_amount):
        """Unit cost of each location in one strongly connected component."""
        member = set(component)
        uom = product.uom_id
        base_qty = {}
        rhs = {}
        internal_incoming = {}
        for location_id in component:
            opening_qty, opening_amount = openings.get(location_id, (0.0, 0.0))
            received_qty, received_amount, _issued = external.get(location_id, (0.0, 0.0, 0.0))
            transfer_in_qty = 0.0
            outside_amount = 0.0
            internal = []
            for source_id, qty in incoming.get(location_id, ()):
                transfer_in_qty += qty
                if source_id in member:
                    internal.append((source_id, qty))
                else:
                    outside_amount += edge_amount.get((source_id, location_id), 0.0)
            base_qty[location_id] = opening_qty + received_qty + transfer_in_qty
            rhs[location_id] = opening_amount + received_amount + outside_amount
            internal_incoming[location_id] = internal

        active = [
            location_id for location_id in component
            if not uom.is_zero(base_qty[location_id])
        ]
        units = dict.fromkeys(component, 0.0)
        index = {location_id: position for position, location_id in enumerate(active)}
        size = len(active)
        if not size:
            return units
        matrix = [[0.0] * size for _index in range(size)]
        vector = [0.0] * size
        for location_id, position in index.items():
            matrix[position][position] = base_qty[location_id]
            vector[position] = rhs[location_id]
            for source_id, qty in internal_incoming[location_id]:
                source_position = index.get(source_id)
                if source_position is not None:
                    matrix[position][source_position] -= qty
        solved = self._solve_linear_system(matrix, vector, uom)
        for location_id, position in index.items():
            units[location_id] = solved[position]
        return units

    @api.model
    def _split_transfer_amount(self, company, product, issued_amount, issued_qty, quantities):
        """Split the transfer share of ``issued_amount`` across ``quantities``.

        The share is ``issued_amount * transferred / issued``. Sales keep the
        rest. The last quantity takes whatever rounding remains.
        """
        currency = company.currency_id
        count = len(quantities)
        if not count:
            return []
        transferred = sum(quantities)
        if (
            product.uom_id.is_zero(issued_qty)
            or product.uom_id.is_zero(transferred)
            or currency.is_zero(issued_amount)
        ):
            return [0.0] * count
        total = currency.round(issued_amount * transferred / issued_qty)
        amounts = []
        remaining = total
        last = count - 1
        for index, qty in enumerate(quantities):
            if index == last:
                amounts.append(currency.round(remaining))
            else:
                share = currency.round(total * qty / transferred)
                remaining -= share
                amounts.append(share)
        return amounts

    @api.model
    def _solve_linear_system(self, matrix, vector, uom):
        """Solve ``Ax = b``. A singular column's variable stays 0.

        Pure transfer cycles have a free unit cost and no external value.
        Setting that variable to 0 keeps the closing amount at 0.
        """
        size = len(vector)
        if not size:
            return []
        augmented = [list(row) + [vector[index]] for index, row in enumerate(matrix)]
        pivot_column = [-1] * size
        row = 0
        for column in range(size):
            if row >= size:
                break
            pivot = max(range(row, size), key=lambda index: abs(augmented[index][column]))
            if uom.is_zero(augmented[pivot][column]):
                continue
            augmented[row], augmented[pivot] = augmented[pivot], augmented[row]
            scale = augmented[row][column]
            for index in range(column, size + 1):
                augmented[row][index] /= scale
            for other in range(size):
                if other == row:
                    continue
                factor = augmented[other][column]
                if not factor:
                    continue
                for index in range(column, size + 1):
                    augmented[other][index] -= factor * augmented[row][index]
            pivot_column[row] = column
            row += 1
        solution = [0.0] * size
        for index, column in enumerate(pivot_column):
            if column >= 0:
                solution[column] = augmented[index][size]
        return solution

    @api.model
    def _strongly_connected_components(self, nodes, successors):
        """Return strongly connected components, sinks first (Tarjan)."""
        index = 0
        stack = []
        on_stack = set()
        indices = {}
        lowlink = {}
        components = []

        def visit(node):
            nonlocal index
            indices[node] = index
            lowlink[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)
            for nxt in successors.get(node, ()):
                if nxt not in indices:
                    visit(nxt)
                    lowlink[node] = min(lowlink[node], lowlink[nxt])
                elif nxt in on_stack:
                    lowlink[node] = min(lowlink[node], indices[nxt])
            if lowlink[node] == indices[node]:
                component = []
                while True:
                    nxt = stack.pop()
                    on_stack.discard(nxt)
                    component.append(nxt)
                    if nxt == node:
                        break
                components.append(component)

        for node in nodes:
            if node not in indices:
                visit(node)
        return components

    @api.model
    def _movement_vals(self, company, product, opening_qty, opening_amount, received_qty, received_amount, issued_qty):
        """Return received, issued, and closing figures for one location.

        Issued amount prices the issued quantity at the average of the opening
        balance plus this year's receipts. It is not the sum of outgoing
        ``move.value``. Quantities are rounded with the product UoM and
        amounts with the company currency before the division, so the stored
        closing matches the stored base minus the stored issue.
        """
        uom = product.uom_id
        currency = company.currency_id
        received_qty = uom.round(received_qty)
        issued_qty = uom.round(issued_qty)
        received_amount = currency.round(received_amount)
        base_qty = uom.round(opening_qty + received_qty)
        base_amount = currency.round(opening_amount + received_amount)
        if uom.is_zero(base_qty):
            issued_amount = 0.0
        else:
            issued_amount = currency.round(base_amount * issued_qty / base_qty)
        return {
            'received_quantity': received_qty,
            'received_amount': received_amount,
            'issued_quantity': issued_qty,
            'issued_amount': issued_amount,
            'closing_quantity': uom.round(base_qty - issued_qty),
            'closing_amount': currency.round(base_amount - issued_amount),
        }

    @api.model
    def _movement_is_zero(self, company, product, vals):
        """True when a brand-new row would show no movement.

        Existing rows are still updated when their movement drops to zero,
        because they may hold an opening balance. Issued amount is omitted:
        a zero base quantity forces it to zero in ``_movement_vals``.
        """
        return (
            product.uom_id.is_zero(vals['received_quantity'])
            and product.uom_id.is_zero(vals['issued_quantity'])
            and company.currency_id.is_zero(vals['received_amount'])
        )

    @api.model
    def _company_tz(self, company):
        """Timezone that decides which calendar year a move belongs to."""
        return company.partner_id.tz or 'UTC'

    @api.model
    def _move_year(self, move):
        """Company-local year of ``move.date``.

        ``stock.move.date`` is naive UTC. A move stored as 2025-12-31 20:00
        is already 2026 in Asia/Ho_Chi_Minh, so the year cannot be read off
        the UTC timestamp.
        """
        moment = move.date or fields.Datetime.now()
        localized = fields.Datetime.context_timestamp(
            move.with_context(tz=self._company_tz(move.company_id)),
            moment,
        )
        return localized.year

    @api.model
    def _period_bounds(self, company, year):
        """Naive UTC ``[start, end)`` covering the company-local calendar year.

        The domain on ``stock.move.date`` compares naive UTC datetimes, so
        local 1 January is converted back to UTC and then stripped of tzinfo.
        """
        timezone = pytz.timezone(self._company_tz(company))
        start_local = timezone.localize(datetime(year, 1, 1))
        end_local = timezone.localize(datetime(year + 1, 1, 1))
        start = start_local.astimezone(pytz.utc).replace(tzinfo=None)
        end = end_local.astimezone(pytz.utc).replace(tzinfo=None)
        return start, end
