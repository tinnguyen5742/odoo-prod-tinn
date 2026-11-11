# -*- coding: utf-8 -*-
{
    'name': 'Patsoft Sale',
    'version': '19.0.1.0.0',
    'category': 'PatSoft/Sales',
    'summary': 'Mở rộng Báo giá và Đơn hàng với Acumatica (CustomerCD, OrderType, Vật tư, ĐVT, Thuế)',
    'description': """
        Module mở rộng nghiệp vụ Bán hàng (Sales):
        - Hiển thị Mã khách hàng (Acu) - CustomerCD trên màn hình Báo giá & Đơn hàng
        - Quản lý và chọn Loại SO (SO Order Type) đồng bộ từ Acumatica API
        - Quản lý và chọn Danh mục Vật tư (inventories) từ Acumatica API
        - Quản lý và chọn Danh mục Đơn vị tính (ItemUnit) từ Acumatica API
        - Quản lý và chọn Danh mục Thuế (vat) từ Acumatica API
    """,
    'author': 'PatSoft',
    'company': 'PatSoft',
    'maintainer': 'PatSoft',
    'depends': ['sale_management', 'sale_pdf_quote_builder', 'ps_contact'],
    'data': [
        'security/ir.model.access.csv',
        'data/ps_sale_order_type_data.xml',
        'views/ps_sale_order_type_views.xml',
        'views/ps_sale_dictionary_views.xml',
        'views/sale_order_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
