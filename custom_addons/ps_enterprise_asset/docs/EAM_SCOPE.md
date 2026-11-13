# Phạm vi phân hệ EAM

Nguồn: EAM_REQUIREMENTS.txt do người dùng cung cấp ngày 2026-10-29.
Yêu cầu bổ sung cùng ngày: giữ giao diện thương hiệu, mẫu in riêng cho hồ sơ/kế hoạch/bảo hành/cảm biến và nhắc bảo hành trước 30 ngày.

| Nhóm nghiệp vụ | Chức năng trong addon |
| --- | --- |
| Danh mục thiết bị | Phân cấp tài sản, thông số, tài liệu đính kèm, lịch sử sửa chữa, trạng thái, TCO, giá trị còn lại và khấu hao đường thẳng |
| Bảo hành | Bảo hành NCC/khách hàng, cảnh báo còn hạn và nhắc trước 30 ngày, hồ sơ bồi thường, mã RMA, phiếu đổi trả liên kết |
| Kế hoạch bảo trì | Lịch ngày/tuần/tháng/quý/năm, đồng hồ giờ/km/chu kỳ, SOP, checklist, sinh lệnh đến hạn |
| Giám sát thiết bị | Đồng hồ/cảm biến, lịch sử số đo, cảnh báo vượt ngưỡng, tự sinh lệnh khắc phục, gateway MQTT xác thực |
| Lệnh bảo trì | Vai trò báo sự cố của vận hành, phân công, lịch, vật tư, cấp và thu hồi công cụ, giờ công, nguyên nhân và chữ ký nghiệm thu |
| Vật tư & phụ tùng | Danh mục phụ tùng, định mức min/max, PR tự động, duyệt thành RFQ, phiếu cấp phát/hoàn trả và lượng thực dùng |
| Báo cáo & phân tích | OEE, MTBF, MTTR, TCO; chi phí thực tế so ngân sách và khắc phục so định kỳ |

## Tích hợp trong phạm vi tài liệu

- **Sản xuất** dùng lịch tài nguyên MRP, tự lập lại lịch công đoạn chưa chạy khi duyệt bảo trì và khóa khởi động công đoạn khi có sự cố khẩn cấp. MPS Enterprise vẫn cần môi trường và module tích hợp riêng.
- **Kho và Mua hàng** dùng phiếu kho chuẩn, xác nhận lượng thực xuất và trả kho. Định mức MRO tự động tuyến Mua tạo PR để quản lý mua hàng duyệt sang RFQ.
- **Kế toán** có chế độ chi phí chung hoặc giá thành theo từng lệnh và lịch khấu hao đường thẳng theo tháng. Kế toán cấu hình nhật ký, tài khoản và ghi sổ hóa đơn nguồn.
- **IoT/SCADA** có gateway MQTT. PLC/SCADA tại nhà máy phát số đo theo hợp đồng dữ liệu, qua broker và topic đã được cấp quyền.

Xem điều kiện cấu hình và cách kiểm thử tại [hướng dẫn tích hợp](EAM_INTEGRATIONS.md).

## Phần giữ theo yêu cầu bổ sung

Giữ các asset giao diện thương hiệu hiện có, bảy mẫu in PDF và cron nhắc bảo hành trước 30 ngày. Không xóa dữ liệu thiết bị, lệnh, bảo hành, số đo, kho, kế toán hoặc tài liệu đính kèm khi tổ chức lại menu. Các phân hệ chuẩn liên quan vẫn phục vụ tích hợp EAM.
