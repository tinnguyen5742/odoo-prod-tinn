# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import api, fields, models


class PsCurrencyExchangeLog(models.Model):
    _name = "ps.currency.exchange.log"
    _description = "FX Rate API Log"
    _order = "create_date desc, id desc"

    name = fields.Char(
        string="Log Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self._default_name(),
    )
    direction = fields.Selection(
        [
            ("outbound", "Outbound (Odoo -> Bên ngoài)"),
            ("inbound", "Inbound (Bên ngoài -> Odoo)"),
        ],
        string="Chiều dữ liệu",
        required=True,
        default="outbound",
        readonly=True,
    )
    endpoint = fields.Char(string="Endpoint URL", readonly=True)
    method = fields.Selection(
        [("GET", "GET"), ("POST", "POST"), ("PUT", "PUT"), ("DELETE", "DELETE")],
        string="HTTP Method",
        default="GET",
        readonly=True,
    )
    status_code = fields.Integer(string="HTTP Status", readonly=True)
    status = fields.Selection(
        [("success", "Thành công"), ("failed", "Thất bại")],
        string="Kết quả",
        compute="_compute_status",
        store=True,
    )
    execution_time_ms = fields.Float(string="Thời gian xử lý (ms)", readonly=True)
    rate_date = fields.Date(string="Ngày tỷ giá", readonly=True)
    rate_id = fields.Many2one(
        "ps.currency.exchange.rate",
        string="Bảng tỷ giá",
        ondelete="set null",
        readonly=True,
    )
    request_headers = fields.Text(string="Request Headers", readonly=True)
    request_payload = fields.Text(string="Request Payload (JSON)", readonly=True)
    response_headers = fields.Text(string="Response Headers", readonly=True)
    response_payload = fields.Text(string="Response Payload (JSON/Text)", readonly=True)
    message = fields.Text(string="Ghi chú / Thông điệp", readonly=True)

    @api.model
    def _default_name(self):
        return f"FX-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"

    @api.depends("status_code")
    def _compute_status(self):
        for rec in self:
            rec.status = "success" if rec.status_code and 200 <= rec.status_code < 300 else "failed"
