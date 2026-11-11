# PS eLearning Reports (`ps_elearning_report`)

Module Odoo cung cấp các mẫu báo cáo cho ứng dụng **eLearning** (`website_slides`), bao gồm báo cáo chi tiết từng khóa học và báo cáo tổng hợp nhiều khóa học. Cả 2 báo cáo đều hỗ trợ hộp thoại Popup cho phép lựa chọn **Preview (Xem trước HTML)** hoặc **Xuất PDF**.

---

## 1. Tính năng chính

### 1.1. Báo cáo khóa học eLearning (`report_course_summary`)
* **Vị trí xuất hiện:** Menu **Thao tác (Action / Bánh răng)** trên giao diện **Form** của từng khóa học (`slide.channel`).
* **Hộp thoại Popup:**
  * Hiển thị: **Tên khóa học** hiện tại.
  * Tùy chọn **Preview:** Xem trước báo cáo dạng HTML trực tiếp trên trình duyệt.
  * Tùy chọn **Xuất PDF:** Tải file PDF báo cáo về máy tính.

---

### 1.2. Báo cáo tổng hợp eLearning (`report_courses_overview`)
* **Vị trí xuất hiện:** Menu **Thao tác (Action) / In** trên giao diện **Danh sách (List)** hoặc **Kanban** của Tất cả khóa học (All Courses) khi chọn các khóa học.
* **Hộp thoại Popup:**
  * Hiển thị: **Số lượng khóa học áp dụng** và danh sách thẻ khóa học được chọn. Nếu không chọn khóa nào, hệ thống mặc định lấy tất cả các khóa đang hoạt động.
  * Tùy chọn **Preview:** Xem trước báo cáo tổng hợp dạng HTML trực tiếp trên trình duyệt.
  * Tùy chọn **Xuất PDF:** Xuất và tải file PDF báo cáo khổ A4 ngang.

---

## 2. Cấu trúc thư mục module

```text
ps_elearning_report/
├── __init__.py
├── __manifest__.py
├── README.md
├── security/
│   └── ir.model.access.csv             # Quyền truy cập wizard popup
├── wizard/
│   ├── __init__.py
│   └── slide_channel_report_wizard.py  # Model popup cho cả 2 loại báo cáo (Preview & Xuất PDF)
├── views/
│   ├── ir_actions_report_views.xml     # Kế thừa form ir.actions.report
│   └── slide_channel_report_wizard_views.xml # View form popup & liên kết action menu
└── report/
    ├── paperformat.xml                 # Khổ giấy A4 ngang
    ├── report_course_summary.xml       # Template QWeb & Report Action từng khóa
    └── report_courses_overview.xml     # Template QWeb & Report Action tổng hợp
```

---

## 3. Cài đặt & Nâng cấp

Nâng cấp module sau khi cập nhật:
```bash
odoo -d <database_name> -u ps_elearning_report
```
Tải lại trang Odoo (F5) để cập nhật giao diện.
