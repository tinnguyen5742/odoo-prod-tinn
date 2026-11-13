# Kết quả kiểm tra PS EAM

- Môi trường: image odoo:19, phiên bản 19.0-20260908; PostgreSQL 18.
- Database riêng: ps_eam_test. Dữ liệu nghiệp vụ của test được rollback bởi TransactionCase.
- Kết quả cuối: 17 ca kiểm thử, 0 failed, 0 errors; process exit code 0.
- Cài mới và cập nhật addon thành công; Python/XML hợp lệ.
- Đã kiểm tra: cây tài sản, ngày bảo hành, PM theo ngày/chỉ số, hủy và sinh lại, chống trùng, cảm biến, phân quyền, checklist, nghiệm thu, khóa nội dung đã đóng, công ty, OEE, RFQ, trừ tồn kho thực tế và chi phí, menu/views theo vai trò, render QWeb HTML.
- Chưa kiểm tra trực quan PDF bằng máy in hoặc luồng thao tác trong trình duyệt đã đăng nhập.

Lệnh tái lập từ thư mục odoo-eam:

```powershell
docker compose run --rm --no-deps odoo odoo -d ps_eam_final_qa_1_4_0 -u ps_eam --without-demo --test-enable --test-tags=/ps_eam --stop-after-init --http-port=8071
```

Lần đầu với database mới dùng -i ps_eam thay cho -u ps_eam. Không dùng database vận hành để chạy test.

## PDF validation - 2026-10-22

- Version 19.0.1.0.3: rendered actual QWeb PDFs with wkhtmltopdf for EAM/2026/00158 (draft alert, empty checklist) and EAM/2026/00055 (in progress, checklist, labour and service costs).
- Both PDFs: one A4 page, logo present, tables aligned, no clipped content; inspected page PNGs rendered with PDFium.
- Dedicated A4 paper format: 12 mm margins, 0 header spacing, 90 DPI. Inline styles and embedded company logo.
- Docker report asset endpoint: report.url = http://127.0.0.1:8069. The browser continues to use localhost:8880.
- Verified actual PDF output; no physical printer test. Current records were not signed or marked completed.


### Report typography - version 19.0.1.0.4

- Bundled Roboto Regular/Bold fonts with Apache-2.0 license and notice.
- Verified font URLs return HTTP 200 in wkhtmltopdf requests. PDF font resources contain Roboto and no DejaVu fallback.
- Re-exported and visually inspected orders 00158 and 00055; both remain one A4 page, Vietnamese accents visible, table and signatures fit.


### Borderless branding and signature - version 19.0.1.0.6

- Replaced branding/signature HTML tables with div-based table-cell layout; no table borders can apply to these blocks. Data grids retain their light borders.
- Restarted web process to invalidate stale QWeb worker cache after shell edits.
- Authenticated HTTP GET /report/pdf/ps_eam.work_order_document/163 returned actual PDF; visually checked with PDFium: one A4 page, no frame around logo or signature.


### Fixed PDF footer - version 19.0.1.0.9

- Moved the closing note from body flow into a real Odoo footer, with page/total-page counters and 20 mm reserved bottom margin.
- Checked footer repetition on a two-page render, then tightened section/cell spacing without reducing text size.
- Re-exported actual orders 00156 (accepted, signature, long cause/resolution, costs) and 00158 (draft). Both final PDFs contain one A4 page with footer at bottom, no orphan footer page, no clipped signatures.
- Verified through authenticated HTTP report endpoint; rendered final PDFs with PDFium for visual QA.

### Six additional PDF reports - version 19.0.1.1.0

- Added equipment dossier, periodic maintenance plan, warranty claim, meter readings, selected-order cost summary and selected-operation/OEE summary.
- Print bindings on list/form views, restricted to EAM users; existing record rules remain in effect. No sudo in templates. Cost and OEE summaries group selected records by company, keeping currencies separate.
- Cost summary excludes non-EAM requests, includes open/closed selected EAM orders and labels its scope. OEE summary explicitly uses the arithmetic average of selected logs.
- Reused A4 paper format, RinBee company logo, embedded Roboto and native repeated page footer; repeating table headings and no row splitting.
- HTML rendered against 47 equipment, 33 plans, 12 claims, 34 meters, 50 orders and 129 operation logs.
- Authenticated HTTP exports verified: equipment/plan/claim/meter one page each, 50-order cost report three pages, ten-log operation report two pages. All pages rendered with PDFium and visually checked.
- Final OEE values use two decimal places. Verified Print bindings through authenticated Odoo RPC.
- Regression suite: 19 post-install tests, zero failures/errors, including selected-cost totals and new-template empty relations/OEE rendering.

Usage: refresh Odoo, open the relevant list, select records, then Print and choose the report. For cost analysis pivot, switch to list before selecting records. Equipment/plan/claim/meter reports print one dossier per selected record; cost/OEE reports summarize the selection.


## Nghiệp vụ và tích hợp — 19.0.1.2.0 (2026-10-29)

- Cài mới trên database riêng thành công; chạy hồi quy sau cập nhật trên `ps_eam_qa_1_2_0`: 27 post-install tests, 0 failed, 0 errors.
- Kiểm tra mới: chu kỳ quý, MTTR thời gian lịch tách khỏi giờ công, OEE tổng hợp, giá trị còn lại tham chiếu, liên kết hồ sơ bảo hành và quyền tạo trạng thái, lịch dừng trung tâm sản xuất tạo/cập nhật/gỡ khi hủy, chặn bắt đầu công đoạn, kiểm tra lịch và khóa thiết bị sau duyệt, tạo hóa đơn dịch vụ nháp không trùng.
- Hồi quy bao gồm phân quyền, đa công ty, tồn kho thực xuất, RFQ và các QWeb HTML hiện có.
- Thử nâng cấp bản sao dữ liệu hiện có tại `ps_eam_upgrade_1_2_0` thành công, giữ đủ 47 thiết bị và 76 maintenance requests; MRP chuẩn được cài theo phụ thuộc mới.
- Backup database/filestore và log QA nằm tại `backups/`, không commit lên GitHub.
- Chưa kiểm thử với PLC/SCADA thật, sơ đồ MPS Enterprise, ghi sổ kế toán thực tế hoặc máy in vật lý; không cấu hình thêm thiết bị, bút toán hay lịch sản xuất vận hành để thử.
- Đã nâng cấp database đang dùng `ps_eam_test` tại localhost:8880 lên 19.0.1.2.0, khởi động lại thành công; HTTP /web/login trả 200, giữ 47 thiết bị và 76 maintenance requests. Không chạy test trên database này.


## Đối chiếu phạm vi tài liệu — 19.0.1.3.0 (2026-10-29)

- Tổ chức menu thành bảy nhóm nghiệp vụ trong `docs/EAM_SCOPE.md`; bổ sung lối vào danh sách KPI thiết bị MTBF/MTTR/TCO, sử dụng các phép tính hiện có.
- Giới hạn danh mục hàng hóa, định mức min/max và lựa chọn phụ tùng trên lệnh về hàng hóa có cờ Phụ tùng bảo trì MRO. Migration phân loại sản phẩm đã dùng trong dòng phụ tùng hoặc phiếu kho liên kết EAM, không đổi tồn kho/định mức.
- Giữ nguyên các tệp giao diện thương hiệu, bảy mẫu in, cron bảo hành trước 30 ngày và tích hợp sản xuất/kho/mua hàng/kế toán.
- Cài mới trên QA riêng thành công. Sau chỉnh thứ tự mở màn hình KPI: toàn bộ 30 post-install tests đạt, 0 failed, 0 errors trên `ps_eam_qa_1_3_0`. Kiểm thử gồm danh mục MRO không lẫn hàng hóa khác, định mức MRO, migration nhận diện phụ tùng cũ, form sản phẩm, bảy nhóm menu, bảy mẫu in, cron bảo hành cùng các hồi quy hiện có.
- Thử nâng cấp bản sao dữ liệu tại `ps_eam_upgrade_1_3_0` thành công: giữ 47 thiết bị, 76 maintenance requests, bảy report actions và cron bảo hành active.
- Đã sao lưu database/filestore trước khi nâng cấp database đang dùng `ps_eam_test`; bản sao nằm tại `backups/before_scope_1_3_0/`, không đưa vào Git.
- Đã nâng cấp hệ thống tại localhost:8880 lên 19.0.1.3.0. Đối chiếu trước/sau: số lượng thiết bị, lệnh, hồ sơ bảo hành, số đo, dòng phụ tùng và checksum tồn kho/đính kèm đều khớp. Không chạy test trên database đang dùng.
- Xác minh bảy menu cấp một và bảy mẫu in còn tồn tại, cron bảo hành active; trang đăng nhập với database ps_eam_test hiển thị bình thường. Chưa kiểm tra tương tác nghiệp vụ trong phiên trình duyệt có đăng nhập; các view/phân quyền được kiểm tra bằng bộ test Odoo.
- Không thay template in hoặc render lại PDF trong lần chỉnh menu này. Giới hạn IoT, PR riêng, khấu hao tự động và MPS được ghi rõ trong tài liệu phạm vi.

## Nghiệm thu QA — 19.0.1.4.0 (2026-11-10)

- Cài mới trên Odoo 19.0-20260908 và PostgreSQL 18 tại `ps_eam_final_qa_1_4_0`. Toàn bộ 40 ca post-install đạt, 0 failed, 0 errors.
- Hồi quy gồm quyền báo sự cố và chặn công đoạn, cấp/thu hồi công cụ, tạo PR từ scheduler và duyệt RFQ, dời lịch công đoạn, hạch toán giờ công, tái phân loại vật tư và hóa đơn dịch vụ đã ghi sổ, nhập thành phẩm có giá thành EAM và ghi từng kỳ khấu hao.
- Thử MQTT bằng Mosquitto, gateway Docker và API JSON-2 có xác thực trên `ps_eam_qa_1_4_0`. Phát hai lần cùng bản tin vượt ngưỡng, ghi đúng một số đo và một lệnh cảnh báo. Thử thêm quyền và mã sự kiện xung đột trong bộ test.
- Nâng cấp bản sao PostgreSQL `ps_eam_upgrade_1_4_0` lên 19.0.1.4.0. Đối chiếu với database nguồn giữ 49 thiết bị, 85 yêu cầu bảo trì, 12 hồ sơ bảo hành và 125 số đo. Database đang dùng vẫn ở 19.0.1.3.0.
- Tích hợp được kiểm tra trên lịch tài nguyên MRP chuẩn. Các cấu hình còn cần nghiệm thu tại nhà máy gồm broker và topic thật, tài khoản và vị trí kho theo công ty, ánh xạ thiết bị với trung tâm sản xuất. MPS Enterprise cần môi trường riêng.
