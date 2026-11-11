from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPsStockOnhand(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')
        cls.customer_location = cls.env.ref('stock.stock_location_customers')
        cls.uom = cls.env.ref('uom.product_uom_unit')
        cls.product = cls.env['product.product'].with_company(cls.company).create({
            'name': 'Onhand AVCO',
            'is_storable': True,
            'uom_id': cls.uom.id,
            'standard_price': 10.0,
            'list_price': 20.0,
        })

    def _onhand(self, product, location):
        return self.env['ps.stock.onhand'].search([
            ('company_id', '=', self.company.id),
            ('product_id', '=', product.id),
            ('location_id', '=', location.id),
        ])

    def _make_in_move(self, product, quantity, unit_cost, location_dest=None):
        location_dest = location_dest or self.stock_location
        move = self.env['stock.move'].create({
            'product_id': product.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': location_dest.id,
            'product_uom': self.uom.id,
            'product_uom_qty': quantity,
            'picking_type_id': self.warehouse.in_type_id.id,
            'price_unit': unit_cost,
            'value_manual': unit_cost * quantity,
        })
        move._action_confirm()
        move._action_assign()
        move.picked = True
        move._action_done()
        return move

    def _make_out_move(self, product, quantity, location=None):
        location = location or self.stock_location
        move = self.env['stock.move'].create({
            'product_id': product.id,
            'location_id': location.id,
            'location_dest_id': self.customer_location.id,
            'product_uom': self.uom.id,
            'product_uom_qty': quantity,
            'picking_type_id': self.warehouse.out_type_id.id,
        })
        move._action_confirm()
        move._action_assign()
        move.picked = True
        move._action_done()
        return move

    def _make_internal_move(self, product, quantity, location, location_dest):
        move = self.env['stock.move'].create({
            'product_id': product.id,
            'location_id': location.id,
            'location_dest_id': location_dest.id,
            'product_uom': self.uom.id,
            'product_uom_qty': quantity,
            'picking_type_id': self.warehouse.int_type_id.id,
        })
        move._action_confirm()
        move._action_assign()
        move.picked = True
        move._action_done()
        return move

    def _shelf(self, name):
        return self.env['stock.location'].create({
            'name': name,
            'usage': 'internal',
            'location_id': self.stock_location.id,
            'company_id': self.company.id,
        })

    def test_period_average_keeps_opening_and_ignores_out_move_value(self):
        move_in = self._make_in_move(self.product, 10, 30)

        row = self._onhand(self.product, self.stock_location)
        self.assertEqual(len(row), 1)
        self.assertEqual(row.warehouse_id, self.stock_location.warehouse_id)
        self.assertEqual(row.received_quantity, 10)
        self.assertEqual(row.received_amount, 300)
        self.assertEqual(row.issued_quantity, 0)
        self.assertEqual(row.closing_quantity, 10)
        self.assertEqual(row.closing_amount, 300)

        row.write({'opening_quantity': 10, 'opening_amount': 100})
        self.env['ps.stock.onhand']._recompute_buckets(move_in)
        self.assertEqual(row.opening_quantity, 10)
        self.assertEqual(row.opening_amount, 100)
        self.assertEqual(row.closing_quantity, 20)
        self.assertEqual(row.closing_amount, 400)

        move_out = self._make_out_move(self.product, 4)
        self.assertEqual(move_out.value, 120)
        self.assertEqual(row.issued_quantity, 4)
        self.assertEqual(row.issued_amount, 80)
        self.assertEqual(row.closing_quantity, 16)
        self.assertEqual(row.closing_amount, 320)

    def test_value_change_rebuilds_received_amount(self):
        move = self._make_in_move(self.product, 10, 10)
        row = self._onhand(self.product, self.stock_location)
        self.assertEqual(row.received_amount, 100)

        move.value_manual = 250
        self.assertEqual(row.received_amount, 250)
        self.assertEqual(row.closing_quantity, 10)
        self.assertEqual(row.closing_amount, 250)

    def test_locations_are_separate_buckets(self):
        shelf = self.env['stock.location'].create({
            'name': 'Shelf A',
            'usage': 'internal',
            'location_id': self.stock_location.id,
            'company_id': self.company.id,
        })
        self._make_in_move(self.product, 5, 10)
        self._make_in_move(self.product, 7, 40, location_dest=shelf)

        stock_row = self._onhand(self.product, self.stock_location)
        shelf_row = self._onhand(self.product, shelf)
        self.assertEqual(stock_row.received_quantity, 5)
        self.assertEqual(stock_row.received_amount, 50)
        self.assertEqual(shelf_row.received_quantity, 7)
        self.assertEqual(shelf_row.received_amount, 280)
        self.assertEqual(shelf_row.warehouse_id, self.warehouse)

    def test_internal_transfer_posts_source_average_on_dest(self):
        self._make_in_move(self.product, 10, 20)
        row = self._onhand(self.product, self.stock_location)
        shelf = self._shelf('Shelf B')
        move = self._make_internal_move(self.product, 2, self.stock_location, shelf)

        self.assertFalse(move.is_in)
        self.assertFalse(move.is_out)
        self.assertTrue(self.company.currency_id.is_zero(move.value))
        self.assertEqual(row.received_quantity, 10)
        self.assertEqual(row.received_amount, 200)
        self.assertEqual(row.issued_quantity, 2)
        self.assertEqual(row.issued_amount, 40)
        self.assertEqual(row.closing_quantity, 8)
        self.assertEqual(row.closing_amount, 160)

        shelf_row = self._onhand(self.product, shelf)
        self.assertEqual(shelf_row.received_quantity, 2)
        self.assertEqual(shelf_row.received_amount, 40)
        self.assertEqual(shelf_row.issued_quantity, 0)
        self.assertEqual(shelf_row.closing_quantity, 2)
        self.assertEqual(shelf_row.closing_amount, 40)
        self.assertEqual(shelf_row.warehouse_id, self.warehouse)

    def test_transfer_and_sale_share_one_average(self):
        move_in = self._make_in_move(self.product, 10, 30)
        row = self._onhand(self.product, self.stock_location)
        row.write({'opening_quantity': 10, 'opening_amount': 100})
        self.env['ps.stock.onhand']._recompute_buckets(move_in)
        shelf = self._shelf('Shelf Share')
        self._make_internal_move(self.product, 4, self.stock_location, shelf)
        self._make_out_move(self.product, 4)

        self.assertEqual(row.opening_quantity, 10)
        self.assertEqual(row.opening_amount, 100)
        self.assertEqual(row.issued_quantity, 8)
        self.assertEqual(row.issued_amount, 160)
        self.assertEqual(row.closing_quantity, 12)
        self.assertEqual(row.closing_amount, 240)
        shelf_row = self._onhand(self.product, shelf)
        self.assertEqual(shelf_row.received_quantity, 4)
        self.assertEqual(shelf_row.received_amount, 80)
        self.assertEqual(shelf_row.closing_amount, 80)

    def test_issue_from_destination_uses_transferred_amount(self):
        self._make_in_move(self.product, 10, 20)
        shelf = self._shelf('Shelf C')
        self._make_internal_move(self.product, 4, self.stock_location, shelf)
        self._make_out_move(self.product, 1, location=shelf)

        stock_row = self._onhand(self.product, self.stock_location)
        shelf_row = self._onhand(self.product, shelf)
        self.assertEqual(stock_row.issued_quantity, 4)
        self.assertEqual(stock_row.issued_amount, 80)
        self.assertEqual(stock_row.closing_quantity, 6)
        self.assertEqual(stock_row.closing_amount, 120)
        self.assertEqual(shelf_row.received_quantity, 4)
        self.assertEqual(shelf_row.received_amount, 80)
        self.assertEqual(shelf_row.issued_quantity, 1)
        self.assertEqual(shelf_row.issued_amount, 20)
        self.assertEqual(shelf_row.closing_quantity, 3)
        self.assertEqual(shelf_row.closing_amount, 60)

    def test_later_receipt_rebuilds_transfer_amount(self):
        self._make_in_move(self.product, 10, 10)
        shelf = self._shelf('Shelf D')
        self._make_internal_move(self.product, 2, self.stock_location, shelf)
        self._make_in_move(self.product, 10, 30)

        stock_row = self._onhand(self.product, self.stock_location)
        shelf_row = self._onhand(self.product, shelf)
        self.assertEqual(stock_row.received_quantity, 20)
        self.assertEqual(stock_row.received_amount, 400)
        self.assertEqual(stock_row.issued_quantity, 2)
        self.assertEqual(stock_row.issued_amount, 40)
        self.assertEqual(stock_row.closing_amount, 360)
        self.assertEqual(shelf_row.received_quantity, 2)
        self.assertEqual(shelf_row.received_amount, 40)
        self.assertEqual(shelf_row.closing_amount, 40)

    def test_return_transfer_keeps_value_on_the_opener(self):
        self._make_in_move(self.product, 10, 10)
        shelf = self._shelf('Shelf E')
        self._make_internal_move(self.product, 4, self.stock_location, shelf)
        self._make_internal_move(self.product, 4, shelf, self.stock_location)

        stock_row = self._onhand(self.product, self.stock_location)
        shelf_row = self._onhand(self.product, shelf)
        self.assertEqual(stock_row.received_quantity, 14)
        self.assertEqual(stock_row.received_amount, 140)
        self.assertEqual(stock_row.issued_quantity, 4)
        self.assertEqual(stock_row.issued_amount, 40)
        self.assertEqual(stock_row.closing_quantity, 10)
        self.assertEqual(stock_row.closing_amount, 100)
        self.assertEqual(shelf_row.received_quantity, 4)
        self.assertEqual(shelf_row.received_amount, 40)
        self.assertEqual(shelf_row.issued_quantity, 4)
        self.assertEqual(shelf_row.issued_amount, 40)
        self.assertEqual(shelf_row.closing_quantity, 0)
        self.assertEqual(shelf_row.closing_amount, 0)

    def test_two_step_transit_conserves_amount(self):
        transit = self.env['stock.location'].create({
            'name': 'Bridge Transit',
            'usage': 'transit',
            'company_id': self.company.id,
        })
        shelf = self._shelf('Shelf F')
        self._make_in_move(self.product, 10, 20)
        self._make_internal_move(self.product, 3, self.stock_location, transit)
        self._make_internal_move(self.product, 3, transit, shelf)

        stock_row = self._onhand(self.product, self.stock_location)
        transit_row = self._onhand(self.product, transit)
        shelf_row = self._onhand(self.product, shelf)
        self.assertEqual(stock_row.issued_quantity, 3)
        self.assertEqual(stock_row.issued_amount, 60)
        self.assertEqual(stock_row.closing_quantity, 7)
        self.assertEqual(stock_row.closing_amount, 140)
        self.assertFalse(transit_row.warehouse_id)
        self.assertEqual(transit_row.received_quantity, 3)
        self.assertEqual(transit_row.received_amount, 60)
        self.assertEqual(transit_row.issued_quantity, 3)
        self.assertEqual(transit_row.issued_amount, 60)
        self.assertEqual(transit_row.closing_quantity, 0)
        self.assertEqual(transit_row.closing_amount, 0)
        self.assertEqual(shelf_row.received_quantity, 3)
        self.assertEqual(shelf_row.received_amount, 60)
        self.assertEqual(shelf_row.closing_amount, 60)

    def test_transfer_split_gives_remainder_to_last_location(self):
        receipt = self._make_in_move(self.product, 3, 10)
        receipt.value_manual = 100
        low = self._shelf('Shelf Low')
        high = self._shelf('Shelf High')
        self._make_internal_move(self.product, 1, self.stock_location, low)
        self._make_internal_move(self.product, 1, self.stock_location, high)

        currency = self.company.currency_id
        issued_amount = currency.round(100 * 2 / 3)
        first_amount = currency.round(issued_amount / 2)
        last_amount = currency.round(issued_amount - first_amount)
        first, last = sorted((low, high), key=lambda location: location.id)

        stock_row = self._onhand(self.product, self.stock_location)
        self.assertEqual(stock_row.received_amount, 100)
        self.assertEqual(stock_row.issued_quantity, 2)
        self.assertEqual(stock_row.issued_amount, issued_amount)
        self.assertEqual(stock_row.closing_amount, currency.round(100 - issued_amount))
        self.assertEqual(self._onhand(self.product, first).received_amount, first_amount)
        self.assertEqual(self._onhand(self.product, last).received_amount, last_amount)
        self.assertEqual(
            currency.round(
                stock_row.closing_amount
                + self._onhand(self.product, first).received_amount
                + self._onhand(self.product, last).received_amount
            ),
            100,
        )

    def test_transit_without_warehouse_still_posts(self):
        transit = self.env['stock.location'].create({
            'name': 'Loose Transit',
            'usage': 'transit',
            'company_id': self.company.id,
        })
        self.assertFalse(transit.warehouse_id)
        self._make_in_move(self.product, 3, 15, location_dest=transit)
        row = self._onhand(self.product, transit)
        self.assertEqual(len(row), 1)
        self.assertFalse(row.warehouse_id)
        self.assertEqual(row.received_quantity, 3)
        self.assertEqual(row.received_amount, 45)
        self.assertEqual(row.closing_amount, 45)
