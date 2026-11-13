# PS Enterprise Asset

PS EAM là addon Odoo 19 quản lý thiết bị và bảo trì với giao diện tiếng Việt. Addon theo dõi vòng đời thiết bị, lập kế hoạch bảo trì, xử lý sự cố và ghi nhận vật tư, công cụ cùng chi phí trên từng lệnh.

## Thiết lập và sử dụng

1. Gán quyền **Kỹ thuật viên EAM** hoặc **Quản lý EAM** theo công việc. Gán vai trò **Vận hành EAM** cho người cần gửi và theo dõi sự cố của mình. Cấp quyền Kho, Mua hàng và Kế toán theo quy trình của từng bộ phận.
2. Tạo hồ sơ thiết bị theo cấp nhà máy, dây chuyền, cụm máy và thiết bị. Khai báo đội bảo trì, người phụ trách, ngày đưa vào sử dụng và thông tin bảo hành.
3. Tạo kế hoạch theo lịch hoặc chỉ số sử dụng, rồi khai báo checklist, đồng hồ và ngưỡng cảnh báo. EAM sinh lệnh khi đến hạn hoặc khi số đo vượt ngưỡng cấu hình.
4. Xử lý lệnh theo luồng **Tạo lệnh → Duyệt → Bắt đầu → Nghiệm thu**. Người vận hành có thể tạo lệnh khắc phục nháp qua mục **Báo sự cố thiết bị**. Khi nghiệm thu, hoàn tất checklist, ghi biện pháp xử lý và xử lý các phiếu vật tư còn mở.

## Kho, sản xuất và kế toán

| Tích hợp | Cách sử dụng |
| --- | --- |
| Kho và mua hàng | Đánh dấu hàng hóa là phụ tùng MRO. Dùng **Cấp phát phụ tùng** để ghi nhận xuất hoặc trả kho, và tab **Công cụ dụng cụ** để theo dõi cấp phát và thu hồi công cụ tái sử dụng. Định mức min/max tự động có thể tạo yêu cầu mua để quản lý duyệt thành RFQ. |
| Sản xuất | Gắn thiết bị với trung tâm sản xuất để đặt lịch dừng và dời công đoạn chưa chạy bị trùng lịch. Tích hợp Master Production Schedule của Odoo Enterprise cần module riêng. |
| Kế toán | Chọn theo dõi nội bộ, hạch toán chi phí chung hoặc phân bổ vào giá thành lệnh sản xuất. Thiết bị có lịch khấu hao đã kích hoạt được ghi sổ theo kỳ. |
| MQTT | Gán topic cho đồng hồ và dùng gateway gửi số đo từ PLC hoặc SCADA vào Odoo qua API JSON-2 có xác thực. Mã sự kiện giúp xử lý bản tin gửi lại. |

Xem cấu hình quyền, vị trí tiêu hao, tài khoản kế toán và gateway trong [hướng dẫn triển khai tích hợp](docs/EAM_INTEGRATIONS.md).

## Báo cáo bảo trì

| Chỉ số | Cách tính |
| --- | --- |
| Chi phí lệnh | Giờ công × đơn giá, cộng chi phí dịch vụ và giá tham chiếu của vật tư thực xuất, trừ vật tư trả kho có liên kết. |
| TCO ghi nhận | Giá mua cộng chi phí các lệnh EAM đã nghiệm thu. |
| MTBF | Tổng giờ chạy trong nhật ký chia cho số lệnh khắc phục đã nghiệm thu. |
| MTTR | Tổng thời gian từ bắt đầu đến nghiệm thu chia cho số lệnh khắc phục đã nghiệm thu. |
| OEE | Khả dụng × hiệu suất × chất lượng. Hồ sơ thiết bị tính theo tổng giờ và sản lượng. Báo cáo pivot và biểu đồ lấy trung bình OEE từng dòng. |

## Cấu trúc addon

| Đường dẫn | Nội dung |
| --- | --- |
| `__manifest__.py` | Phiên bản, phụ thuộc và thứ tự nạp dữ liệu |
| `models/`, `views/` | Mô hình, nghiệp vụ, giao diện và menu |
| `data/`, `security/` | Dữ liệu cấu hình, tác vụ định kỳ và phân quyền |
| `report/`, `static/`, `i18n/` | Mẫu in, tài nguyên giao diện và bản dịch |
| `tests/` | Kiểm thử |

- [Phạm vi chức năng](docs/EAM_SCOPE.md)
- [Yêu cầu nghiệp vụ](docs/EAM_REQUIREMENTS.txt)
- [Kết quả kiểm tra và nâng cấp](VALIDATION.md)
