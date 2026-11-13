{
    "name": "PATSOFT eLearning Reports",
    "summary": "PDF and analytical reports for Odoo eLearning",
    "version": "19.0.5.0.0",
    "category": "Productivity",
    "author": "PATSOFT",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "website_slides",
    ],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "security/rules.xml",
        "data/paperformats.xml",
        "templates/report_training_progress.xml",
        "data/report_actions.xml",
        "views/training_report_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
