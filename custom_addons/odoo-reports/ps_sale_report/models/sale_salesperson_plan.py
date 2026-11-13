from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SaleSalespersonPlan(models.Model):
    _name = "ps.sale.salesperson.plan"
    _description = "Kế hoạch doanh thu và sản lượng Sales"
    _rec_name = "salesperson_id"
    _order = "date_from desc, salesperson_id"
    _check_company_auto = True

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, string="Công ty")
    currency_id = fields.Many2one(related="company_id.currency_id", string="Loại tiền")
    salesperson_id = fields.Many2one("res.users", required=True, string="Nhân viên Sales", domain=[("share", "=", False)])
    date_from = fields.Date("Từ ngày", required=True)
    date_to = fields.Date("Đến ngày", required=True)
    planned_m2 = fields.Float("SL kế hoạch (M²)", digits=(16, 4))
    planned_revenue = fields.Monetary("DT kế hoạch chưa thuế", currency_field="currency_id")

    _period_unique = models.Constraint(
        "UNIQUE(company_id, salesperson_id, date_from, date_to)",
        "Đã có kế hoạch cho Sales, công ty và khoảng ngày này.",
    )

    @api.constrains("date_from", "date_to", "planned_m2", "planned_revenue", "salesperson_id", "company_id")
    def _check_plan(self):
        for plan in self:
            if plan.date_from > plan.date_to:
                raise ValidationError("Từ ngày không được lớn hơn đến ngày.")
            if plan.planned_m2 < 0 or plan.planned_revenue < 0:
                raise ValidationError("Kế hoạch số lượng và doanh thu không được âm.")
            if plan.company_id not in plan.salesperson_id.company_ids:
                raise ValidationError("Nhân viên Sales không được phép sử dụng công ty này.")
