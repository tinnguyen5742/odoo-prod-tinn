# -*- coding: utf-8 -*-
import logging

from odoo.addons.ps_contact.models.acumatica_api import AcumaticaAPI

_logger = logging.getLogger(__name__)


class SaleAcumaticaAPI(AcumaticaAPI):
    """Client API Acumatica cho phân hệ Sales"""

    def __init__(self, env):
        super().__init__(env)
        self.timeout = 25  # Timeout 25s hợp lý cho cả kết nối mạng và xử lý dữ liệu

    # Gọi API lấy danh sách Loại SO (SOOrderType)
    def get_so_order_types(self):
        return self._request('GET', '/api/v1/dic/SOOrderType')

    # Gọi API lấy danh sách Vật tư (inventories)
    def get_inventories(self, limit=1000):
        return self._request('GET', '/api/v1/dic/inventories', params={'limit': limit})

    # Gọi API lấy danh sách Đơn vị tính (ItemUnit)
    def get_item_units(self, limit=1000):
        return self._request('GET', '/api/v1/dic/ItemUnit', params={'limit': limit})

    # Gọi API lấy danh sách Thuế (vat)
    def get_taxes(self, limit=100):
        return self._request('GET', '/api/v1/dic/vat', params={'limit': limit})

    # Gọi API tạo khách hàng mới trên Acumatica
    def create_customer(self, partner):
        acct_cd = partner.x_customer_code or partner.ref or f"CUST{partner.id}"
        payload = {
            'AcctCD': acct_cd,
            'AcctName': partner.name or '',
            'CustomerName': partner.name or '',
            'Phone': partner.phone or getattr(partner, 'mobile', '') or '',
            'Email': partner.email or '',
            'TaxRegistrationID': partner.vat or '',
            'AddressLine1': partner.street or '',
            'AddressLine2': partner.street2 or '',
            'City': partner.city or '',
        }
        return self._request('POST', '/api/v1/process/createCustomer', json=payload)

    # Gọi API raiseevent kích hoạt sự kiện sang Acumatica
    def raise_event(self, event_name, id_list):
        payload = {
            'EventName': event_name,
            'List': [str(x) for x in id_list],
        }
        return self._request('POST', '/api/v1/process/raiseevent', json=payload)

    # Gọi API tạo Sales Order trên Acumatica
    def create_sales_order(self, data):
        return self._request('POST', '/api/v1/process/createSO', json=data)

