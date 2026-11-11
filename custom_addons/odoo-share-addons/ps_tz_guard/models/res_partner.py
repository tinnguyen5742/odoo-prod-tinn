import datetime

import pytz

from odoo import api, models

from .tz_utils import resolve_tz


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("tz"):
                vals["tz"] = resolve_tz(vals["tz"]) or False
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("tz"):
            vals["tz"] = resolve_tz(vals["tz"]) or False
        return super().write(vals)

    @api.depends("tz")
    def _compute_tz_offset(self):
        for partner in self:
            try:
                partner.tz_offset = datetime.datetime.now(
                    pytz.timezone(partner.tz or "GMT")
                ).strftime("%z")
            except Exception:
                partner.tz_offset = "+0000"
