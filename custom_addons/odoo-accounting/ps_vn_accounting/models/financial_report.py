from datetime import date

from odoo import api, fields, models


class PsFinancialReportTemplate(models.Model):
    """Mẫu báo cáo tài chính, ví dụ: TT99-BCDKT, TT99-KQKD."""
    _name = "ps.financial.report.template"
    _description = "Financial Report Template"
    _order = "x_code, id"

    # Mã mẫu báo cáo
    x_code = fields.Char(string="Template Code", required=True, index=True)
    # Tên mẫu báo cáo
    x_name = fields.Char(string="Template Name", required=True)
    # Mô tả mẫu báo cáo
    x_description = fields.Text(string="Description")
    # Trạng thái còn sử dụng
    x_active = fields.Boolean(string="Active", default=True)
    # Số lượng công thức của mẫu
    x_formula_count = fields.Integer(
        string="Formula Count",
        compute="_compute_x_formula_count",
        store=True,
    )
    # Danh sách công thức thuộc mẫu
    x_formula_ids = fields.One2many(
        "ps.financial.report.formula",
        "x_template_id",
        string="Formulas",
    )

    def action_open_report_wizard(self):
        """Mở wizard in báo cáo cho mẫu hiện tại."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Print Financial Report",
            "res_model": "ps.financial.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_x_template_id": self.id},
        }

    def action_preview_report(self):
        """Xem trước báo cáo tài chính ở tab mới (HTML preview)."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        wizard = self.env["ps.financial.report.wizard"].create({
            "x_template_id": self.id,
            "x_company_id": self.env.company.id,
            "x_date_from": date(today.year, 1, 1),
            "x_date_to": today,
        })
        return {
            "type": "ir.actions.act_url",
            "name": "Xem trước báo cáo",
            "url": f"/report/html/ps_vn_accounting.action_report_financial_tt99_bcdkt/{wizard.id}",
            "target": "new",
        }

    # Ràng buộc mã mẫu báo cáo là duy nhất
    _unique_x_code = models.Constraint(
        'UNIQUE (x_code)',
        'The template code must be unique.',
    )

    # Đếm số công thức của mẫu
    @api.depends("x_formula_ids")
    def _compute_x_formula_count(self):
        for template in self:
            template.x_formula_count = len(template.x_formula_ids)

    # Hiển thị tên dạng [mã] tên
    @api.depends("x_code", "x_name")
    def _compute_display_name(self):
        for template in self:
            template.display_name = f"[{template.x_code}] {template.x_name}"


class PsFinancialReportFormula(models.Model):
    """Công thức tính toán cho từng mẫu báo cáo tài chính."""
    _name = "ps.financial.report.formula"
    _description = "Financial Report Formula"
    _order = "x_sequence, x_code, id"

    # Mẫu báo cáo cha
    x_template_id = fields.Many2one(
        "ps.financial.report.template",
        string="Report Template",
        required=True,
        index=True,
        ondelete="cascade",
    )
    # Số thứ tự hiển thị
    x_sequence = fields.Integer(string="Sequence", default=10)
    # Mã công thức, ví dụ: @1114
    x_code = fields.Char(string="Formula Code")
    # Công thức tính toán
    x_formula = fields.Text(string="Formula")
    # Ghi chú/diễn giải công thức
    x_note = fields.Text(string="Note")
    # Tên chỉ tiêu hiển thị trên báo cáo
    x_label = fields.Char(string="Label")
    # Cấp độ thụt lề (0 = tổng, 1 = nhóm, 2 = chi tiết)
    x_level = fields.Integer(string="Level", default=2)
    # Phân loại dòng báo cáo
    x_line_type = fields.Selection(
        [
            ("section", "Phần / Mục lớn"),
            ("group", "Nhóm"),
            ("detail", "Chi tiết"),
            ("total", "Tổng cộng"),
        ],
        string="Line Type",
        default="detail",
    )
