# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PsCurrencyExchangeRate(models.Model):
    _name = "ps.currency.exchange.rate"
    _description = "FX Rate Snapshot"
    _order = "id desc"

    name = fields.Char(string="Tham chiếu", required=True, copy=False, readonly=True, default=lambda self: _("New"))
    rate_date = fields.Date(
        string="Ngày tỷ giá",
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    fetched_at = fields.Datetime(string="Lấy lúc", readonly=True)
    source_updated_at = fields.Char(string="Cập nhật từ ngân hàng", readonly=True)
    status = fields.Selection(
        [("draft", "Nháp"), ("success", "Thành công"), ("failed", "Thất bại")],
        string="Kết quả",
        default="draft",
        readonly=True,
        copy=False,
    )
    message = fields.Text(string="Thông điệp", readonly=True)
    line_ids = fields.One2many("ps.currency.exchange.rate.line", "rate_id", string="Tỷ giá")
    log_ids = fields.One2many("ps.currency.exchange.log", "rate_id", string="API Logs")
    log_count = fields.Integer(string="Số log", compute="_compute_log_count")
    response_payload = fields.Text(string="Response JSON", readonly=True)

    @api.depends("log_ids")
    def _compute_log_count(self):
        for rec in self:
            rec.log_count = len(rec.log_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.name in (False, _("New"), "New"):
                rec.name = f"FX-{fields.Date.to_string(rec.rate_date)}-{rec.id}"
        return records

    def action_fetch_rates(self):
        self.ensure_one()
        try:
            result = self.env["ps.currency.exchange.service"].fetch_rates(
                rate_date=self.rate_date,
                rate_id=self.id,
            )
        except UserError as exc:
            self.write({"status": "failed", "message": str(exc)})
            raise
        self.line_ids.unlink()
        self.write({
            "fetched_at": fields.Datetime.now(),
            "source_updated_at": result.get("updated_at") or result.get("source_date") or "",
            "status": "success",
            "message": _("Đã tải %s loại tiền từ Vietcombank.", len(result["rates"])),
            "response_payload": result["log"].response_payload,
            "line_ids": [
                (0, 0, {
                    "sequence": index + 1,
                    "currency_code": row["currency_code"],
                    "currency_name": row["currency_name"],
                    "cash": row["cash"],
                    "transfer": row["transfer"],
                    "sell": row["sell"],
                })
                for index, row in enumerate(result["rates"])
            ],
        })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Đã lấy tỷ giá"),
                "message": _("Vietcombank: %s loại tiền, ngày %s.", len(self.line_ids), self.rate_date),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.client",
                    "tag": "soft_reload",
                },
            },
        }

    def action_view_logs(self):
        self.ensure_one()
        return {
            "name": _("API Logs - %s", self.name),
            "type": "ir.actions.act_window",
            "res_model": "ps.currency.exchange.log",
            "view_mode": "list,form",
            "views": [[False, "list"], [False, "form"]],
            "domain": [("rate_id", "=", self.id)],
            "context": {"default_rate_id": self.id},
        }


class PsCurrencyExchangeRateLine(models.Model):
    _name = "ps.currency.exchange.rate.line"
    _description = "FX Rate Line"
    _order = "sequence, currency_code, id"

    rate_id = fields.Many2one("ps.currency.exchange.rate", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    currency_code = fields.Char(string="Mã NT", required=True)
    currency_name = fields.Char(string="Tên ngoại tệ")
    cash = fields.Float(string="Mua tiền mặt", digits=(16, 2))
    transfer = fields.Float(string="Mua chuyển khoản", digits=(16, 2))
    sell = fields.Float(string="Bán", digits=(16, 2))
