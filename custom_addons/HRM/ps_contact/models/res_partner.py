from odoo import models, fields, api, _
from odoo.addons.ps_vn_address.models import vn_address_service as vn_addr


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_address_old = fields.Char(
        string='Pre-Merger Address',
        help='Address before administrative merger (provinces/districts/wards), used to convert to the new address.'
    )

    @api.onchange('x_address_old')
    def _onchange_x_address_old(self):
        if not self.x_address_old:
            return

        parsed = vn_addr.parse_vn_address(self.x_address_old)
        if not parsed:
            return {
                'warning': {
                    'title': _('Address Not Recognized'),
                    'message': _('Could not extract province/city from the entered address.'),
                }
            }

        api_key = vn_addr._get_api_key(self.env)
        converted = vn_addr.convert_old_to_new_address(
            parsed['province_code'],
            parsed['district_code'],
            parsed['ward_code'],
            parsed['street'],
            api_key,
        )

        if not converted or not converted.get('new'):
            return {
                'warning': {
                    'title': _('Address Conversion Failed'),
                    'message': _('No corresponding new address was found.'),
                }
            }

        new = converted['new']
        province_name = new.get('province', {}).get('name')
        ward_name = new.get('ward', {}).get('name')
        state = vn_addr._find_state(self.env, province_name)
        country = vn_addr._find_vn_country(self.env)

        self.street = parsed['street'] or ''
        self.street2 = ''
        self.city = ward_name or ''
        self.state_id = state.id if state else False
        self.country_id = country.id if country else False
        self.zip = ''