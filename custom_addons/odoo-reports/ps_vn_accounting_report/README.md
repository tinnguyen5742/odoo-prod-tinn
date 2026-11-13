# PS VN Accounting Report

Module Odoo 19 tùy chỉnh các báo cáo kế toán Việt Nam của PatSoft.

## Chức năng

- 11 mẫu QWeb cho Preview HTML và bản in PDF.
- Header riêng trong từng file báo cáo, có logo, tên, địa chỉ, mã số thuế,
  điện thoại và email của công ty. Email nằm trên dòng riêng.
- Logo và thông tin công ty được căn cân đối; có thể sửa từng mẫu độc lập.
- Khổ giấy riêng cho từng báo cáo và renderer Python cho báo cáo TT99.

## Phụ thuộc

Cần Odoo 19 và module `ps_vn_accounting` cùng các phụ thuộc của module đó
(`accounting_pdf_reports`, `om_account_daily_reports`, `om_account_accountant`,
`l10n_vn`, `stock_account`). Repository này chỉ chứa `ps_vn_accounting_report`.

Các external ID báo cáo trong `ps_vn_accounting` phải có sẵn khi cài đặt.

## Các mẫu báo cáo

| Báo cáo | File trong `reports/` |
| --- | --- |
| General Ledger | `ps_general_ledger_report.xml` |
| Trial Balance | `ps_trial_balance_report.xml` |
| Tax Report | `ps_tax_report.xml` |
| Journals Audit | `ps_journal_audit_report.xml` |
| Aged Partner Balance | `ps_aged_partner_report.xml` |
| Day Book | `ps_daybook_report.xml` |
| Cash Book | `ps_cashbook_report.xml` |
| Bank Book | `ps_bankbook_report.xml` |
| Báo cáo tài chính (kết quả kinh doanh, cân đối kế toán) | `ps_report_financial.xml` |
| Partner Ledger | `ps_partner_ledger_report.xml` |
| Báo cáo tình hình tài chính TT99 | `financial_report_template.xml` |

Sửa trực tiếp header trong file XML tương ứng. TT99 lấy thông tin công ty
được chọn trên wizard; các mẫu khác lấy công ty trong ngữ cảnh báo cáo.
Cập nhật logo và thông tin liên hệ trong Settings → Companies.

## Cài đặt

Đặt thư mục module `ps_vn_accounting_report` trong một thư mục thuộc
`addons_path`. Sau đó cập nhật danh sách ứng dụng và cài **Vietnam Accounting Reports**.
Module mở rộng các menu báo cáo hiện có, không tạo ứng dụng riêng.

Ví dụ với Docker Compose của dự án, chạy từ thư mục có file Compose
(thay `Test` bằng tên database phù hợp):

```powershell
docker compose stop odoo
docker compose run --rm --no-deps odoo odoo -d Test -i ps_vn_accounting_report --stop-after-init
docker compose up -d odoo
```

Sau khi sửa mẫu, dùng `-u ps_vn_accounting_report` thay cho `-i` để cập nhật.
Tạo bản in mới để nhận mẫu mới nhất.

## Kiểm tra

Các mẫu đã được kiểm tra cú pháp XML, cập nhật module trên Odoo 19 và xuất
HTML/PDF với dữ liệu của dự án. Báo cáo Cash Book cần tài khoản tiền mặt
hoặc nhật ký Cash được cấu hình cho công ty đang chọn.

## Giấy phép

LGPL-3, theo khai báo trong `__manifest__.py`.