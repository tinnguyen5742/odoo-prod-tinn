# Triển khai các tích hợp PS EAM 19.0.1.4.0

## Vận hành và cấp phát

- Gán vai trò **Vận hành EAM — Báo sự cố** cho công nhân. Họ chọn thiết bị đang sử dụng thuộc công ty được cấp quyền, mô tả sự cố và xem tiến độ báo cáo của mình. Thiết bị cần có đội bảo trì. EAM tạo lệnh khắc phục nháp ngay khi lưu báo cáo.
- Đánh dấu **Máy hỏng, cần dừng sản xuất** nếu phải chặn khởi động công đoạn ở trung tâm liên kết. Tổ sản xuất dừng an toàn công đoạn đã chạy. Khi duyệt lịch bảo trì, Odoo dời các công đoạn chưa chạy bị trùng. Xem **Trạng thái máy theo EAM** và **Lịch dừng máy bảo trì** tại **Sản xuất → Lập kế hoạch**.
- Đánh dấu **Công cụ bảo trì** trên từng hồ sơ thiết bị dùng làm công cụ. Thêm công cụ vào tab **Công cụ dụng cụ** trên lệnh, ghi cấp phát và thu hồi bằng các nút tương ứng. Một công cụ chỉ có thể được cấp cho một lệnh tại một thời điểm. Hoàn tất thu hồi trước khi đóng lệnh.
- Người có quyền Kho dùng nút **Cấp phát phụ tùng** trên lệnh để mở tab phụ tùng và phiếu kho. Tạo vị trí loại **Inventory Loss** trong **Kho → Cấu hình → Vị trí tiêu hao bảo trì**. Gán công ty và tài khoản định giá phù hợp trước khi xuất vật tư có hạch toán. Trường hợp nhiều kho dùng cùng một công ty, xác nhận kho mặc định đang dùng cho EAM trước khi vận hành.

## Yêu cầu mua phụ tùng

1. Đánh dấu hàng hóa **Phụ tùng bảo trì (MRO)**, bật theo dõi tồn kho, khai báo nhà cung cấp, tuyến **Buy** và định mức **Auto**.
2. Chọn người nhận hoạt động duyệt trong tab **Thiết bị & Bảo trì** trên hồ sơ công ty. Mặc định hệ thống chọn một quản lý Mua hàng đang hoạt động trong công ty nếu có.
3. Scheduler kho tạo một PR đang chờ trên mỗi định mức. Xem tại **Mua hàng → Yêu cầu mua phụ tùng EAM**. Khi duyệt, hệ thống kiểm tra lại nhu cầu hiện tại, nhà cung cấp và tuyến Mua. Nếu nhu cầu đã được đáp ứng, PR chuyển sang **Đã đủ nhu cầu**.
4. RFQ sau duyệt dùng giá, đơn vị, thời gian cung ứng và thuế từ luồng mua chuẩn Odoo. Người mua tiếp tục xác nhận đơn mua và nhập kho theo quy trình hiện tại.

## MQTT cho PLC và SCADA

Gán một topic cụ thể cho mỗi đồng hồ. Các đồng hồ đếm dùng giá trị tích lũy và đơn vị đã cấu hình trong Odoo. Các cảm biến tình trạng dùng ngưỡng trên/dưới của đồng hồ. Thiết bị hoặc gateway nhà máy cần phát MQTT 3.1.1 với QoS 1. Ví dụ payload cho topic `nha-may/line-1/may-01/nhiet-do`:

```json
{
  "event_id": "may-01-20261110-0001",
  "measured_at": "2026-11-10T15:30:00+07:00",
  "value": 82.5
}
```

Mỗi sự kiện có mã ổn định theo đồng hồ. Phát lại cùng nội dung trả về kết quả đã ghi. Thời điểm ISO 8601 có múi giờ được quy đổi về UTC. Dùng tài khoản Odoo riêng có nhóm **Cầu nối MQTT EAM**, chỉ cấp cho các công ty được phép nhận dữ liệu. Tạo API key với quyền RPC và đặt thông tin kết nối trong tệp riêng ngoài kho mã nguồn.

| Biến môi trường | Giá trị |
| --- | --- |
| `ODOO_URL` | URL dịch vụ Odoo. Trong mạng Compose mặc định dùng `http://odoo:8069`. Dùng HTTPS nếu kết nối qua mạng bên ngoài. |
| `ODOO_DATABASE` | Database đích, ví dụ `ps_eam_test`. |
| `ODOO_API_KEY` hoặc `ODOO_API_KEY_FILE` | API key của tài khoản cầu nối hoặc đường dẫn đến tệp bí mật đã mount. |
| `MQTT_HOST`, `MQTT_PORT` | Broker và cổng. Mặc định là 8883 khi bật TLS. |
| `MQTT_CLIENT_ID` | Mã client ổn định, riêng cho gateway này. Broker cần duy trì phiên và hàng đợi QoS 1. |
| `MQTT_TOPIC_FILTER` | Bộ lọc đăng ký theo cấu hình nhà máy, ví dụ `nha-may/line-1/+/nhiet-do`. |
| `MQTT_USERNAME` và `MQTT_PASSWORD` hoặc `MQTT_PASSWORD_FILE` | Thông tin truy cập broker nếu broker yêu cầu. |
| `MQTT_TLS`, `MQTT_CA_FILE` | TLS bật mặc định. Có thể mount tệp CA riêng và cung cấp đường dẫn trong container. Dùng `MQTT_TLS=0` cho mạng thử nghiệm cô lập. |

```powershell
docker build -f docs/eam_mqtt_bridge.Dockerfile -t ps-eam-mqtt-bridge:1.4.0 docs
docker run -d --name ps-eam-mqtt --restart unless-stopped --network ps-eam_default --env-file C:/secure/eam-mqtt.env ps-eam-mqtt-bridge:1.4.0
docker logs ps-eam-mqtt
```

Kiểm tra một bản tin đúng và phát lại cùng mã. Kết quả mong đợi là một bản ghi số đo. Kiểm tra thêm một bản tin vượt ngưỡng hoặc đạt mốc bảo trì theo mức sử dụng, sau đó xác nhận lệnh tương ứng. Cầu nối xác nhận bản tin sau khi Odoo xử lý. Lỗi kết nối làm tiến trình dừng để Docker khởi động lại và broker có thể phát lại bản tin chưa xác nhận. Payload sai định dạng được ghi log và bỏ qua.

## Hạch toán và khấu hao

Cấu hình nhật ký bút toán tổng hợp, tài khoản chi phí chung và đối ứng giờ công trong tab **Thiết bị & Bảo trì** của công ty. Quản lý EAM chọn chế độ trên lệnh trước khi tạo phiếu vật tư.

| Chế độ | Xử lý khi nghiệm thu |
| --- | --- |
| **Theo dõi nội bộ** | Tính chi phí báo cáo EAM. Odoo xử lý chứng từ kho và hóa đơn theo quy trình hiện có. Đây là mặc định cho các lệnh cũ. |
| **Chi phí chung nhà máy** | Ghi sổ giờ công và chuyển chi phí thực tế đã ghi nhận từ kho, hóa đơn dịch vụ sang tài khoản chi phí chung nếu tài khoản nguồn khác. |
| **Giá thành lệnh sản xuất** | Chuyển chi phí thực tế vào tài khoản dở dang của lệnh sản xuất đã chọn. Odoo tính khoản này vào lô thành phẩm đầu tiên có sản lượng thực tế. Cần thành phẩm FIFO hoặc AVCO, định giá tự động và tài khoản dở dang trên vị trí sản xuất. |

Kế toán ghi sổ hóa đơn nguồn trước khi nghiệm thu nếu có dịch vụ thuê ngoài. Nguồn hóa đơn phải là số lệnh EAM và số tiền trên dòng chi phí phải khớp giá trị trước thuế theo tiền công ty. Vật tư cần phiếu đã xác nhận và định giá kho chính thức. Dùng tài khoản đối ứng phù hợp với quy trình lương để đối chiếu khoản giờ công.

Tại **Kế toán → Cấu hình → Khấu hao thiết bị EAM**, nhập nguyên giá, giá trị thu hồi, số đã khấu hao, kỳ đầu, số tháng còn lại và hai tài khoản. Kế toán kích hoạt lịch. Tác vụ hàng ngày ghi sổ các kỳ đến hạn theo phương pháp đường thẳng, với chênh lệch làm tròn được cân đối theo lũy kế. Chỉ chọn một nguồn ghi khấu hao cho mỗi tài sản. Nếu doanh nghiệp đang khấu hao tài sản trong hệ thống kế toán khác, giữ theo dõi tham chiếu trên EAM cho tài sản đó.

Phần sản xuất dùng lịch và định giá MRP của Odoo 19. Master Production Schedule của Odoo Enterprise cần module và môi trường riêng để kiểm thử kết nối.
