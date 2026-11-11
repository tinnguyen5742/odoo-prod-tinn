# odoo-prod

Repository trung tâm quản lý phiên bản và phát hành mã nguồn Odoo Production:
- Quản lý và cố định (pin) commit của các custom addon thông qua **Git Submodule** (tại thư mục `custom_addons/`). Toàn bộ mã nguồn phát triển addon nằm ở repo submodule tương ứng.
- Đóng gói và phát hành (publish) Docker image chính thức lên GitHub Packages: `ghcr.io/patsoft-dev/odoo-prod`.

> 💡 **Dành cho Developer:** Xem ngay **[Hướng dẫn Code Style, Setup Môi Trường & Linter (Odoo 19)](docs/code-style-guide.md)** để cấu hình PyCharm, Ruff, Pylint-Odoo và tuân thủ quy chuẩn viết code trước khi phát triển addon.

---

## Cơ chế nạp Module & Quy trình Build Docker

### Quy tắc nhận diện Module
- **Tên module** chính là tên thư mục chứa file `__manifest__.py`.
- Odoo chỉ nạp (load) một module khi thư mục của module đó là **thư mục con trực tiếp** của một trong các đường dẫn được khai báo trong `addons_path`.

### Quá trình Flatten (Làm phẳng cấu trúc) khi Build Image
Khi thực hiện build Docker image, toàn bộ thư mục `custom_addons/` sẽ được sao chép vào container tại `/mnt/extra-addons`. Script [`scripts/discover-addons.sh`](scripts/discover-addons.sh) sẽ tự động xử lý:
1. **Làm phẳng (Flatten):** Di chuyển mọi thư mục module (chứa `__manifest__.py`) lên thành thư mục con trực tiếp của `/mnt/extra-addons/<tên-module>` (ví dụ: `custom_addons/odoomates-apps/om_account_accountant` → `/mnt/extra-addons/om_account_accountant`). Cấu trúc cây submodule trên Git vẫn được giữ nguyên không đổi.
2. **Cập nhật `addons_path`:** Ghi tự động đường dẫn nạp module vào file `/etc/odoo/odoo.conf` theo thứ tự ưu tiên:
   - `/mnt/extra-addons` (chứa các module custom đã flatten).
   - Thư mục cha trực tiếp của các module khác (nếu có module nằm ngoài `/mnt/extra-addons`).
   - Các đường dẫn gốc mặc định của Odoo core.

### Quy tắc bắt buộc (Validation Rules)
- **Vị trí file manifest:** Mỗi `__manifest__.py` bắt buộc phải nằm bên trong một thư mục module con. Build sẽ **bị dừng ngay lập tức** nếu file `__manifest__.py` nằm trực tiếp ngay tại gốc `custom_addons/`.
- **Trùng tên module:** Không được phép có hai thư mục module trùng tên nhau (kể cả từ hai submodule khác nhau). Bước flatten sẽ phát hiện và dừng build nếu xảy ra trùng lặp.
- **Thư viện phụ thuộc (`requirements.txt`):** Script cài đặt và hệ thống CI chỉ quét các file `requirements.txt` đặt ở thư mục gốc trực tiếp của từng submodule (`custom_addons/<tên-submodule>/requirements.txt`).

---

## Các cấu trúc Submodule được hỗ trợ & Cách xử lý

### 1. Một submodule chứa một module duy nhất (Khuyến nghị / Phổ biến)

```text
custom_addons/ps_employee/
├── __manifest__.py
└── requirements.txt
```

- **Mô tả:** Bản thân submodule là một module Odoo (`ps_employee`).
- **Xử lý:**
  - Giữ nguyên cấu trúc tại `/mnt/extra-addons/ps_employee`.
  - Đường dẫn `addons_path` chỉ cần trỏ tới `/mnt/extra-addons`.
  - Tự động chạy `pip install` cho file `custom_addons/ps_employee/requirements.txt`.
  - Đây là cấu trúc tiêu chuẩn đang được áp dụng cho phần lớn các submodule hiện tại.

### 2. Một submodule chứa nhiều module con trực tiếp (Suite / Monorepo)

```text
custom_addons/suite/
├── requirements.txt
├── ps_a/
│   └── __manifest__.py
└── ps_b/
    └── __manifest__.py
```

- **Mô tả:** Submodule đóng vai trò là một bộ sản phẩm (suite), chứa nhiều module độc lập (`ps_a`, `ps_b`) và dùng chung một file `requirements.txt` ở cấp gốc của submodule.
- **Xử lý:**
  - Cập nhật con trỏ submodule `suite` (bump commit SHA) sẽ đồng bộ cả `ps_a` và `ps_b` cùng lúc.
  - Cài đặt `custom_addons/suite/requirements.txt` trước khi thực hiện flatten.
  - Image flatten thành `/mnt/extra-addons/ps_a` và `/mnt/extra-addons/ps_b`. `addons_path` giữ `/mnt/extra-addons`.

### 3. Module nằm sâu trong thư mục con

```text
custom_addons/suite/
├── requirements.txt
└── addons/
    └── ps_a/
        └── __manifest__.py
```

- **Mô tả:** Module `ps_a` nằm trong thư mục trung gian (như `addons/`) bên trong submodule.
- **Xử lý:**
  - Quá trình build sẽ tự động tìm kiếm và làm phẳng thành `/mnt/extra-addons/ps_a`.
  - File `requirements.txt` vẫn được cài đặt nếu được đặt ở gốc submodule (`custom_addons/suite/requirements.txt`).

### 4. Manifest ở cả gốc submodule và thư mục con

```text
custom_addons/suite/
├── __manifest__.py
└── ps_extra/
    └── __manifest__.py
```

- **Mô tả:** Gốc submodule là module `suite`, đồng thời bên trong có thêm module con `ps_extra`.
- **Xử lý:** Image flatten đưa cả hai lên thành `/mnt/extra-addons/suite` và `/mnt/extra-addons/ps_extra`.

### 5. Submodule không có `__manifest__.py` (Lỗi)

- **Hiện tượng:** Submodule trong `custom_addons/` không chứa bất kỳ file `__manifest__.py` nào.
- **Hệ quả:** Pipeline CI sẽ dừng ở bước **Verify submodules**, không cho phép build image.

### 6. Trùng tên thư mục module giữa các repo (Lỗi)

```text
custom_addons/repo_a/ps_foo/__manifest__.py
custom_addons/repo_b/ps_foo/__manifest__.py
```

- **Hiện tượng:** Có hai module cùng mang tên thư mục là `ps_foo`.
- **Hệ quả:** Bước flatten sẽ báo lỗi xung đột tên, tiến trình build dừng lại và image không được đẩy lên GHCR.

### 7. File `requirements.txt` thiếu toán tử cố định phiên bản `==` (Lỗi)

- **Quy định:** CI đọc từng file `custom_addons/*/requirements.txt`. Tất cả các dòng khai báo package (ngoại trừ dòng trống và dòng ghi chú `#`) bắt buộc phải có toán tử cố định phiên bản `==` (ví dụ: `requests==2.31.0`).
- **Hệ quả:** Nếu có dòng thiếu `==`, workflow CI sẽ dừng ngay lập tức trước bước build image để đảm bảo môi trường production luôn đồng nhất và có thể tái lặp chính xác.

---

## Lưu ý về cấu hình runtime (`odoo.conf`)

Khi triển khai container, nếu bạn mount file cấu hình `/etc/odoo/odoo.conf` từ máy chủ (host) vào container, file này sẽ ghi đè lên cấu hình mặc định (bao gồm cả dòng `addons_path` đã được image tính toán tự động).

> ⚠️ **Quan trọng:** Hãy đảm bảo giữ nguyên toàn bộ giá trị của dòng `addons_path` trong image khi bạn cần bổ sung thêm các tham số như `admin_passwd` hay `dbfilter`. Chi tiết xem tại [Hướng dẫn pull & chạy image](docs/pull-image.md).

---

## Tài liệu

- **Phát triển & Quy chuẩn code:**
  - [Hướng dẫn Code Style, Setup Môi Trường & Linter (Odoo 19)](docs/code-style-guide.md)
  - [Làm việc trên repo module](docs/module-git.md)
  - [Hướng dẫn submodule, tag & GitHub Actions](docs/dev-workflow.md)
  - [Quy ước & Nguyên tắc đặt Tag Git](docs/tag-guidelines.md)
- **Vận hành & CI/CD:**
  - [Hướng dẫn pull & chạy image](docs/pull-image.md)
  - [Workflow Build and push to GHCR](docs/docker-publish.md)
