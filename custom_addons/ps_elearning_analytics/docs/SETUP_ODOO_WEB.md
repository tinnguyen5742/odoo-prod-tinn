# Cài đặt và sử dụng trên Odoo 19

## Cài addon

Đưa `custom_addons/ps_elearning_report` vào `addons_path`, khởi động lại Odoo và cập nhật danh sách Apps. Cài trước hai ứng dụng:

- `website_slides`
- `hr`

Cài **PATSOFT eLearning Reports**. Addon tạo các QWeb report actions, paper format, SQL view báo cáo tiến độ và giao diện list/pivot/graph. Post-install hook đăng ký ba template QWeb báo cáo cũ; template tiến độ HCNS được nạp trực tiếp như dữ liệu addon.

Addon chỉ phục vụ báo cáo. Không còn luồng ghi danh tự động/hàng loạt, cấu hình khóa bắt buộc, nhắc hạn, tạo Discuss chat hoặc đồng bộ chứng nhận vào hồ sơ nhân viên. Việc cấp chứng nhận thuộc Odoo Survey; addon không tạo chứng nhận.

## Cấp quyền

- Gán **eLearning HR Manager** cho người cần xem tiến độ toàn công ty và in báo cáo tiến độ nhiều khóa.
- eLearning Officer xem dữ liệu tiến độ của khóa họ phụ trách.
- Nhân viên nội bộ chỉ đọc dòng tiến độ của chính mình.
- Kiểm tra người dùng thuộc nhiều nhóm và thử đọc/in trên staging trước khi cài production.

## Xuất báo cáo

| Báo cáo | Vị trí |
| --- | --- |
| Báo cáo khóa học eLearning | Mở một khóa học > Print |
| Báo cáo tiến độ học viên | Mở một khóa học > Print; nhóm eLearning Officer |
| Báo cáo tổng hợp eLearning | Chọn khóa học trong danh sách/kanban > Print |
| Báo cáo tiến độ đào tạo HCNS | Chọn khóa học > Print; nhóm eLearning HR Manager |
| Báo cáo tiến độ dạng list/pivot/graph | eLearning > Báo cáo > Employee Progress |

Báo cáo HCNS chỉ tổng hợp các khóa đang hoạt động/đã công khai được chọn lúc in. Báo cáo dùng dữ liệu ghi danh hiện có; hạn chỉ được hiển thị nếu enrollment đã có `deadline_date`. Addon không tự tạo hoặc nhắc hạn.

## Khôi phục thủ công QWeb

Chỉ dùng nếu không thể cài addon và cần khôi phục ba báo cáo cũ trên database riêng. Bật Developer Mode, mở Settings > Technical > User Interface > Views. Architecture QWeb nguồn nằm trong `templates/`; không dán XML cấu hình `data/` vào trường Architecture. Sau khi tạo view, đăng ký template external ID đúng tên trong `t-name` và tạo report action liên kết model `slide.channel`. Ưu tiên cài addon để tạo đủ report actions và paper format.
