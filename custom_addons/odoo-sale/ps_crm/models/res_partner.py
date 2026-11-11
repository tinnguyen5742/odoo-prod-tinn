import logging

from odoo.fields import Domain
from odoo import api, fields, models

from odoo.addons.ps_contact.models.acumatica_api import AcumaticaAPI

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Giới hạn khi đọc danh sách khách hàng từ Acumatica
    ACU_MAX_PAGES = 10
    ACU_MAX_MATCHES = 20
    ACU_TIMEOUT = 15

    # Hiển thị: nối chuỗi tên công ty hiện tại (mã khách hàng) nếu có
    # Ví dụ: [liên hệ] ABC Capital Ventures - ABCVENTURE
    @api.depends_context('ps_show_acu_id')
    def _compute_display_name(self):
        super()._compute_display_name()
        if not self.env.context.get('ps_show_acu_id'):
            return
        for partner in self:
            if partner.x_customer_code:
                suffix = f" - {partner.x_customer_code}"
                if not (partner.display_name or '').endswith(suffix) and suffix not in (partner.display_name or ''):
                    partner.display_name = f"{partner.display_name}{suffix}"

    # Tìm kiếm: gộp khách hàng Odoo + khách hàng đọc từ Acumatica
    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        if not self.env.context.get('ps_search_accu'):
            return super().name_search(name=name, domain=domain, operator=operator, limit=limit)
        self._ensure_acumatica_partners(name)
        search_domain = Domain(domain or Domain.TRUE)
        if name:
            search_domain &= Domain.OR([
                [('name', operator, name)],
                [('x_customer_code', operator, name)],
            ])
        return super().name_search(name='', domain=search_domain, operator=operator, limit=limit)

    # Đọc khách hàng từ API Acumatica và tạo bản ghi chưa tồn tại
    def _ensure_acumatica_partners(self, term=''):
        term = (term or '').lower().strip()
        if not term:
            return
        api = AcumaticaAPI(self.env)
        api.timeout = self.ACU_TIMEOUT
        matches = []
        try:
            page = 1
            while page <= self.ACU_MAX_PAGES and len(matches) < self.ACU_MAX_MATCHES:
                payload = api.get_customers(page=page)
                items = (payload or {}).get('Data') or []
                if not items:
                    break
                for data in items:
                    customer_name = (data.get('CustomerName') or '').lower()
                    customer_cd = (data.get('CustomerCD') or '').lower()
                    if term and term not in customer_name and term != customer_cd:
                        continue
                    matches.append(data)
                    if len(matches) >= self.ACU_MAX_MATCHES:
                        break
                page += 1
        except Exception as err:
            _logger.warning('Không đọc được khách hàng từ Acumatica: %s', err)
            return

        for data in matches:
            customer_cd = (data.get('CustomerCD') or '').strip()
            if not customer_cd or self.search_count([('x_customer_code', '=', customer_cd)]):
                continue
            try:
                vals = {
                    'name': (data.get('CustomerName') or customer_cd).strip(),
                    'x_customer_code': customer_cd,
                    'company_type': 'company',
                    'x_created_from': 'acumatica',
                    'acu_sync_status': 'synced',
                    'acu_sync_date': fields.Datetime.now(),
                }
                if data.get('TaxRegistrationID'):
                    vals['vat'] = data['TaxRegistrationID'].strip()
                if data.get('EMail'):
                    vals['email'] = data['EMail'].strip()
                if data.get('Phone1and2'):
                    vals['phone'] = data['Phone1and2'].strip()
                if data.get('AddressLine1'):
                    vals['street'] = data['AddressLine1'].strip()
                if data.get('AddressLine2'):
                    vals['street2'] = data['AddressLine2'].strip()
                if data.get('City'):
                    vals['city'] = data['City'].strip()
                if data.get('PostalCode'):
                    vals['zip'] = data['PostalCode'].strip()

                with self.env.cr.savepoint():
                    self.create(vals)
            except Exception as err:
                _logger.warning('Không tạo được khách hàng Acumatica %s: %s', customer_cd, err)
