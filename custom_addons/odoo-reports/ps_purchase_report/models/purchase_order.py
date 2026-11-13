from odoo import models, fields, api
from odoo.exceptions import UserError

class PurchaseOrder(models.Model):
    # Kế thừa mở rộng model purchase_order của Odoo 19.0
    _inherit = 'purchase.order'

    # 1. Thêm một trường dữ liệu mới
    x_ly_do_mua_hang = fields.Text(string='Lý do mua hàng (Custom)')
    x_is_urgent = fields.Boolean(string='Đơn khẩn cấp', default=False)

    def action_custom_check(self):
        for order in self:
            # Thêm logic xử lý của bạn ở đây. Ví dụ:
            order.message_post(body="Đã chạy kiểm tra nội bộ thành công!")
        return True

    # 2. Ghi đè (Override) hàm chuẩn của Odoo 19.0 (Ví dụ hàm Xác nhận đơn)
    def button_confirm(self):
        # Chạy logic kiểm tra của riêng bạn trước
        for order in self:
            if order.x_is_urgent and not order.x_ly_do_mua_hang:
                raise UserError("Vui lòng nhập lý do mua hàng cho đơn khẩn cấp!")

        # Gọi lại hàm button_confirm gốc của module purchase bằng super()
        # Điều này đảm bảo Odoo vẫn chạy các luồng tính toán tồn kho, kế toán mặc định
        res = super(PurchaseOrder, self).button_confirm()

        # Bạn có thể thêm logic gì đó sau khi Odoo chạy xong (vd: gửi email)
        return res