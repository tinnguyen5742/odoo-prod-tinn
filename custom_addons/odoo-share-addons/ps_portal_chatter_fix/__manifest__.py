{
    'name': 'Patsoft Portal Chatter Fix',
    'version': '19.0.1.0.0',
    'category': 'PatSoft/Technical',
    'summary': 'Workaround for Odoo 19 portal chatter template duplicate bug',
    'description': """
        Odoo 19 build >= 20260324 has a core bug where portal.assets_chatter
        includes html_editor.assets_editor, whose XML templates are already
        loaded by web.assets_frontend_lazy. This causes registerTemplate() to
        throw "Template html_editor.MediaDialog already exists" and the whole
        portal.assets_chatter.bundle.xml module fails, preventing portal.Chatter
        from being registered.

        This module removes html_editor XML templates from portal.assets_chatter
        while keeping the JS assets, so the portal chatter can load correctly.
    """,
    'author': 'PatSoft',
    'company': 'PatSoft',
    'maintainer': 'PatSoft',
    'depends': ['portal'],
    'data': [],
    'assets': {
        'portal.assets_chatter': [
            # Remove html_editor XML templates already present in web.assets_frontend_lazy
            # to avoid "Template html_editor.MediaDialog already exists" error.
            ('remove', 'html_editor/static/src/**/*.xml'),
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
