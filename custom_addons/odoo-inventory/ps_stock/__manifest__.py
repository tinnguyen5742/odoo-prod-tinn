{
    'name': 'Patsoft Stock',
    'version': '19.0.0.4',
    'description': 'PatSoft Stock',
    'category': 'PatSoft/Stock',
    'depends': [
        'ps_sequence',
        'web', 'stock'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/product_category_views.xml',
        'views/product_views.xml',
        'views/menus.xml',

    ],
    'post_init_hook': 'post_init_hook',
    'application': True,
    'author': 'PatSoft',
    'license': 'LGPL-3',
}
