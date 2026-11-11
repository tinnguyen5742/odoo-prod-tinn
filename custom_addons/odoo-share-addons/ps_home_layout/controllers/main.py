from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.database import Database

class CustomDatabaseManager(Database):

    @http.route('/web/database/selector', type='http', auth='none')
    def selector(self, **kw):
        response = super().selector(**kw)
        html = response.get_data(as_text=True)
        selector_css = """
        <style>
            .o_database_list > img.img-fluid,
            .o_database_list > .text-center.mt-2 {
                display: none !important;
            }
            .o_database_list > .list-group {
                padding-top: 5vh !important; 
            }
        </style>
        """
        response.set_data(html.replace('</head>', f'{selector_css}</head>', 1))
        return response

    @http.route('/web/database/manager', type='http', auth='none')
    def manager(self, **kw):
        # Kiểm tra xem user đã đăng nhập và có quyền system (Administrator) hay chưa
        has_permission = False
        if request.session.uid:
            user = request.env['res.users'].sudo().browse(request.session.uid)
            if user.has_group('base.group_system'):
                has_permission = True

        # Nếu có quyền admin, trả về giao diện quản lý database gốc bình thường
        if has_permission:
            return super().manager(**kw)

        # Nếu không có quyền, hiển thị trang thông báo tùy chỉnh gọn gàng, chuyên nghiệp
        html_content = """
        <!DOCTYPE html>
        <html lang="vi">
        <head>
            <meta charset="UTF-8">
            <title>Truy cập bị từ chối</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body class="bg-light d-flex align-items-center justify-content-center vh-100">
            <div class="card shadow-sm p-4 text-center" style="max-width: 400px; width: 100%; border-radius: 1rem;">
                <div class="card-body">
                    <div class="mb-3 text-danger">
                        <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" fill="currentColor" class="bi bi-shield-lock-fill" viewBox="0 0 16 16">
                            <path fill-rule="evenodd" d="M8 0c-.69 0-1.843.265-2.928.56-1.11.3-2.229.655-2.87 1.07A1.97 1.97 0 0 0 1 3.22V9c0 4.54 3.203 7.92 5.085 9.255.5.355 1.14.355 1.64 0C9.797 16.92 13 13.54 13 9V3.22a1.97 1.97 0 0 0-.202-1.59c-.641-.415-1.76-.77-2.87-1.07C9.843.265 8.69 0 8 0m0 5a1 1 0 1 1 0 2 1 1 0 0 1 0-2m2.5 5.5a.5.5 0 0 1-.5.5h-4a.5.5 0 0 1-.5-.5v-2a.5.5 0 0 1 .5-.5h4a.5.5 0 0 1 .5.5z"/>
                        </svg>
                    </div>
                    <h3 class="card-title fw-bold text-dark mb-2">Truy cập bị từ chối</h3>
                    <p class="text-muted mb-4">Bạn không có quyền truy cập vào trang quản lý cơ sở dữ liệu hệ thống.</p>
                    <a href="/web/login" class="btn btn-primary w-100" style="background-color: #71639e; border-color: #71639e;">Quay lại trang đăng nhập</a>
                </div>
            </div>
        </body>
        </html>
        """
        return request.make_response(html_content)
