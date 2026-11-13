# PS Sale Reports

Module báo cáo dành cho **Odoo 19**, hỗ trợ tổng hợp dữ liệu bán hàng, thực hiện đơn hàng, xuất nhập tồn, công nợ và vận chuyển. Người dùng có thể xem báo cáo trực tiếp trong Odoo và xuất PDF hoặc Excel.

- **Tên module:** `ps_sale_reports`
- **Nền tảng:** Odoo 19
- **Giấy phép khai báo trong manifest:** LGPL-3

## 1. Chức năng chính

- Cung cấp 17 báo cáo phục vụ kinh doanh, kho, kế toán và giao hàng.
- Lọc dữ liệu theo các tiêu chí phù hợp với từng báo cáo: thời gian, công ty, khách hàng, sản phẩm, đơn hàng hoặc nhân viên kinh doanh.
- Xem báo cáo trong Odoo, in PDF khổ A4 ngang và xuất Excel `.xlsx`.
- Bổ sung thông tin hợp đồng, theo dõi đơn hàng, kế hoạch Sales, kế hoạch giao hàng và chi phí vận chuyển.

## 2. Danh sách báo cáo

| STT | Báo cáo | Cơ sở dữ liệu / thời gian |
| --- | --- | --- |
| 1 | Lịch sử đặt hàng | Ngày đơn bán hàng; có tùy chọn bao gồm báo giá |
| 2 | Doanh thu trong năm theo khách hàng (xuất bán) | Giao hàng và trả hàng hoàn tất trong năm |
| 3 | Tình hình thực hiện hợp đồng | Ngày đơn bán hàng; giao hàng ròng đến ngày kết thúc |
| 4 | Chi tiết bán hàng theo ngày (xuất bán) | Ngày hoàn tất giao hàng / trả hàng |
| 5 | Tổng hợp bán hàng theo ngày | Ngày hoàn tất giao hàng / trả hàng |
| 6 | Công nợ theo hóa đơn khách hàng | Ngày hóa đơn; thanh toán và số dư đến ngày kết thúc |
| 7 | Theo dõi đơn hàng | Ngày đơn bán hàng; tồn kho và sản xuất tại thời điểm chạy |
| 8 | Doanh thu – Số lượng theo Sales (SO) | Ngày đơn bán hàng; đối chiếu kế hoạch cùng kỳ |
| 9 | Tổng hợp bán hàng theo M² / ĐVT gốc | Ngày hoàn tất giao hàng / trả hàng |
| 10 | Tình hình thực hiện đơn hàng bán | Ngày đơn bán hàng; đề nghị xuất và giao thực tế |
| 11 | Theo dõi đề nghị xuất bán | Ngày đơn bán hàng; số lượng đề nghị và thực xuất |
| 12 | Nhập Xuất Tồn chi tiết theo SO | Dịch chuyển kho hoàn tất có liên kết đơn bán hàng |
| 13 | Doanh thu – Số lượng theo thành phẩm xuất bán | Ngày hoàn tất giao hàng / trả hàng |
| 14 | Thu tiền khách hàng | Hóa đơn, thu tiền và đối soát đến ngày kết thúc |
| 15 | Kế hoạch giao hàng | Ngày dự kiến giao của từng đợt |
| 16 | Bảng kê thời hạn công nợ bán ra | Điều khoản thanh toán và hạn mức hiện tại của khách hàng |
| 17 | Bảng kê chi tiết vận chuyển | Ngày dự kiến giao; thông tin và cước vận chuyển trên kế hoạch |

**SO** là đơn bán hàng; **ĐVT** là đơn vị tính. Ngày đơn hàng, ngày hoàn tất giao hàng, ngày hóa đơn và ngày dự kiến giao là những mốc riêng; cần chọn đúng khoảng thời gian theo báo cáo.

## 3. Cài đặt

### Yêu cầu

- Odoo 19 Community với cơ sở dữ liệu PostgreSQL.
- Các module phụ thuộc: `account`, `sale_management`, `sale_stock`, `sale_mrp`.
- Môi trường Python của Odoo có thư viện `xlsxwriter` để xuất Excel.

### Cài trên Odoo có sẵn

Đặt toàn bộ thư mục repo vào đường dẫn addons của Odoo với tên thư mục `ps_sale_reports`. Có thể dùng `git clone https://github.com/patsoft-extra/ps_sale_report.git ps_sale_reports` trực tiếp trong đường dẫn addons. Cài đủ các phụ thuộc, khởi động lại Odoo, cập nhật danh sách ứng dụng và cài **PS Sale Reports**.

### Cập nhật module

Sao lưu cơ sở dữ liệu và filestore, cập nhật mã nguồn rồi khởi động lại Odoo. Bật chế độ nhà phát triển, mở **Apps**, tìm **PS Sale Reports** và chọn **Upgrade**. Nếu nâng cấp qua dòng lệnh, dùng tùy chọn `-u ps_sale_reports` với cấu hình Odoo và cơ sở dữ liệu của bạn.

## 4. Sử dụng báo cáo

1. Đăng nhập Odoo và chọn công ty cần xem dữ liệu.
2. Vào **Sales → Reporting → Sales Reports**.
3. Chọn loại báo cáo.
4. Nhập các bộ lọc đang hiển thị, như khoảng ngày, khách hàng hoặc sản phẩm.
5. Chọn **Xem** để mở báo cáo, **Print** để in PDF hoặc **Xuất Excel** để tải file `.xlsx`.
6. Chọn **Thoát** để đóng bộ lọc.

Báo cáo lấy dữ liệu theo quyền truy cập của tài khoản đang đăng nhập. Các báo cáo kế toán cần quyền truy cập dữ liệu kế toán tương ứng.

Bản PDF dùng khổ A4 ngang, font Times New Roman và font serif dự phòng. Excel dùng Times New Roman cỡ 11. Để PDF hiển thị đúng font, môi trường kết xuất cần có font tương ứng.

## 5. Chuẩn bị dữ liệu

### Đơn bán hàng và sản phẩm

Nhập khách hàng, nhân viên kinh doanh, số hợp đồng và ngày giao cam kết trên đơn bán hàng. Bổ sung QCSP, PO khách hàng, thông tin lệnh sản xuất và các ngày theo dõi trên dòng đơn hàng khi cần.

Khai báo hệ số **M² / ĐVT gốc** nếu cần quy đổi diện tích. Mã nội bộ sản phẩm, Reference khách hàng và **Mã NV Sales** được dùng để hiển thị mã trên báo cáo.

### Xuất hàng và kế hoạch Sales

Nhập **Số đề nghị xuất** và **SL đề nghị xuất** trên dòng phiếu giao hàng. Số lượng xuất thực tế được lấy từ phiếu kho đã hoàn tất; xác nhận đơn bán hàng chưa đồng nghĩa với đã giao hàng.

Để đối chiếu kế hoạch Sales, tài khoản quản lý vào **Sales → Configuration → Sales Targets**, khai báo công ty, nhân viên, khoảng ngày, số lượng kế hoạch M² và doanh thu kế hoạch chưa thuế. Khoảng ngày của kế hoạch phải trùng bộ lọc báo cáo.

### Giao hàng và vận chuyển

Trên đơn bán hàng, tạo **Kế hoạch giao hàng** cho từng đợt và chọn đúng dòng đơn hàng. Nhập ngày dự kiến, số lượng, phân xưởng, tuyến, phương tiện và địa chỉ giao.

Chọn **Đợt giao dự kiến** trên dòng phiếu kho để liên kết xuất thực tế với kế hoạch. Bổ sung chủ xe hoặc đơn vị vận chuyển, số phiếu vận chuyển, kho nhận, khối lượng, số kiện, cơ sở tính cước, đơn giá và các khoản phí trên kế hoạch.

### Hóa đơn và công nợ

Các báo cáo công nợ và thu tiền sử dụng hóa đơn đã ghi sổ cùng dữ liệu đối soát thanh toán. Báo cáo công nợ theo hóa đơn phản ánh các hóa đơn trong khoảng lọc và số dư đến ngày kết thúc.

Trên khách hàng, khai báo điều khoản thanh toán tại tab **Sales & Purchase** và bổ sung hạn mức, ghi chú trong nhóm **Thông tin công nợ bán ra**. Chọn đúng công ty trước khi nhập các giá trị phụ thuộc công ty.

### Cách đọc số liệu

- Báo cáo xuất bán dựa trên giao hàng hoàn tất; các phiếu trả có cập nhật đơn bán hàng làm giảm số liệu tương ứng.
- Doanh thu xuất bán được tính sau chiết khấu, chưa thuế; các cột VAT và tổng thanh toán được thể hiện riêng khi báo cáo có hỗ trợ.
- Số lượng được tổng hợp theo ĐVT hoặc quy đổi theo hệ số đã khai báo. Các báo cáo tiền tệ sử dụng loại tiền và cách quy đổi của từng mẫu.
- Báo cáo Nhập Xuất Tồn theo SO chỉ tính dịch chuyển có liên kết đơn bán hàng; số tồn này có thể khác tồn kho tổng và có thể âm khi thiếu lượng nhập liên kết SO.
- Báo cáo thời hạn công nợ sử dụng cấu hình khách hàng hiện tại. Tồn kho và tiến độ sản xuất trong báo cáo theo dõi đơn hàng phản ánh thời điểm chạy báo cáo.
- Chi phí vận chuyển được tính từ thông tin trên kế hoạch giao hàng; đây là số liệu phục vụ báo cáo vận chuyển, không tự tạo bút toán chi phí.

## 6. Cấu trúc thư mục

```text
ps_sale_report/
├── README.md
├── .gitignore
├── __init__.py
├── __manifest__.py
├── models/       # Model, wizard và Python báo cáo
├── views/        # Giao diện, menu, quy tắc và mẫu QWeb XML
└── security/     # Khai báo quyền truy cập model
```

Tên repository là `ps_sale_report`; tên kỹ thuật của module Odoo là `ps_sale_reports`. Khi cài đặt hoặc nâng cấp module bằng dòng lệnh, sử dụng `ps_sale_reports`.
