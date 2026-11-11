{
    'name': 'Patsoft VN Address',
    'version': '19.0.1.0.0',
    'category': 'PatSoft/Technical',
    'summary': 'Dịch vụ convert địa chỉ Việt Nam',
    'description': """
        Cung cấp tiện ích parse và convert địa chỉ Việt Nam sang cấu trúc mới
        theo quyết định sáp nhập đơn vị hành chính. Các module khác có thể
        depends vào module này để sử dụng lại logic địa chỉ.
    """,
    'author': 'PatSoft',
    'company': 'PatSoft',
    'maintainer': 'PatSoft',
    'depends': ['base', 'base_setup'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
