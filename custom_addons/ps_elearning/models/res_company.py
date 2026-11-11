from odoo import models, fields


# Bảng map index color_picker (0-11) -> hex color (theo $o-colors của Odoo)
COLOR_PALETTE = [
    '#a2a2a2',  # 0  - xám
    '#ee2d2d',  # 1  - đỏ
    '#dc8534',  # 2  - cam
    '#e8bb1d',  # 3  - vàng
    '#5794dd',  # 4  - xanh dương
    '#9f628f',  # 5  - tím nhạt
    '#db8865',  # 6  - cam đất
    '#41a9a2',  # 7  - xanh ngọc
    '#304be0',  # 8  - xanh dương đậm
    '#ee2f8a',  # 9  - hồng
    '#61c36e',  # 10 - xanh lá
    '#9872e6',  # 11 - tím violet
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    cert_secondary_color = fields.Char(
        string='Màu phụ chứng nhận',
        default='#d4af37',
        help='Màu dùng cho khung, sao, viền phụ của chứng nhận (mặc định vàng).',
    )
    cert_company_name = fields.Char(
        string='Tên công ty trên chứng nhận',
        help='Tên hiển thị ở dòng "Công ty ABC trân trọng chứng nhận".',
    )
    cert_signature = fields.Image(
        string='Chữ ký/Đóng dấu',
        help='Ảnh chữ ký hoặc con dấu của đại diện công ty.',
    )
    cert_primary_hex = fields.Char(
        string='Màu chính (hex)',
        compute='_compute_cert_primary_hex',
         compute_sudo=True, #sửa lỗi 403(khi User portal(neu khong can co the bo))
        help='Màu chính của chứng nhận, map từ color picker của công ty.',
    )

    def _compute_cert_primary_hex(self):
        for company in self:
            idx = company.color if company.color is not None else 0
            if idx is None or idx < 0 or idx >= len(COLOR_PALETTE):
                idx = 0
            company.cert_primary_hex = COLOR_PALETTE[idx]
