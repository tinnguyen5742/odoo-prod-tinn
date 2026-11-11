import datetime

import pytz

from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.depends("tz")
    def _compute_tz_offset(self):
        for user in self:
            try:
                user.tz_offset = datetime.datetime.now(
                    pytz.timezone(user.tz or "GMT")
                ).strftime("%z")
            except Exception:
                user.tz_offset = "+0000"
