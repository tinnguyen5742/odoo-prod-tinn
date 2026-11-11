import requests
from math import radians, sin, cos, sqrt, atan2
from odoo import models, api, fields

COMPANY_LAT = 10.76247850549426
COMPANY_LNG = 106.64762780083724
COMPANY_ADDRESS = 'Số 44, đường 7, Cư xá Bình Thới, Phường Bình Thới, Thành phố Hồ Chí Minh, Việt Nam'
RADIUS_KM = 0.1


def _haversine_km(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def _get_location_name(lat, lng):
    # Trả về tên địa chỉ dựa theo tọa độ
    if _haversine_km(lat, lng, COMPANY_LAT, COMPANY_LNG) <= RADIUS_KM:
        return COMPANY_ADDRESS
    try:
        resp = requests.get(
            'https://nominatim.openstreetmap.org/reverse',
            params={'format': 'json', 'lat': lat, 'lon': lng, 'zoom': 18, 'addressdetails': 1},
            headers={'Accept-Language': 'vi'},
            timeout=5,
        )
        data = resp.json()
        a = data.get('address', {})
        parts = [
            a.get('house_number'),
            a.get('road'),
            a.get('quarter') or a.get('suburb'),
            a.get('city_district') or a.get('district'),
            a.get('city') or a.get('town') or a.get('village'),
            a.get('country'),
        ]
        return ', '.join(p for p in parts if p)
    except Exception:
        return ''


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    location = fields.Char(compute='_compute_location', store=False)

    # Tính toán lại location, nếu khác location check in & out thì ghép chuỗi
    @api.depends('in_location', 'out_location')
    def _compute_location(self):
        for rec in self:
            in_loc = (rec.in_location or '').strip()
            out_loc = (rec.out_location or '').strip()

            # Loại bỏ giá trị rỗng
            parts = [p for p in {in_loc, out_loc} if p]

            # Join nếu có nhiều hơn 1 giá trị
            rec.location = ' → '.join(parts)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            lat = vals.get('in_latitude', 0)
            lng = vals.get('in_longitude', 0)
            if lat and lng:
                vals['in_location'] = _get_location_name(lat, lng)
        return super().create(vals_list)

    def write(self, vals):
        lat = vals.get('out_latitude', 0)
        lng = vals.get('out_longitude', 0)
        if lat and lng:
            vals['out_location'] = _get_location_name(lat, lng)
        return super().write(vals)