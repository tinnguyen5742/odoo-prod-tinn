{
    "name": "Currency Exchange",
    "version": "1.0.0",
    "author": "PatSoft",
    "category": "Patsoft",
    "summary": "Fetch realtime FX rates (Vietcombank) into Odoo",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "views/fx_rate_views.xml",
        "views/fx_api_log_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
