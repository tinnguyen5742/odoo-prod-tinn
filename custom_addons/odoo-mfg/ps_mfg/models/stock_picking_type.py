from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    ps_mfg_finish_type = fields.Boolean(
        "Manufacturing Finished Goods Receipt",
        copy=False,
        help="Operation type used by finished goods receipts (Production → stock), "
        "without picking.",
    )


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    def _ps_mfg_get_finish_picking_type(self):
        """Operation type 'Nhập thành phẩm SX' của kho, tạo khi cần.

        Bật use_create_lots để popup Detailed Operations của Odoo hiện
        Generate Serials / Import Lots và tạo lot từ lot_name khi done.
        """
        self.ensure_one()
        PickingType = self.env["stock.picking.type"].with_context(active_test=False)
        picking_type = PickingType.search(
            [("warehouse_id", "=", self.id), ("ps_mfg_finish_type", "=", True)],
            limit=1,
        )
        if picking_type:
            return picking_type
        return (
            PickingType.sudo()
            .create(
                {
                    "name": _("Manufacturing Receipts"),
                    "code": "incoming",
                    "sequence_code": "FG",
                    "warehouse_id": self.id,
                    "company_id": self.company_id.id,
                    "default_location_src_id": self.company_id._ps_mfg_production_location().id,
                    "default_location_dest_id": self.lot_stock_id.id,
                    "use_create_lots": True,
                    "use_existing_lots": False,
                    "ps_mfg_finish_type": True,
                }
            )
            .sudo(False)
        )


class ResCompany(models.Model):
    _inherit = "res.company"

    def _ps_mfg_production_location(self):
        """Kho ảo Production của công ty (Odoo 19: theo công ty, không có xmlid)."""
        self.ensure_one()
        location_id = (
            self.env["product.template"]
            .with_company(self)
            .default_get(["property_stock_production"])
            .get("property_stock_production")
        )
        if location_id:
            return self.env["stock.location"].browse(location_id)
        location = self.env["stock.location"].search(
            [("usage", "=", "production"), ("company_id", "in", (self.id, False))],
            limit=1,
        )
        if not location:
            raise UserError(_("No production location found for this company."))
        return location
