# -*- coding: utf-8 -*-
{
    'name': 'Patsoft Sale API',
    'version': '19.0.1.0.0',
    'category': 'PatSoft/Sales',
    'summary': 'REST API backend trao đổi dữ liệu Sales Order giữa Odoo và Acumatica Gateway',
    'description': """
        Module cung cấp các REST API cho hệ thống Acumatica Gateway:
        - Nhận cập nhật số SO Acumatica và ngày tạo SO vào Báo giá Odoo
        - Tra cứu thông tin Báo giá / Đơn hàng Odoo cho phía Acumatica
    """,
    'author': 'PatSoft',
    'company': 'PatSoft',
    'maintainer': 'PatSoft',
    'depends': ['ps_sale'],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}

