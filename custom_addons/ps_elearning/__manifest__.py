{
    'name': 'Patsoft Elearning(19.1.5)',
    'version': '19.0.1.0.5',
    'category': 'PatSoft/Elearning',
    'summary': 'Thêm thông tin cho Elearning',
    'description': """
        Them button quay lai du an
    """,
    'author': 'PatSoft',
    'depends': ['website_slides', 'mail', 'survey', 'hr', 'hr_recruitment'],
    'data': [
        'views/slide_channel_views.xml',
        'views/survey_start_templates.xml',
        'views/survey_in_template.xml',
        'views/survey_end_templates.xml',
        'views/survey_user_input_views.xml',
        'views/res_company_views.xml',
        'views/hr_job_views.xml',
        'views/website_slides_templates.xml',
        'report/certificate_template.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ps_elearning/static/src/js/ai_chat_modal.js',
            'ps_elearning/static/src/js/back_to_course.js',
            'ps_elearning/static/src/xml/ai_chat_button.xml',
        ],
        'web.assets_frontend': [
            'ps_elearning/static/src/js/course_evaluation_reload.js',
            'ps_elearning/static/src/scss/survey_start.scss',
            'ps_elearning/static/src/scss/survey_in.scss',
            'ps_elearning/static/src/scss/survey_end.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
