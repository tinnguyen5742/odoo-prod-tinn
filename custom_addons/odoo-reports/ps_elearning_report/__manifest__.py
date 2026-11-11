{
    "name": "PS eLearning Reports",
    "summary": "Báo cáo PDF eLearning: từng khóa học và tổng hợp khóa học",
    "version": "19.0.1.0.0",
    "author": "PS",
    "category": "Website/eLearning",
    "license": "LGPL-3",
    "depends": ["web", "website_slides"],
    "data": [
        "security/ir.model.access.csv",
        "report/paperformat.xml",
        "report/report_course_summary.xml",
        "report/report_courses_overview.xml",
        "views/ir_actions_report_views.xml",
        "views/slide_channel_report_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
