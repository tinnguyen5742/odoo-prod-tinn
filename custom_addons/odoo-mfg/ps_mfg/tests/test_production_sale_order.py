from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMfgProductionSaleOrder(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.uom_pack = cls.env.ref("uom.product_uom_pack_6")
        cls.partner = cls.env["res.partner"].create({"name": "MO SO Customer"})
        cls.goods = cls.env["product.product"].create(
            {
                "name": "SO Goods",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.goods_b = cls.env["product.product"].create(
            {
                "name": "SO Goods B",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.goods_c = cls.env["product.product"].create(
            {
                "name": "SO Goods C",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.service = cls.env["product.product"].create(
            {
                "name": "SO Service",
                "type": "service",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.downpayment = cls.env["product.product"].create(
            {
                "name": "SO Down Payment",
                "type": "consu",
                "uom_id": cls.uom_unit.id,
            }
        )
        cls.workcenter = cls.env["ps.mfg.work.center"].create(
            {
                "name": "WC SO Test",
                "code": "WC-SO-T",
                "location_id": cls.env["stock.location"]
                .search(
                    [
                        ("usage", "=", "internal"),
                        ("company_id", "in", (False, cls.env.company.id)),
                    ],
                    limit=1,
                )
                .id,
                "expense_account_id": cls.env["account.account"].search([], limit=1).id,
                "wip_account_id": cls.env["account.account"].search([], limit=1).id,
                "mo_prefix": "MO/SO/",
                "comp_request_prefix": "CR/SO/",
                "receipt_request_prefix": "RC/SO/",
            }
        )
        cls.bom = cls._create_bom(cls.goods, cls.uom_unit)
        cls.bom_b = cls._create_bom(cls.goods_b, cls.uom_unit)
        cls.bom_c = cls._create_bom(cls.goods_c, cls.uom_unit)

    @classmethod
    def _create_bom(cls, product, uom, version=1):
        return cls.env["ps.mfg.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "product_id": product.id,
                "product_qty": 1.0,
                "product_uom_id": uom.id,
                "version": version,
            }
        )

    def _sale_order(self, lines):
        return self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "order_line": [(0, 0, vals) for vals in lines],
            }
        )

    def _mo_form(self):
        form = Form(self.env["ps.mfg.production"])
        form.workcenter_id = self.workcenter
        return form

    def test_single_product_sets_product_qty_and_bom(self):
        order = self._sale_order(
            [
                {"display_type": "line_section", "name": "Section"},
                {"display_type": "line_note", "name": "Note"},
                {"product_id": self.service.id, "product_uom_qty": 1.0},
                {
                    "product_id": self.downpayment.id,
                    "product_uom_qty": 9.0,
                    "is_downpayment": True,
                    "price_unit": 10.0,
                },
                {"product_id": self.goods.id, "product_uom_qty": 5.0},
            ]
        )
        mo = self.env["ps.mfg.production"].new({"sale_order_id": order.id})
        self.assertEqual(mo._sale_order_products(), self.goods)

        form = self._mo_form()
        form.sale_order_id = order
        self.assertEqual(form.product_id, self.goods)
        self.assertEqual(form.product_qty, 5.0)
        self.assertEqual(form.bom_id, self.bom)
        self.assertEqual(form.customer_name, self.partner.name)
        saved = form.save()
        self.assertEqual(saved.product_id, self.goods)
        self.assertEqual(saved.product_qty, 5.0)
        self.assertEqual(saved.bom_id, self.bom)
        self.assertEqual(saved.customer_name, self.partner.name)

    def test_duplicate_lines_sum_qty(self):
        order = self._sale_order(
            [
                {"product_id": self.goods.id, "product_uom_qty": 2.0},
                {"product_id": self.goods.id, "product_uom_qty": 3.0},
            ]
        )
        form = self._mo_form()
        form.sale_order_id = order
        self.assertEqual(form.product_id, self.goods)
        self.assertEqual(form.product_qty, 5.0)

    def test_several_products_qty_follows_choice(self):
        order = self._sale_order(
            [
                {"display_type": "line_section", "name": "Section"},
                {"display_type": "line_note", "name": "Note"},
                {"product_id": self.service.id, "product_uom_qty": 1.0},
                {
                    "product_id": self.downpayment.id,
                    "product_uom_qty": 9.0,
                    "is_downpayment": True,
                    "price_unit": 10.0,
                },
                {"product_id": self.goods.id, "product_uom_qty": 4.0},
                {"product_id": self.goods_b.id, "product_uom_qty": 7.0},
            ]
        )
        form = self._mo_form()
        form.sale_order_id = order
        self.assertFalse(form.product_id)
        self.assertEqual(
            {product.id for product in form.sale_product_ids},
            {self.goods.id, self.goods_b.id},
        )

        form.product_id = self.goods
        self.assertEqual(form.product_qty, 4.0)
        self.assertEqual(form.bom_id, self.bom)

        form.product_id = self.goods_b
        self.assertEqual(form.product_qty, 7.0)
        self.assertEqual(form.bom_id, self.bom_b)

    def test_qty_converts_into_bom_uom(self):
        packed = self.env["product.product"].create(
            {
                "name": "SO Packed Goods",
                "type": "consu",
                "uom_id": self.uom_unit.id,
            }
        )
        bom = self._create_bom(packed, self.uom_pack)
        order = self._sale_order(
            [
                {"product_id": packed.id, "product_uom_qty": 12.0},
            ]
        )
        form = self._mo_form()
        form.sale_order_id = order
        self.assertEqual(form.bom_id, bom)
        self.assertEqual(form.product_uom_id, self.uom_pack)
        # 12 units = 2 packs of 6.
        self.assertEqual(form.product_qty, 2.0)

    def test_switch_sale_order_clears_unknown_product(self):
        current = self._sale_order(
            [
                {"product_id": self.goods.id, "product_uom_qty": 5.0},
            ]
        )
        other = self._sale_order(
            [
                {"product_id": self.goods_b.id, "product_uom_qty": 8.0},
                {"product_id": self.goods_c.id, "product_uom_qty": 3.0},
            ]
        )
        form = self._mo_form()
        form.sale_order_id = current
        self.assertEqual(form.product_id, self.goods)
        form.sale_order_id = other
        self.assertFalse(form.product_id)
        self.assertFalse(form.bom_id)
        self.assertEqual(form.product_qty, 1.0)

    def test_switch_to_single_product_replaces_product(self):
        current = self._sale_order(
            [
                {"product_id": self.goods.id, "product_uom_qty": 5.0},
            ]
        )
        other_partner = self.env["res.partner"].create({"name": "Other SO Customer"})
        other = self._sale_order(
            [
                {"product_id": self.goods_b.id, "product_uom_qty": 8.0},
            ]
        )
        other.partner_id = other_partner
        form = self._mo_form()
        form.sale_order_id = current
        self.assertEqual(form.customer_name, self.partner.name)
        form.sale_order_id = other
        self.assertEqual(form.product_id, self.goods_b)
        self.assertEqual(form.product_qty, 8.0)
        self.assertEqual(form.bom_id, self.bom_b)
        self.assertEqual(form.customer_name, other_partner.name)

    def test_clear_sale_order_keeps_product_and_qty(self):
        order = self._sale_order(
            [
                {"product_id": self.goods.id, "product_uom_qty": 5.0},
            ]
        )
        mo = self.env["ps.mfg.production"].create(
            {
                "sale_order_id": order.id,
                "product_id": self.goods.id,
                "product_qty": 7.0,
                "customer_name": self.partner.name,
                "workcenter_id": self.workcenter.id,
            }
        )
        form = Form(mo)
        form.sale_order_id = self.env["sale.order"]
        self.assertEqual(form.product_id, self.goods)
        self.assertEqual(form.product_qty, 7.0)
        self.assertEqual(form.bom_id, mo.bom_id)
        self.assertFalse(form.customer_name)
