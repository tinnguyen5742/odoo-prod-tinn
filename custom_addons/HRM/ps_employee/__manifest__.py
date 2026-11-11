{
    'name': 'Patsoft Employee(19.0.7)',
    'version': '19.0.7.1.2',
    'category': 'PatSoft/Employees',
    'summary': 'Thêm thông tin cho nhân viên',
    'description': """
        Module mở rộng nhân viên với thông tin:
        - Bằng cấp / Văn bằng
        - Trình độ chính trị
        - Ngoại ngữ
        - Tin học
        - Bảo hiểm
    """,
    'author': 'PatSoft',
    'depends': ['hr', 'hr_recruitment', 'account', 'stock', 'ps_vn_address'],
    'data': [
        'security/ir.model.access.csv',
        'security/employee_security.xml',
        'data/hr_level_data.xml',
        'data/hr_contract_data.xml',
        'data/hr_grade_data.xml',
        'views/hr_employee_views.xml',
        'views/hr_department_views.xml',
        'views/hr_level_views.xml',
        'views/hr_contract_views.xml',
        'views/hr_contract_mass_views.xml',
        'views/hr_grade_views.xml',
        'views/hr_salary_grade_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
