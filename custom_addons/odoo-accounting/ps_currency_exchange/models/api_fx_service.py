# -*- coding: utf-8 -*-
import json
import logging
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_FX_API_URL = "https://www.vietcombank.com.vn/api/exchangerates"
PRIORITY_CODES = ("USD", "EUR", "GBP", "JPY", "CNY", "AUD", "SGD", "KRW", "THB")


class PsCurrencyExchangeService(models.AbstractModel):
    """Outbound helper: fetch Vietcombank FX rates."""

    _name = "ps.currency.exchange.service"
    _description = "FX Rate API Service (Outbound Helper)"

    @api.model
    def _get_config(self):
        icp = self.env["ir.config_parameter"].sudo()
        base_url = icp.get_param("ps_currency_exchange.fx_api_base_url", DEFAULT_FX_API_URL)
        token = icp.get_param("ps_currency_exchange.fx_api_token", "")
        return {
            "base_url": (base_url or DEFAULT_FX_API_URL).rstrip("/"),
            "token": token or "",
        }

    @api.model
    def _get_rate_url(self, rate_date):
        cfg = self._get_config()
        if not cfg["base_url"]:
            raise UserError(_("Chưa cấu hình URL API tỷ giá. Vào Cài đặt tỷ giá để thiết lập."))
        parsed = urlparse(cfg["base_url"])
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if rate_date:
            query["date"] = fields.Date.to_string(rate_date)
        return urlunparse(parsed._replace(query=urlencode(query)))

    @api.model
    def _prepare_headers(self):
        cfg = self._get_config()
        headers = {
            "Accept": "application/json",
            "User-Agent": "Odoo-PS-Currency-Exchange/1.0",
        }
        if cfg["token"]:
            headers["Authorization"] = f"Bearer {cfg['token']}"
        return headers

    @api.model
    def _to_float(self, value):
        if value in (None, False, "", "-"):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", "").replace(" ", "")
        if text in ("", "-"):
            return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0

    @api.model
    def _parse_rates(self, payload):
        if not isinstance(payload, dict):
            raise UserError(_("API tỷ giá trả về dữ liệu không hợp lệ (không phải JSON object)."))
        raw_rows = payload.get("Data") or payload.get("data") or payload.get("results") or []
        if not raw_rows:
            raise UserError(_("API tỷ giá không trả về danh sách ngoại tệ."))

        rates = []
        for row in raw_rows:
            code = (row.get("currencyCode") or row.get("currency") or row.get("CurrencyCode") or "").strip()
            if not code:
                continue
            rates.append({
                "currency_code": code,
                "currency_name": (row.get("currencyName") or row.get("CurrencyName") or code).strip(),
                "cash": self._to_float(row.get("cash") or row.get("buy_cash") or row.get("Buy")),
                "transfer": self._to_float(row.get("transfer") or row.get("buy_transfer") or row.get("Transfer")),
                "sell": self._to_float(row.get("sell") or row.get("Sell")),
            })

        order = {code: index for index, code in enumerate(PRIORITY_CODES)}
        rates.sort(key=lambda item: (order.get(item["currency_code"], 100), item["currency_code"]))
        return {
            "source_date": payload.get("Date") or "",
            "updated_at": payload.get("UpdatedDate") or "",
            "count": payload.get("Count") or len(rates),
            "rates": rates,
        }

    @api.model
    def fetch_rates(self, rate_date=None, rate_id=None):
        """GET Vietcombank exchangerates. Always writes an API log."""
        rate_date = rate_date or fields.Date.context_today(self)
        url = self._get_rate_url(rate_date)
        headers = self._prepare_headers()

        start_time = time.time()
        status_code = 0
        resp_text = ""
        resp_headers = ""
        error_msg = ""
        parsed = None

        try:
            response = requests.get(url=url, headers=headers, timeout=10)
            status_code = response.status_code
            resp_text = response.text
            resp_headers = json.dumps(dict(response.headers), ensure_ascii=False, indent=2)
            response.raise_for_status()
            parsed = self._parse_rates(response.json())
        except requests.exceptions.Timeout:
            error_msg = _("Quá thời gian kết nối (Timeout sau 10 giây) tới API tỷ giá.")
            _logger.error("FX API timeout [%s]", url)
        except requests.exceptions.ConnectionError:
            error_msg = _("Không kết nối được máy chủ tỷ giá: %s", url)
            _logger.error("FX API connection failed [%s]", url)
        except requests.exceptions.HTTPError as exc:
            error_msg = f"HTTP Error ({status_code}): {resp_text or str(exc)}"
            _logger.error("FX API HTTP error [%s]: %s", url, error_msg)
        except UserError as exc:
            error_msg = str(exc)
        except Exception as exc:
            error_msg = _("Lỗi không xác định: %s", str(exc))
            _logger.exception("FX API unexpected error [%s]", url)

        exec_time_ms = (time.time() - start_time) * 1000
        log = self.env["ps.currency.exchange.log"].sudo().create({
            "direction": "outbound",
            "endpoint": url,
            "method": "GET",
            "status_code": status_code,
            "request_headers": json.dumps(headers, indent=2),
            "request_payload": "",
            "response_headers": resp_headers,
            "response_payload": resp_text,
            "execution_time_ms": round(exec_time_ms, 2),
            "rate_date": rate_date,
            "rate_id": rate_id,
            "message": error_msg or _("Lấy tỷ giá Vietcombank thành công (%s loại tiền).", parsed["count"] if parsed else 0),
        })

        if error_msg or not parsed:
            raise UserError(_(
                "Không lấy được tỷ giá ngoại tệ.\n\n"
                "• Endpoint: %s\n"
                "• Mã HTTP: %s\n"
                "• Chi tiết: %s",
                url,
                status_code,
                resp_text or error_msg,
            ))

        parsed["log"] = log
        return parsed
