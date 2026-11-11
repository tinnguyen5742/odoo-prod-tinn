{
    'name': 'Patsoft CRM(19.0.1)',
    'version': '19.0.1.0.1',
    'category': 'PatSoft/CRM',
    'summary': 'Thêm thông tin cho CRM',
    'description': """
        Them button quay lai du an
    """,
    'author': 'PatSoft',
    'depends': ['crm','project','mail','ps_contact'],
    'data': [
        'security/crm_security.xml',
        'views/crm_lead_views.xml',
        'views/crm_lead_convert_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ps_crm/static/src/js/back_to_crm.js',
            'ps_crm/static/src/js/discuss_actions.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
