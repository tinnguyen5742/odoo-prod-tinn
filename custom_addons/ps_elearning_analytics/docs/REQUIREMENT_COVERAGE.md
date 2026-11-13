# Phạm vi báo cáo eLearning

Addon `ps_elearning_report` chỉ bổ sung báo cáo cho Odoo eLearning; nghiệp vụ khóa học và chứng nhận lõi thuộc các ứng dụng Odoo gốc.

| Hạng mục báo cáo | Hiện thực |
| --- | --- |
| Báo cáo tóm tắt một khóa | QWeb template `report_course_summary.xml`; report action hiển thị ở Print trên form khóa học. |
| Báo cáo tổng quan nhiều khóa | QWeb template `report_courses_overview.xml`; report action hiển thị ở Print trên danh sách/kanban. |
| Báo cáo tiến độ một khóa | QWeb template `report_course_progress.xml`; hiển thị trạng thái, phần trăm, ngày ghi danh, lần cập nhật gần nhất và bài học tiếp theo. |
| Báo cáo tiến độ nhiều khóa cho HCNS | QWeb template `report_training_progress.xml`; liệt kê ghi danh cho các khóa được chọn, kể cả người học chưa liên kết hồ sơ nhân viên. Có thể hiển thị phòng ban/vị trí nếu có hồ sơ nhân viên. |
| Phân tích tiến độ | SQL view `elearning.training.report`; hỗ trợ list/pivot/graph và bộ lọc trạng thái, quá hạn, phòng ban, nhân viên, khóa học. |
| Cấp chứng nhận | Thuộc Odoo Survey; addon không phát hành report action hoặc xử lý cấp chứng nhận. |
| Phân quyền báo cáo | Nhân viên nội bộ chỉ đọc dòng của mình; eLearning Officer đọc dữ liệu khóa mình phụ trách; nhóm eLearning HR Manager xem toàn bộ tiến độ. |
| Trường báo cáo phụ trợ | Enrollment có `employee_id` tính từ liên kết user/partner và `deadline_date` để báo cáo hiển thị giá trị đã tồn tại. Addon không tự ghi deadline. |

## Dữ liệu và giới hạn

- PDF được render khi người dùng chọn Print, từ dữ liệu hiện có trong Odoo. `pdf/` giữ ba bản PDF mẫu xuất từ Odoo test để review; addon không nạp chúng thành dữ liệu Odoo.
- Instance test chỉ có ba report action cho khóa học; action PDF tiến độ HCNS của addon chưa xuất hiện trên instance đó.
- Báo cáo HCNS chỉ hiển thị hạn khi bản ghi ghi danh đã có `deadline_date`; addon không tự tạo hạn.
- Không bao gồm tuyển dụng, ghi danh tự động/hàng loạt, chính sách khóa học, nhắc hạn, tạo Discuss chat hoặc cập nhật hồ sơ chứng nhận nhân viên.
