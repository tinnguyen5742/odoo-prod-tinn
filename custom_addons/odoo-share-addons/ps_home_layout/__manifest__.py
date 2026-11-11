{
    'name': 'PS Home Menu & Custom Layout',
    'version': '1.0',
    'category': 'Themes/PatSoft',
    'summary': 'Custom Odoo Home and Layout',
    'depends': ['web', 'base'],
    'data': [
        # Home Menu View
        'views/home_menu.xml',
    
        # Custom Theme Color Views
        'views/company_theme_color_views.xml',
        'views/company_theme_assets.xml',

        # Custom login
        'views/login_template.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # SCSS
            'ps_home_layout/static/src/css/loading_overlay.scss',
            'ps_home_layout/static/src/css/navbar_custom.scss',
            'ps_home_layout/static/src/css/home_template.scss',
            # JS
            'ps_home_layout/static/src/js/home_action.js',
            'ps_home_layout/static/src/js/navbar_custom.js',
            'ps_home_layout/static/src/js/lang_switcher.js',
            
            # XML Templates
            'ps_home_layout/static/src/xml/home_template.xml',

            # Custom Form Status Indicator
            'ps_home_layout/static/src/xml/form_status_indicator_custom.xml',

            # Đường dẫn đến file JS logger (Thay "ps_theme_company_color" bằng tên thư mục module của bạn)
            'ps_home_layout/static/src/js/company_theme_assets.js',
        ],
        'web.assets_frontend': [
            'ps_home_layout/static/src/css/login_template.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': True,
    'license': 'LGPL-3',
}