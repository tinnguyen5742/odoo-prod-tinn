import datetime

import pytz

from odoo import api, models

from odoo.addons.ps_tz_guard.models.tz_utils import resolve_tz


class ResourceCalendar(models.Model):
    _inherit = "resource.calendar"

    def _sanitize_tz(self, vals):
        if vals.get("tz"):
            vals["tz"] = resolve_tz(vals["tz"]) or "UTC"
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._sanitize_tz(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._sanitize_tz(vals))

    @api.depends("tz")
    def _compute_tz_offset(self):
        for calendar in self:
            try:
                calendar.tz_offset = datetime.datetime.now(
                    pytz.timezone(calendar.tz or "GMT")
                ).strftime("%z")
            except Exception:
                calendar.tz_offset = "+0000"


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    def _sanitize_tz(self, vals):
        if vals.get("tz"):
            vals["tz"] = resolve_tz(vals["tz"]) or "UTC"
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._sanitize_tz(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._sanitize_tz(vals))
