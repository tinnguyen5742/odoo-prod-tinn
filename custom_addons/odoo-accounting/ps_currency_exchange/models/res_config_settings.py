import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

from .api_fx_service import DEFAULT_FX_API_URL


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    fx_api_base_url = fields.Char(
        string="FX API URL",
        config_parameter="ps_currency_exchange.fx_api_base_url",
        default=DEFAULT_FX_API_URL,
        help="Vietcombank JSON endpoint. Date is appended automatically as ?date=YYYY-MM-DD.",
    )
    fx_api_token = fields.Char(
        string="FX API Token",
        config_parameter="ps_currency_exchange.fx_api_token",
        help="Optional Bearer token. Leave empty for the public Vietcombank API.",
    )

    def action_test_fx_connection(self):
        self.ensure_one()
        base_url = (self.fx_api_base_url or DEFAULT_FX_API_URL).rstrip("/")
        ping_url = f"{base_url}?date={fields.Date.to_string(fields.Date.context_today(self))}"
        try:
            resp = requests.get(
                ping_url,
                headers={"Accept": "application/json", "User-Agent": "Odoo-PS-Currency-Exchange/1.0"},
                timeout=10,
            )
            if resp.status_code == 200:
                payload = resp.json()
                count = payload.get("Count") or len(payload.get("Data") or [])
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Kết nối thành công!"),
                        "message": _("Vietcombank phản hồi %s loại tiền tại %s", count, ping_url),
                        "type": "success",
                        "sticky": False,
                    },
                }
            raise UserError(_("API tỷ giá phản hồi mã lỗi: %s\nNội dung: %s", resp.status_code, resp.text[:500]))
        except UserError:
            raise
        except Exception as exc:
            raise UserError(_(
                "Không kết nối được API tỷ giá tại: %s\nLỗi: %s",
                ping_url,
                str(exc),
            )) from exc
