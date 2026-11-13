# Odoo Field Service Management (FSM) Module

## 📋 Giới thiệu tổng quan
Phân hệ **Field Service Management (FSM)** là giải pháp quản lý dịch vụ hiện trường toàn diện được thiết kế riêng cho nền tảng **Odoo 19**. Module này giúp doanh nghiệp tự động hóa và tối ưu hóa toàn bộ quy trình vận hành bên ngoài văn phòng như: lắp đặt, bảo trì, sửa chữa, bảo hành thiết bị tại địa điểm của khách hàng, đồng thời kết nối xuyên suốt giữa đội ngũ điều hành, kỹ thuật viên di động, kho vận và kế toán.

---

## 🚀 Các tính năng chính (Core Features)

1. **Quản lý Yêu cầu Dịch vụ & Phiếu công tác (Work Order Management)**
   * Tự động sinh mã phiếu công tác theo định dạng chuyên nghiệp (`FSO/00001`, `FSO/00002`...) thông qua `ir.sequence`.
   * Quản lý thông tin khách hàng, địa điểm thực hiện, người phụ trách và mức độ ưu tiên (thấp, bình thường, cao, khẩn cấp).

2. **Lập kế hoạch & Điều phối Thông minh (Scheduling & Dispatch)**
   * Giao diện Kanban trực quan đóng vai trò bảng điều phối trung tâm.
   * **Sắp xếp tự động:** Các phiếu công tác có hạn chót SLA gần nhất hoặc độ ưu tiên khẩn cấp được tự động đẩy lên trên cùng.
   * **Cảnh báo màu sắc:** Trực quan hóa các phiếu vi phạm SLA hoặc khẩn cấp bằng hệ thống màu sắc cảnh báo ngay trên thẻ Kanban.

3. **Quản lý Thiết bị của Khách hàng (Customer Asset Tracking)**
   * Theo dõi danh mục thiết bị/máy móc lắp đặt tại nhà khách hàng định danh theo số Serial / Barcode.
   * Quản lý ngày lắp đặt và hạn bảo hành để kiểm tra chính sách dịch vụ.

4. **Kho Dịch vụ & Vật tư Lưu động (Van Stock & Parts)**
   * Quản lý chi tiết danh mục linh kiện, vật tư thay thế sử dụng ngay trên phiếu công tác.
   * Tự động trừ kho và đồng bộ chi phí vật tư khi hoàn tất công việc.

5. **Quản lý Hợp đồng Dịch vụ, Bảo hành & Cam kết SLA (Service Contracts & SLAs)**
   * Thiết lập hạn chót cam kết phản hồi (`sla_deadline`) và tự động phát hiện trạng thái vi phạm SLA (`is_sla_failed`).
   * Theo dõi thời hạn bảo hành thiết bị.

6. **Chi phí Phát sinh & Tự động hóa Hóa đơn (Expenses & Invoicing Integration)**
   * Quản lý các chi phí phát sinh tại hiện trường (xăng xe, cầu đường...).
   * **Tự động hóa tài chính:** Khi kỹ thuật viên bấm nút *Hoàn thành & Nghiệm thu*, hệ thống tự động trích xuất toàn bộ vật tư sử dụng (`line_ids`) và chi phí phát sinh (`expense_ids`) để sinh ra một **Hóa đơn nháp (`account.move`)** cho khách hàng, giúp loại bỏ thao tác nhập liệu thủ công.

7. **Nghiệm thu & Chữ ký điện tử (Sign-on-Glass)**
   * Thu thập chữ ký xác nhận trực tiếp của khách hàng ngay trên giao diện di động hoặc máy tính bảng khi bàn giao công việc.

8. **Tối ưu Tuyến đường & Điều hướng Địa chỉ (Area-Based Route Optimization & Navigation)**
   * Tích hợp thuật toán gom nhóm theo khu vực (`area_id`) để tối ưu hóa lịch trình di chuyển cho kỹ thuật viên theo thực tế địa phương.
   * Nút bấm mở trực tiếp Google Maps chỉ đường dựa trên địa chỉ văn bản của khách hàng mà không cần tọa độ GPS phức tạp.

---

## 📊 Tiến độ hiện tại của phân hệ (Current Implementation Status)

| Hạng mục tính năng | Trạng thái | Ghi chú chi tiết |
| :--- | :---: | :--- |
| **Cấu trúc Model cốt lõi (`field.service.order`)** | ✅ Đã hoàn thành | Đã định nghĩa các trường dữ liệu, quan hệ với khách hàng, thiết bị, kỹ thuật viên, SLA và quy trình trạng thái (Draft -> Assigned -> In Progress -> Done -> Cancel). |
| **Giao diện Người dùng (Views: Form, List, Kanban)** | ✅ Đã hoàn thành | Hoàn thiện giao diện Form chi tiết, List view danh sách và Kanban điều phối trực quan có gắn màu sắc cảnh báo SLA/Ưu tiên. |
| **Tích hợp Google Maps theo Địa chỉ văn bản** | ✅ Đã hoàn thành | Xây dựng nút bấm trực quan trên Form giúp mở nhanh Google Maps chỉ đường dựa vào trường địa chỉ chi tiết. |
| **Tối ưu tuyến đường theo khu vực (`area_id`)** | 🔄 Đã triển khai code | Đã bổ sung hàm Python gom nhóm khu vực, Server Action và nút bấm thao tác hàng loạt trên giao diện danh sách. Đang trong giai đoạn tinh chỉnh vận hành ổn định trên môi trường Docker. |
| **Tự động hóa sinh Hóa đơn & Kho** | ✅ Đã hoàn thành | Tự động đồng bộ vật tư, chi phí phát sinh thành hóa đơn nháp khi nghiệm thu công việc. |

---

## 🛠️ Yêu cầu hệ thống & Phụ thuộc (Dependencies)
Module này được phát triển và tối ưu cho **Odoo 19** trong môi trường Docker (`odoo-1`, `db-1`) và yêu cầu các module chuẩn sau để hoạt động đầy đủ:
- `base` (Hệ thống cốt lõi)
- `mail` (Hệ thống thảo luận, chatter và activity)
- `product` (Quản lý sản phẩm và linh kiện)
- `account` (Phân hệ Kế toán để tự động hóa sinh hóa đơn)
