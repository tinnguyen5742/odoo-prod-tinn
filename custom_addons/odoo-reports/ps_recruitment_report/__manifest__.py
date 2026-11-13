{
    "name": "PS Recruitment Reports",
    "summary": "Báo cáo PDF Tuyển dụng (Danh sách vị trí và Ứng viên theo vị trí)",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Recruitment",
    "author": "PATSOFT",
    "license": "LGPL-3",
    "depends": [
        "web",
        "hr_recruitment",
        "hr_recruitment_skills",
        "website_hr_recruitment",
    ],
    "data": [
        "views/recruitment_report_rules.xml",
        "views/recruitment_job_positions_report.xml",
        "views/recruitment_applicants_by_job_report.xml",
    ],
    "installable": True,
    "application": False,
}
