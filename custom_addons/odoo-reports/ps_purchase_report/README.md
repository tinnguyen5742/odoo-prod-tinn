# Odoo Custom Purchase Reports Module (`custom_purchase` / `ps_purchase_report`)

Module chuyên dụng cung cấp hệ thống **10 báo cáo mua hàng nâng cao** dành cho doanh nghiệp trên nền tảng Odoo. Module tích hợp cửa sổ tương tác (Wizard) linh hoạt, hỗ trợ 3 phong cách giao diện, tùy chỉnh mã màu chủ đạo, chuẩn hóa chữ ký doanh nghiệp và xuất file PDF mượt mà không bị lỗi tràn lề.

---

## 🚀 Tính năng nổi bật

1. **Giao diện Cấu hình Trung tâm (Wizard):**
   - Cho phép lọc theo khoảng thời gian (`Từ ngày` - `Đến ngày`), Nhà cung cấp và Vật tư/Hàng hóa.
   - Hỗ trợ chọn nhanh 1 trong 10 loại báo cáo nghiệp vụ mua hàng chuyên sâu.

2. **Hệ thống Tùy chỉnh Giao diện & Màu sắc (Theming):**
   - **Executive (Cổ điển & Trang trọng):** Phù hợp với các báo cáo tài chính, kiểm toán.
   - **Dynamic Corporate (Hiện đại & Tươi sáng):** Giao diện tiêu chuẩn doanh nghiệp năng động.
   - **Minimalist Clean (Tối giản tinh tế):** Giao diện thoáng đãng, dễ nhìn.
   - **Tùy chỉnh màu chủ đạo (Primary Color):** Cho phép nhập mã màu Hex (VD: `#0056b3`) để tự động đồng bộ màu tiêu đề, viền và các dòng tổng cộng trên toàn bộ 10 báo cáo.

3. **Chuẩn hóa In ấn PDF & Chữ ký doanh nghiệp:**
   - Cấu trúc CSS tối ưu hóa chống tràn lề, tương thích tuyệt đối với bộ công cụ render PDF (`wkhtmltopdf`).
   - Tự động neo khối chữ ký ở đáy trang (`page-break-inside: avoid`), loại bỏ hoàn toàn lỗi rớt dòng hoặc lệch trang trắng.
   - Hỗ trợ linh hoạt cấu hình chữ ký (1 người lập biểu hoặc 2 người ký đối xứng: Người lập & Trưởng phòng Mua hàng).

---

## 📊 Danh sách 10 Báo cáo Mua hàng

1. **Tổng hợp giá trị mua hàng theo năm** (Hiển thị ma trận 12 tháng, hỗ trợ khổ A4 ngang).
2. **Tổng hợp mua hàng theo Vật tư & Nhà cung cấp**.
3. **Bảng kê phiếu nhập mua theo PO**.
4. **Bảng kê tình hình thực hiện đơn hàng** (Theo dõi số lượng đặt, đã nhận và còn lại).
5. **Báo cáo so sánh giá mua hàng**.
6. **Báo cáo thống kê PO chưa nhận hàng**.
7. **Bảng kê chi tiết mua hàng theo nhà cung cấp**.
8. **Báo cáo kế hoạch giao hàng theo PO** (`date_planned`).
9. **Báo cáo theo dõi yêu cầu mua hàng Full quy trình**.
10. **Báo cáo theo dõi yêu cầu mua hàng tổng hợp**.

---

## 🛠️ Cấu trúc Thư mục Module

```text
custom_purchase/
│
├── __init__.py
├── __manifest__.py
├── models/                  # (Hoặc gộp chung) Logic Python xử lý AbstractModel
├── wizard/                  # Chứa model TransientModel (purchase.report.wizard) và file giao diện XML
│   ├── __init__.py
│   ├── purchase_report_wizard.py
│   └── purchase_report_wizard_views.xml
├── views/                   # Chứa file CSS dùng chung và các QWeb Template báo cáo
│   ├── purchase_report_styles.xml
│   └── purchase_report_templates.xml (hoặc các file qweb tương ứng)
└── security/
    └── ir.model.access.csv
