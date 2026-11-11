# -*- coding: utf-8 -*-
import json
import logging
from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class SaleAcumaticaApiController(http.Controller):

    # Endpoint nhận webhook cập nhật số SO và ngày tạo SO từ Acumatica
    @http.route(
        '/api/v1/sale/order/update_acumatica_so',
        type='http',
        auth='public',
        methods=['POST', 'GET'],
        csrf=False,
    )
    def update_acumatica_so(self, **kwargs):
        data = {}
        # 1. Thử đọc payload JSON từ raw_body
        try:
            raw_body = request.httprequest.get_data(as_text=True)
            if raw_body:
                parsed = json.loads(raw_body)
                if isinstance(parsed, dict):
                    data = parsed
        except Exception:
            pass

        # 2. Nếu không có JSON body, fallback sang request.params (form-data, URL query params)
        if not data and request.params:
            data = dict(request.params)

        # 3. Hỗ trợ trường hợp JSON payload bọc trong 'params' (JSON-RPC) hoặc 'Data' / 'data'
        if isinstance(data, dict):
            if 'params' in data and isinstance(data['params'], dict):
                data = data['params']
            elif 'Data' in data and isinstance(data['Data'], dict):
                data = data['Data']
            elif 'data' in data and isinstance(data['data'], dict):
                data = data['data']
        else:
            data = {}

        _logger.info('Nhận webhook cập nhật Acumatica SO: %s (kwargs: %s)', data, kwargs)

        # 4. Trích xuất linh hoạt theo các định dạng tên trường
        order_id = (
            data.get('odoo_order_id')
            or data.get('order_id')
            or data.get('id')
            or data.get('OdooOrderID')
            or kwargs.get('odoo_order_id')
            or kwargs.get('order_id')
            or kwargs.get('id')
        )
        order_name = (
            data.get('odoo_order_name')
            or data.get('order_name')
            or data.get('name')
            or data.get('OdooOrderName')
            or kwargs.get('odoo_order_name')
            or kwargs.get('order_name')
            or kwargs.get('name')
        )
        so_number = (
            data.get('acumatica_so_number')
            or data.get('OrderNbr')
            or data.get('so_number')
            or data.get('SONumber')
            or data.get('order_nbr')
            or kwargs.get('acumatica_so_number')
            or kwargs.get('OrderNbr')
            or kwargs.get('so_number')
            or kwargs.get('SONumber')
            or ''
        )
        if isinstance(so_number, str):
            so_number = so_number.strip()
        else:
            so_number = str(so_number).strip() if so_number else ''

        so_date = (
            data.get('acumatica_so_date')
            or data.get('OrderDate')
            or data.get('so_date')
            or data.get('order_date')
            or kwargs.get('acumatica_so_date')
            or kwargs.get('OrderDate')
            or kwargs.get('so_date')
        )

        if not so_number:
            return request.make_json_response({
                'success': False,
                'message': 'Thiếu trường acumatica_so_number (hỗ trợ các tên: acumatica_so_number, OrderNbr, so_number, SONumber)',
            }, status=400)

        domain = []
        if order_id:
            try:
                domain = [('id', '=', int(order_id))]
            except ValueError:
                return request.make_json_response({'success': False, 'message': 'odoo_order_id không hợp lệ'}, status=400)
        elif order_name:
            domain = [('name', '=', str(order_name).strip())]
        else:
            return request.make_json_response({
                'success': False,
                'message': 'Cần truyền odoo_order_id hoặc odoo_order_name (hỗ trợ: odoo_order_id, order_id, id, odoo_order_name, order_name, name)',
            }, status=400)


        admin_user = request.env.ref('base.user_admin', raise_if_not_found=False) or request.env.ref('base.user_root')
        order = request.env['sale.order'].with_user(admin_user).search(domain, limit=1)
        if not order:
            return request.make_json_response({'success': False, 'message': 'Không tìm thấy đơn báo giá trong Odoo'}, status=404)

        vals = {
            'x_acumatica_so_number': so_number,
            'x_acumatica_so_status': 'synced',
        }
        if so_date:
            vals['x_acumatica_so_date'] = so_date
        else:
            vals['x_acumatica_so_date'] = fields.Datetime.now()

        order.write(vals)

        # Cập nhật mã Acumatica CustomerCD nếu chưa có
        customer_cd = (
            data.get('customer_cd')
            or data.get('CustomerCD')
            or data.get('customer_code')
            or kwargs.get('customer_cd')
            or kwargs.get('CustomerCD')
        )
        if customer_cd and order.partner_id and not order.partner_id.x_customer_code:
            order.partner_id.write({'x_customer_code': str(customer_cd).strip()})

        order.message_post(body=f"Hệ thống Acumatica đã cập nhật số SO: <b>{so_number}</b>")

        return request.make_json_response({
            'success': True,
            'message': 'Cập nhật thành công',
            'order_id': order.id,
            'order_name': order.name,
            'acumatica_so_number': so_number,
            'acumatica_so_date': str(order.x_acumatica_so_date),
        }, status=200)

    # Endpoint tra cứu thông tin chi tiết Báo giá Odoo cho Acumatica Gateway
    @http.route('/api/v1/sale/order/info', type='http', auth='public', methods=['GET'], csrf=False)
    def get_sale_order_info(self, **params):
        order_id = params.get('order_id')
        order_name = params.get('order_name')

        domain = []
        if order_id:
            try:
                domain = [('id', '=', int(order_id))]
            except ValueError:
                return request.make_json_response({'success': False, 'message': 'order_id không hợp lệ'}, status=400)
        elif order_name:
            domain = [('name', '=', str(order_name).strip())]
        else:
            return request.make_json_response({'success': False, 'message': 'Cần truyền order_id hoặc order_name'}, status=400)

        admin_user = request.env.ref('base.user_admin', raise_if_not_found=False) or request.env.ref('base.user_root')
        order = request.env['sale.order'].with_user(admin_user).search(domain, limit=1)
        if not order:
            return request.make_json_response({'success': False, 'message': 'Không tìm thấy đơn báo giá trong Odoo'}, status=404)

        data = self._serialize_so_request(order)
        return request.make_json_response({'success': True, 'data': data}, status=200)

    # Chuyển đổi đối tượng res.partner sang CustomerRequest theo chuẩn Acumatica
    def _serialize_customer_request(self, partner):
        if not partner:
            return None
        phone = getattr(partner, 'phone', '') or ''

        # Lấy danh sách địa chỉ giao hàng và người liên hệ con
        delivery_addresses = []
        contact_persons = []
        if partner.child_ids:
            for child in partner.child_ids:
                c_phone = getattr(child, 'phone', '') or ''
                if child.type == 'delivery':
                    delivery_addresses.append({
                        'ID': child.id,
                        'Name': child.name or '',
                        'Address': child.street or '',
                        'City': child.city or '',
                        'Phone': c_phone,
                        'Email': child.email or '',
                    })
                elif child.type == 'contact':
                    contact_persons.append({
                        'ID': child.id,
                        'Name': child.name or '',
                        'JobTitle': getattr(child, 'function', '') or '',
                        'Phone': c_phone,
                        'Email': child.email or '',
                    })

        res = {
            'CustomerID': partner.id,
            'AcctCD': partner.x_customer_code or partner.ref or '',
            'AcctName': partner.name or '',
            'DefContactEMail': partner.email or '',
            'DefContactPhone1': phone,
            'DefAddressAddressLine1': partner.street or '',
            'City': partner.city or '',
            'TaxRegistrationID': partner.vat or '',
            'CreatedFrom': partner.x_created_from or ('acumatica' if partner.x_customer_code else 'odoo'),
        }
        if delivery_addresses:
            res['DeliveryAddresses'] = delivery_addresses
        if contact_persons:
            res['Contacts'] = contact_persons
        return res

    # Chuyển đổi đối tượng sale.order sang SORequest kèm LineItems theo chuẩn Acumatica
    def _serialize_so_request(self, order):
        line_items = []
        if order.order_line:
            for line in order.order_line:
                if line.display_type:
                    continue
                inv_id = None
                inv_cd = ''
                if hasattr(line, 'x_inventory_id') and line.x_inventory_id:
                    inv_id = line.x_inventory_id.inventory_id or line.x_inventory_id.id
                    inv_cd = line.x_inventory_id.inventory_cd or ''
                elif line.product_id:
                    inv_id = line.product_id.id
                    inv_cd = line.product_id.default_code or ''

                uom_name = ''
                if hasattr(line, 'x_item_unit_id') and line.x_item_unit_id:
                    uom_name = line.x_item_unit_id.name or ''
                elif hasattr(line, 'product_uom_id') and line.product_uom_id:
                    uom_name = line.product_uom_id.name or ''
                elif hasattr(line, 'product_uom') and line.product_uom:
                    uom_name = line.product_uom.name or ''

                tax_id = ''
                tax_rate = 0.0
                if hasattr(line, 'x_tax_id') and line.x_tax_id:
                    tax_id = line.x_tax_id.tax_id or ''
                    tax_rate = float(line.x_tax_id.tax_rate or 0.0)

                line_items.append({
                    'InventoryID': inv_id,
                    'InventoryCD': inv_cd,
                    'Description': line.name or '',
                    'Quantity': float(line.product_uom_qty or 0.0),
                    'CuryUnitPrice': float(line.price_unit or 0.0),
                    'UOM': uom_name,
                    'TaxID': tax_id,
                    'TaxRate': tax_rate,
                    'LineTotal': float(line.price_subtotal or 0.0),
                })

        # Fallback: Nếu không có order_line nhưng có trường x_inventory_id ở header
        if not line_items and hasattr(order, 'x_inventory_id') and order.x_inventory_id:
            line_items.append({
                'InventoryID': order.x_inventory_id.inventory_id or order.x_inventory_id.id,
                'InventoryCD': order.x_inventory_id.inventory_cd or '',
                'Description': order.x_inventory_id.name or '',
                'Quantity': 1.0,
                'CuryUnitPrice': float(order.x_unit_price or 0.0),
                'UOM': order.x_item_unit_id.name if hasattr(order, 'x_item_unit_id') and order.x_item_unit_id else '',
                'LineTotal': float(order.x_unit_price or 0.0),
            })

        order_type = 'SO'
        if hasattr(order, 'x_order_type_id') and order.x_order_type_id and order.x_order_type_id.code:
            order_type = order.x_order_type_id.code

        return {
            'CustomerID': order.partner_id.id if order.partner_id else None,
            'OrderType': order_type,
            'OdooRefOrder': order.id,
            'OdooOrderName': order.name or '',
            'AcumaticaSONumber': order.x_acumatica_so_number or '',
            'OrderDate': str(order.date_order) if order.date_order else '',
            'Status': order.state or '',
            'CuryID': order.currency_id.name if order.currency_id else 'VND',
            'OrderTotal': float(order.amount_total or 0.0),
            'Customer': self._serialize_customer_request(order.partner_id),
            'LineItems': line_items,
        }

    # API lấy danh sách Sales Orders định dạng SORequest cho Acumatica (Chỉ chấp nhận POST)
    @http.route(
        ['/api/v1/sale/orders', '/api/v1/sale/order/list'],
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def get_sale_orders(self, **params):
        try:
            # Nhận body JSON khi gọi bằng POST
            try:
                raw_body = request.httprequest.get_data(as_text=True)
                if raw_body:
                    body_json = json.loads(raw_body)
                    if isinstance(body_json, dict):
                        params = {**params, **body_json}
            except Exception:
                pass

            domain = []

            # Lọc theo state nếu có (vd: sale, draft)
            state = params.get('state')
            if state:
                states = [s.strip() for s in state.split(',') if s.strip()]
                if states:
                    domain.append(('state', 'in', states))

            # Lọc theo trạng thái đồng bộ Acumatica
            acu_status = params.get('acumatica_so_status') or params.get('status')
            if acu_status:
                domain.append(('x_acumatica_so_status', '=', acu_status))

            # Lọc theo ID hoặc danh sách IDs
            ids_param = params.get('ids')
            order_id = params.get('id') or params.get('order_id')
            if ids_param:
                try:
                    target_ids = [int(i.strip()) for i in str(ids_param).split(',') if i.strip()]
                    if target_ids:
                        domain.append(('id', 'in', target_ids))
                except ValueError:
                    return request.make_json_response({'success': False, 'message': 'ids không hợp lệ'}, status=400)
            elif order_id:
                try:
                    domain.append(('id', '=', int(order_id)))
                except ValueError:
                    return request.make_json_response({'success': False, 'message': 'order_id không hợp lệ'}, status=400)

            # Lọc theo tên đơn (vd: S00033)
            order_name = params.get('name') or params.get('order_name')
            if order_name:
                domain.append(('name', 'ilike', str(order_name).strip()))

            # Tìm kiếm từ khóa chung (q hoặc search)
            search = (params.get('search') or params.get('q') or '').strip()
            if search:
                domain_search = ['|', '|', ('name', 'ilike', search), ('x_acumatica_so_number', 'ilike', search), ('partner_id.name', 'ilike', search)]
                if search.isdigit():
                    domain_search = ['|'] + domain_search + [('id', '=', int(search))]
                domain.extend(domain_search)

            # Phân trang
            try:
                page = max(1, int(params.get('page', 1)))
                limit = min(200, max(1, int(params.get('limit', 20))))
            except ValueError:
                page, limit = 1, 20
            offset = (page - 1) * limit

            admin_user = request.env.ref('base.user_admin', raise_if_not_found=False) or request.env.ref('base.user_root')
            order_model = request.env['sale.order'].with_user(admin_user)

            total_records = order_model.search_count(domain)
            orders = order_model.search(domain, offset=offset, limit=limit, order='id desc')

            data = [self._serialize_so_request(o) for o in orders]

            return request.make_json_response({
                'success': True,
                'message': 'Success',
                'total': total_records,
                'page': page,
                'limit': limit,
                'total_pages': (total_records + limit - 1) // limit if limit else 1,
                'data': data,
            }, status=200)
        except Exception as e:
            _logger.error('Lỗi khi gọi API get_sale_orders: %s', e, exc_info=True)
            return request.make_json_response({'success': False, 'message': f'Internal Server Error: {str(e)}'}, status=500)

    # API lấy thông tin chi tiết một Sales Order định dạng SORequest (Chỉ chấp nhận POST)
    @http.route(
        ['/api/v1/sale/orders/<int:order_id>', '/api/v1/sale/order/detail'],
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def get_sale_order_detail(self, order_id=None, **params):
        try:
            # Nhận body JSON khi gọi bằng POST
            try:
                raw_body = request.httprequest.get_data(as_text=True)
                if raw_body:
                    body_json = json.loads(raw_body)
                    if isinstance(body_json, dict):
                        params = {**params, **body_json}
            except Exception:
                pass

            target_id = order_id or params.get('order_id') or params.get('id')
            order_name = params.get('order_name') or params.get('name')

            domain = []
            if target_id:
                try:
                    domain = [('id', '=', int(target_id))]
                except ValueError:
                    return request.make_json_response({'success': False, 'message': 'order_id không hợp lệ'}, status=400)
            elif order_name:
                domain = [('name', '=', str(order_name).strip())]
            else:
                return request.make_json_response({'success': False, 'message': 'Thiếu tham số order_id hoặc order_name'}, status=400)

            admin_user = request.env.ref('base.user_admin', raise_if_not_found=False) or request.env.ref('base.user_root')
            order = request.env['sale.order'].with_user(admin_user).search(domain, limit=1)
            if not order:
                return request.make_json_response({'success': False, 'message': 'Không tìm thấy đơn hàng trong Odoo'}, status=404)

            return request.make_json_response({
                'success': True,
                'message': 'Success',
                'data': self._serialize_so_request(order),
            }, status=200)
        except Exception as e:
            _logger.error('Lỗi khi gọi API get_sale_order_detail: %s', e, exc_info=True)
            return request.make_json_response({'success': False, 'message': f'Internal Server Error: {str(e)}'}, status=500)

    # API lấy danh sách Khách hàng định dạng CustomerRequest cho Acumatica (Chỉ chấp nhận POST)
    @http.route(
        ['/api/v1/sale/customers', '/api/v1/sale/customer/list'],
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def get_customers(self, **params):
        try:
            # Nhận body JSON khi gọi bằng POST
            try:
                raw_body = request.httprequest.get_data(as_text=True)
                if raw_body:
                    body_json = json.loads(raw_body)
                    if isinstance(body_json, dict):
                        params = {**params, **body_json}
            except Exception:
                pass

            domain = [('customer_rank', '>', 0)] if params.get('customer_only') == 'true' else [('active', '=', True)]

            # Mặc định chỉ lấy khách hàng chính cấp cao nhất (loại bỏ các địa chỉ con trùng lặp)
            if params.get('include_children') != 'true' and not (params.get('ids') or params.get('id') or params.get('customer_id')):
                domain.append(('parent_id', '=', False))

            # Lọc theo ID hoặc danh sách IDs
            ids_param = params.get('ids')
            customer_id = params.get('id') or params.get('customer_id')
            if ids_param:
                try:
                    target_ids = [int(i.strip()) for i in str(ids_param).split(',') if i.strip()]
                    if target_ids:
                        domain.append(('id', 'in', target_ids))
                except ValueError:
                    return request.make_json_response({'success': False, 'message': 'ids không hợp lệ'}, status=400)
            elif customer_id:
                try:
                    domain.append(('id', '=', int(customer_id)))
                except ValueError:
                    return request.make_json_response({'success': False, 'message': 'customer_id không hợp lệ'}, status=400)

            # Lọc theo mã Acumatica (AcctCD)
            acct_cd = (params.get('acct_cd') or params.get('x_customer_code') or '').strip()
            if acct_cd:
                domain.append(('x_customer_code', '=ilike', acct_cd))

            # Lọc khách hàng có/chưa có mã Acumatica
            if params.get('has_acumatica_code') == 'true':
                domain.append(('x_customer_code', '!=', False))
            elif params.get('has_acumatica_code') == 'false':
                domain.append(('x_customer_code', '=', False))

            # Lọc theo nguồn tạo (odoo hoặc acumatica)
            created_from = (params.get('created_from') or '').strip().lower()
            if created_from in ('odoo', 'acumatica'):
                domain.append(('x_created_from', '=', created_from))

            # Tìm kiếm từ khóa (q hoặc search)
            search = (params.get('search') or params.get('q') or '').strip()
            if search:
                domain_search = ['|', '|', '|', ('name', 'ilike', search), ('x_customer_code', 'ilike', search), ('phone', 'ilike', search), ('email', 'ilike', search)]
                domain.extend(domain_search)

            # Phân trang
            try:
                page = max(1, int(params.get('page', 1)))
                limit = min(200, max(1, int(params.get('limit', 50))))
            except ValueError:
                page, limit = 1, 50
            offset = (page - 1) * limit

            admin_user = request.env.ref('base.user_admin', raise_if_not_found=False) or request.env.ref('base.user_root')
            partner_model = request.env['res.partner'].with_user(admin_user)

            total_records = partner_model.search_count(domain)
            partners = partner_model.search(domain, offset=offset, limit=limit, order='id desc')

            data = [self._serialize_customer_request(p) for p in partners]

            return request.make_json_response({
                'success': True,
                'message': 'Success',
                'total': total_records,
                'page': page,
                'limit': limit,
                'total_pages': (total_records + limit - 1) // limit if limit else 1,
                'data': data,
            }, status=200)
        except Exception as e:
            _logger.error('Lỗi khi gọi API get_customers: %s', e, exc_info=True)
            return request.make_json_response({'success': False, 'message': f'Internal Server Error: {str(e)}'}, status=500)

    # API tìm kiếm Sales Orders bằng phương thức POST với JSON payload
    @http.route(
        ['/api/v1/sale/orders/search', '/api/v1/sale/order/search'],
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def search_sale_orders(self, **kwargs):
        try:
            raw_body = request.httprequest.get_data(as_text=True)
            params = json.loads(raw_body) if raw_body else {}
        except Exception as e:
            return request.make_json_response({'success': False, 'message': f'Invalid JSON format: {str(e)}'}, status=400)

        return self.get_sale_orders(**params)

