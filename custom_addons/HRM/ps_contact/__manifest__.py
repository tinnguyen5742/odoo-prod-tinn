{
    'name': 'Patsoft Contact',
    'version': '19.0.1.0.0',
    'category': 'PatSoft/Contacts',
    'summary': 'Mở rộng contacts với convert địa chỉ VN',
    'description': """
        Thêm field "Vị trí trước sáp nhập" trên đối tác (res.partner).
        Khi nhập địa chỉ cũ, hệ thống tự động convert sang địa chỉ mới
        theo quyết định sáp nhập đơn vị hành chính và ghi vào các trường
        địa chỉ chuẩn của Odoo.
    """,
    'author': 'PatSoft',
    'company': 'PatSoft',
    'maintainer': 'PatSoft',
    'depends': ['contacts', 'ps_vn_address'],
    'data': [
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
