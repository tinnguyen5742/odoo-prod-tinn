from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..scripts.feed_demo_data import run_seed


class FeedDemoDataWizard(models.TransientModel):
    _name = "ps.mfg.feed.demo.wizard"
    _description = "Wizard Nạp Dữ Liệu Mẫu Sản Xuất"

    is_demo_db = fields.Boolean(
        string="Database Demo?",
        default=lambda self: self._check_is_demo(),
        readonly=True,
    )
    confirm_force = fields.Boolean(
        string="Tôi hiểu rủi ro và xác nhận muốn nạp dữ liệu mẫu vào database này",
        default=False,
    )

    @api.model
    def _check_is_demo(self):
        """Kiểm tra cờ demo của database dựa trên module base hoặc bất kỳ module nào."""
        base_mod = self.env.ref("base.module_base", raise_if_not_found=False)
        if base_mod and base_mod.demo:
            return True
        return bool(self.env["ir.module.module"].search_count([("demo", "=", True)]))

    def action_proceed_seed(self):
        self.ensure_one()
        # Chỉ Quản trị viên mới được thực thi
        if not self.env.user.has_group("base.group_system"):
            raise UserError(
                _("Chỉ Quản trị viên hệ thống (Admin) mới có quyền nạp dữ liệu mẫu!")
            )

        # Chặn nếu DB không phải demo và user chưa tick xác nhận rủi ro
        if not self.is_demo_db and not self.confirm_force:
            raise UserError(
                _(
                    "CẢNH BÁO: Database này không được gắn cờ Demo Data (rất có thể là Production hoặc DB thực tế)!\n\n"
                    "Vui lòng tích vào ô 'Tôi hiểu rủi ro và xác nhận muốn nạp dữ liệu mẫu vào database này' trước khi bấm tiếp tục."
                )
            )

        # Thực thi nạp toàn bộ kịch bản demo data
        run_seed(self.env)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Nạp dữ liệu thành công!"),
                "message": _(
                    "Đã nạp toàn bộ kịch bản dữ liệu mẫu Manufacturing (MO, BoM, Đề nghị chuyển kho, WIP) thành công!"
                ),
                "type": "success",
                "sticky": False,
            },
        }
