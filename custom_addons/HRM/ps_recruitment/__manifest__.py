{
    'name': 'Patsoft Recruitment(19.0.1)',
    'version': '19.0.1.0.0',
    'summary': 'Mở rộng module Tuyển dụng - Thêm thông tin ứng viên',
    'description': """
        Module mở rộng hr.applicant:
        - Thêm trường ngày sinh (x_birth_date)
        - Thêm trường địa chỉ (x_address)
        - Thêm trường giới tính (x_gender)
        - Hiển thị các trường trên khi ở giai đoạn "Phỏng vấn lần 2"
    """,
    'author': 'PatSoft',
    'category': 'Recruitment',
    'depends': ['hr_recruitment','ps_employee'],
    'data': [
        'data/ir_sequence_data.xml',
        'views/ps_recruitment_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ps_recruitment/static/src/css/style.css',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
