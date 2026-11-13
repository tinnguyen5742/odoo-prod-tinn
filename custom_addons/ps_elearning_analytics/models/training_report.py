from odoo import fields, models
from odoo.tools import drop_view_if_exists


class ElearningTrainingReport(models.Model):
    _name = "elearning.training.report"
    _description = "Employee eLearning Progress"
    _auto = False
    _rec_name = "course_id"
    _order = "deadline_date, course_id, employee_id"

    course_id = fields.Many2one("slide.channel", string="Course", readonly=True)
    employee_id = fields.Many2one("hr.employee", string="Employee", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Learner", readonly=True)
    department_id = fields.Many2one("hr.department", string="Department", readonly=True)
    job_id = fields.Many2one("hr.job", string="Job Position", readonly=True)
    manager_id = fields.Many2one("hr.employee", string="Manager", readonly=True)
    responsible_id = fields.Many2one("res.users", string="Course Responsible", readonly=True)
    member_status = fields.Selection(
        [
            ("invited", "Invited"),
            ("joined", "Not Started"),
            ("ongoing", "In Progress"),
            ("completed", "Completed"),
        ],
        string="Status",
        readonly=True,
    )
    completion = fields.Integer(string="Completion (%)", readonly=True)
    deadline_date = fields.Date(string="Deadline", readonly=True)
    is_overdue = fields.Boolean(string="Overdue", readonly=True)
    enrollment_count = fields.Integer(string="Enrollments", readonly=True)

    def init(self):
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"""
            CREATE VIEW {self._table} AS (
                SELECT
                    enrollment.id AS id,
                    enrollment.channel_id AS course_id,
                    employee.id AS employee_id,
                    enrollment.partner_id AS partner_id,
                    employee.department_id AS department_id,
                    employee.job_id AS job_id,
                    employee.parent_id AS manager_id,
                    course.user_id AS responsible_id,
                    enrollment.member_status AS member_status,
                    COALESCE(enrollment.completion, 0) AS completion,
                    enrollment.deadline_date AS deadline_date,
                    COALESCE(
                        enrollment.deadline_date < CURRENT_DATE
                        AND enrollment.member_status != 'completed',
                        FALSE
                    ) AS is_overdue,
                    1 AS enrollment_count
                FROM slide_channel_partner enrollment
                JOIN slide_channel course ON course.id = enrollment.channel_id
                LEFT JOIN LATERAL (
                    SELECT
                        employee.id,
                        employee.parent_id,
                        employee_version.department_id,
                        employee_version.job_id
                    FROM hr_employee employee
                    JOIN res_users account ON account.id = employee.user_id
                    LEFT JOIN hr_version employee_version
                        ON employee_version.id = employee.current_version_id
                    WHERE account.partner_id = enrollment.partner_id
                      AND employee.active
                    ORDER BY employee.id
                    LIMIT 1
                ) employee ON TRUE
                WHERE enrollment.active
            )
            """
        )
