from odoo import api, fields, models


class SlideChannelPartner(models.Model):
    _inherit = "slide.channel.partner"

    deadline_date = fields.Date(index=True, copy=False)
    employee_id = fields.Many2one(
        "hr.employee",
        compute="_compute_employee_id",
        store=True,
        index=True,
        compute_sudo=True,
    )

    @api.depends("partner_id")
    def _compute_employee_id(self):
        employees = self.env["hr.employee"].sudo().search(
            [("user_id.partner_id", "in", self.partner_id.ids), ("active", "=", True)]
        )
        by_partner = {}
        for employee in employees:
            by_partner.setdefault(employee.user_id.partner_id.id, employee)
        for enrollment in self:
            enrollment.employee_id = by_partner.get(enrollment.partner_id.id)
