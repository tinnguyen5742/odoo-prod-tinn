{
    'name': 'Patsoft Attendance Management(19.0.3)',
    'version': '19.0.3.0.0',
    'category': 'PatSoft/Attendances',
    'summary': """GPS check in/out location and work shift management
        """,
    'author': 'PATSOFT',
    'depends': ['hr_attendance'],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/ps_work_month_data.xml',
        'views/hr_attendance_views.xml',
        'views/ps_work_shift_views.xml',
        'views/ps_public_holiday_views.xml',
        'views/ps_shift_rotation_views.xml',
        'views/ps_work_schedule_registration_views.xml',
        'views/ps_overtime_registration_views.xml',
        'views/ps_shift_change_views.xml',
        'views/ps_shift_schedule_views.xml',
        'views/menus.xml',
        'data/cron.xml',
    ],
    'assets': {
            'web.assets_backend': [ 
                'ps_attendance_management/static/src/scss/styles.scss', 
            ],
    },

    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
