from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class VnAccountingCostCenter(models.Model):
    """Trung tâm chi phí (Cost center) dùng cho báo cáo kế toán Việt Nam."""
    _name = "ps.vn.accounting.cost.center"
    _description = "Accounting Cost Center"
    _parent_store = True  # Bật tối ưu phân cấp cha-con
    _rec_name = "complete_name"
    _order = "sequence, code, id"

    # Công ty áp dụng
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )

    # Thông tin cơ bản
    code = fields.Char(string="Code", required=True, help="Cost Center Code")
    name = fields.Char(string="Name", required=True, help="Cost Center Name")
    complete_name = fields.Char(
        string="Complete Name",
        compute="_compute_complete_name",
        recursive=True,
        store=True,
    )

    # Phân cấp cha - con
    parent_id = fields.Many2one(
        "ps.vn.accounting.cost.center",
        string="Parent Cost Center",
        index=True,
        ondelete="restrict",
    )
    child_ids = fields.One2many(
        "ps.vn.accounting.cost.center",
        "parent_id",
        string="Child Cost Centers",
    )
    parent_path = fields.Char(index=True)

    # Thông tin bổ sung
    manager_id = fields.Many2one("res.users", string="Manager")
    sequence = fields.Integer(string="Sequence", default=10)
    description = fields.Text(string="Description")
    enabled = fields.Boolean(string="Enabled", default=True)

    # Ràng buộc mã Cost center duy nhất trong mỗi công ty
    _unique_code_per_company = models.Constraint(
        'UNIQUE (company_id, code)',
        'The cost center code must be unique per company.',
    )

    # Kiểm tra không cho phép vòng lặp phân cấp
    @api.constrains("parent_id")
    def _check_cost_center_recursion(self):
        if self._has_cycle():
            raise ValidationError(_("You cannot create recursive cost centers."))

    # Hiển thị tên dạng [mã] tên
    @api.depends_context("hierarchical_naming")
    def _compute_display_name(self):
        if self.env.context.get("hierarchical_naming", True):
            return super()._compute_display_name()
        for record in self:
            record.display_name = f"[{record.code}] {record.name}"

    # Tính tên đầy đủ theo phân cấp cha/con
    @api.depends("code", "name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for center in self:
            name = f"[{center.code}] {center.name}"
            if center.parent_id:
                center.complete_name = "%s / %s" % (
                    center.parent_id.complete_name,
                    name,
                )
            else:
                center.complete_name = name
