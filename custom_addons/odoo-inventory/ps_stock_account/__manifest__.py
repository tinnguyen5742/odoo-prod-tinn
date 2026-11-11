{
    'name': 'Patsoft Stock',
    'version': '19.0.0.3',
    'description': 'PatSoft Stock Account',
    'category': 'PatSoft/Stock',
    'depends': ['ps_stock', 'stock', 'account', 'stock_account'],
    'data': [
        'data/cost_method_defaults.xml',
        'views/stock_warehouse_views.xml',
        'views/product_category_views.xml',
        'views/onhand_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'application': False,
    'auto_install': True,
    'author': 'PatSoft',
    'license': 'LGPL-3'
}
