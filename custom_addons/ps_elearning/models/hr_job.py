from odoo import models, fields

class HrJob(models.Model):
    _inherit = 'hr.job'

    mandatory_course_ids = fields.Many2many(
        'slide.channel',
        string="Mandatory Courses",
        help="Mandatory courses for employees in this job position."
    )