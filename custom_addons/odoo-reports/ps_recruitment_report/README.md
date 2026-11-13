# PS Recruitment Reports — Odoo 19

Bộ nguồn hai báo cáo PDF Tuyển dụng được thiết lập trên web Odoo, kèm các PDF hiện tại do người dùng yêu cầu đưa lên GitHub. Đây là bộ bàn giao XML và hướng dẫn, **không phải module Odoo**; không có `__manifest__.py`.

| Báo cáo | Template | Luồng sử dụng đã chốt |
| --- | --- | --- |
| Danh sách các vị trí tuyển dụng | `custom_recruitment.report_job_positions_list` | Chọn vị trí trong List/Kanban rồi In |
| Danh sách các ứng viên theo từng vị trí | `custom_recruitment.report_applicants_by_job` | Mở một vị trí rồi In trong màn hình chi tiết |

Cả hai nhận model `hr.job`. Chưa thêm lọc ngày. Người dùng đã chốt A4 ngang, giữ Document Layout doanh nghiệp, bảng chữ thường, padding 3px × 6px, không cắt nội dung dài.

## Cấu trúc

```text
templates/                    4 Architecture QWeb, gồm style/body dùng chung
views/                        Form kế thừa để hiện binding_view_types
config/report_actions.json    Cấu hình đích cho hai Report Action
config/paperformats.json      Hồ sơ khổ giấy tham chiếu trong bộ bàn giao
config/source_templates.json  Nguồn và SHA-256 của từng XML
config/source_snapshot.json   Cấu hình thực tế đã đọc và thay đổi trên giao diện
config/pdf_samples.json       Tên tệp gốc, số trang, kích thước và SHA-256 PDF
pdf/                          Hai PDF dữ liệu hiện tại, giữ nguyên nội dung
docs/SETUP_ODOO_WEB.md         Hướng dẫn cài và cập nhật trên web
docs/VERIFICATION.md           Phạm vi kiểm tra và các điểm còn cần đối chiếu
tools/validate_bundle.py      Kiểm tra ngoại tuyến XML/biểu thức/phụ thuộc
bundle.json                   Bảng kê nguồn/cấu hình và trạng thái kiểm tra
```

## Hai báo cáo

**Danh sách vị trí:** mỗi vị trí một dòng; loại việc làm nằm dưới tên vị trí trong cùng ô. Có phòng ban, địa điểm, người tuyển dụng/phỏng vấn, nhu cầu tuyển, số hồ sơ và trạng thái. Không kèm mô tả công việc dài hoặc ghi chú quy ước dưới tiêu đề.

**Danh sách ứng viên:** mỗi vị trí một bảng, tên vị trí và phòng ban đặt ở đầu bảng. Mỗi hồ sơ một dòng; nhiều người phỏng vấn nằm chung ô. Hiển thị họ tên, liên hệ, ngày nộp, giai đoạn/trạng thái, bằng cấp, kỹ năng/mức độ và người phụ trách. Không đưa lương, nguồn tuyển, tài liệu đính kèm hoặc thông tin nhân viên vào mẫu mới. Giữ cả hồ sơ từ chối/lưu trữ theo quyền đọc. Tổng phân biệt hồ sơ, Contact khác nhau và hồ sơ chưa gắn Contact.

## PDF hiện tại

- [Danh sách các vị trí tuyển dụng](pdf/recruitment_job_positions.pdf): bản người dùng chỉ định **“Danh sách các vị trí tuyển dụng (1).pdf”**, đã kiểm tra tất cả trang là A4 ngang, 2 trang.
- [Danh sách các ứng viên theo từng vị trí](pdf/recruitment_applicants_by_job.pdf): bản hiện có **“Danh sách các ứng viên theo từng vị trí (1).pdf”**, A4 ngang, 7 trang.

Giữ nguyên các PDF hiện có theo yêu cầu; không tạo PDF mô phỏng hoặc chỉnh lại nội dung mẫu. Chỉ hai danh sách mới được đưa vào repo, không có các báo cáo cũ đã gỡ hoặc báo cáo hồ sơ đã tạo nhân viên.

## Thiết lập

Làm theo [hướng dẫn web](docs/SETUP_ODOO_WEB.md). Tạo helper trước báo cáo phụ thuộc, điền đúng Key và t-name. Chỉ nội dung trong `templates/` mới là Architecture QWeb; các JSON trong `config/` là tài liệu tham chiếu, không phải tệp import.

Ngày 11/11/2026 đã phát hiện action danh sách vị trí chưa gắn Paper Format; đã gán khổ riêng **“Tuyển dụng - Danh sách - A4 ngang”**. Thông số thực đọc trên khổ đó là top 40, bottom 20, trái/phải 7 mm, header spacing 35, DPI 90, Landscape; xem [snapshot thực tế](config/source_snapshot.json). Các số 52/32/0/0/52 trong hồ sơ bàn giao là tham chiếu eLearning lịch sử, không phải thông số đã được lưu trên khổ này. Không áp dụng cứng một bộ số cho mọi công ty/layout.

## Nguồn và giới hạn kiểm tra

Khác bộ eLearning đã có CSV export, XML trong repo này lấy từ **các tệp bàn giao cục bộ đã soạn trong phiên làm việc**, chưa xuất lại trực tiếp từ Architecture đang cài trên Odoo. Không có CSV export hoặc bản sao database. Cấu hình đích trong `bundle.json`/`report_actions.json` và snapshot UI thực tế được phân biệt rõ.

Đã kiểm tra tĩnh XML, biểu thức, Key, chuỗi t-call và tổng độ rộng cột. Các PDF là đầu ra Odoo hiện có, không chứng minh toàn bộ View/action trên môi trường nguồn đã khớp từng dòng với bộ XML bàn giao. Chưa thử cài trên database Odoo mới; xem [trạng thái kiểm tra](docs/VERIFICATION.md).

## Phụ thuộc

Odoo 19, `web`, Tuyển dụng (`hr_recruitment`), Kỹ năng tuyển dụng (`hr_recruitment_skills`), tích hợp Website Tuyển dụng cho `website_published`, và bộ tạo PDF Odoo. Dữ liệu chỉ đọc theo quyền hiện hữu; không có `sudo()` hoặc token tài liệu trong mẫu.

Kiểm tra lại source offline với Python 3:

```text
python tools/validate_bundle.py bundle.json --json
```

Kết quả tĩnh không thay thế kiểm tra schema/quyền và xuất PDF thực tế. Repo không chứa tài khoản, mật khẩu, cookie phiên hoặc dữ liệu cấu hình đăng nhập.
