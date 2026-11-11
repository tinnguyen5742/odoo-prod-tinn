# Quy ước & Nguyên tắc đặt Tag Git trong dự án Odoo

Tài liệu này quy định chuẩn hóa việc đặt **Git Tag** và quy trình release áp dụng cho toàn bộ team phát triển Odoo (bao gồm repo cha `odoo-prod` và các repo con `custom_addons/*`).

---

## 1. Mục đích & Tầm quan trọng của Tag

- **Định danh phiên bản phát hành (Release Identification):** Xác định chính xác phiên bản mã nguồn đang chạy ở từng môi trường (Development, Staging, Production).
- **Trigger tự động CI/CD:** Push tag trên repo cha `odoo-prod` sẽ kích hoạt GitHub Actions build Docker image và publish lên GHCR (`ghcr.io/patsoft-dev/odoo-prod:X.Y.Z`).
- **Quản lý Git Submodule đồng bộ:** Repo cha dùng `scripts/release.sh` để phát hiện và pin đúng commit được tag từ các repo submodule.
- **Tính bất biến (Immutability):** Tag đã tạo ra là duy nhất và cố định để đảm bảo khả năng rollback / truy vết khi có sự cố.

---

## 2. Quy tắc đặt tên Tag (Naming Conventions)

Hệ thống áp dụng chuẩn **Semantic Versioning (SemVer)**: `vX.Y.Z` (`MAJOR.MINOR.PATCH`).

### 2.1. Đối với Repo Submodule (`custom_addons/*`)

Repo submodule (như `odoo-inventory`, `odoo-mfg`, `odoo-accounting`,...) có thể phục vụ nhiều nhánh khác nhau (`main`, nhánh khách hàng, nhánh nội bộ).

Quy ước: **`<branch>/vX.Y.Z`** hoặc **`vX.Y.Z`**

| Cấu trúc nhánh | Cú pháp Tag | Ví dụ |
|---|---|---|
| Nhánh nội bộ (`internal/pat`) | `<branch>/vX.Y.Z` | `internal/pat/v0.0.1`, `internal/pat/v0.1.0` |
| Nhánh khách hàng (`client/<ten>`) | `<branch>/vX.Y.Z` | `client/tanphong/v0.0.2` |
| Nhánh chính (`main`) | `vX.Y.Z` | `v0.0.3` |

> **Lưu ý đặc biệt:**
> - Script `scripts/release.sh` của repo cha **ưu tiên nhận dạng `<branch>/vX.Y.Z`**, sau đó mới đến `vX.Y.Z`.
> - **Chỉ những commit ĐÃ ĐƯỢC TAG mới được kéo vào release** của repo cha. Commit chưa tag sẽ bị bỏ qua.

### 2.2. Đối với Repo Cha (`odoo-prod`)

Repo cha quản lý cấu hình deploy, Dockerfile và pin submodule SHA.

Quy ước: **`vX.Y.Z`** (Bắt buộc có tiền tố `v`, theo sau là 3 cụm số).

| Tag Git | Image Docker trên GHCR | Ý nghĩa |
|---|---|---|
| `v0.0.12` | `ghcr.io/patsoft-dev/odoo-prod:0.0.12` | Version chính thức (bỏ chữ `v`) |
| *(Tự động)* | `ghcr.io/patsoft-dev/odoo-prod:latest` | Luôn trỏ tới tag mới nhất |
| *(Mỗi commit build)* | `ghcr.io/patsoft-dev/odoo-prod:sha-<short>` | Image theo commit SHA |

---

## 3. Khi nào cần Bump Version (`X.Y.Z`)?

| Thành phần | Tên gọi | Khi nào tăng? | Ví dụ |
|---|---|---|---|
| **Z** | **PATCH** | Sửa bug nhỏ, sửa lỗi logic, cập nhật text/dịch thuật, fix stylesheet mà không đổi data model. | `v0.0.1` → `v0.0.2` |
| **Y** | **MINOR** | Thêm module mới, tính năng mới, thêm fields/views mới (tương thích ngược hoàn toàn, không mất dữ liệu cũ). | `v0.0.2` → `v0.1.0` |
| **X** | **MAJOR** | Thay đổi lớn kiến trúc, đổi Odoo major version (16 → 17), xóa bảng/field lớn đòi hỏi migration script đặc biệt. | `v0.1.0` → `v1.0.0` |

---

## 4. Các nguyên tắc cốt lõi (Bắt buộc tuân thủ)

### Nguyên tắc 1: Luôn dùng Annotated Tag (`-a`), KHÔNG dùng Lightweight Tag
- ✅ **ĐÚNG:**
  ```bash
  git tag -a internal/pat/v0.0.2 -m "release: thêm tính năng tính giá vốn kho"
  ```
- ❌ **SAI:**
  ```bash
  git tag internal/pat/v0.0.2
  ```
- *Lý do:* Annotated tag lưu trữ đầy đủ thông tin: người tạo, thời gian (timestamp), GPG signature (nếu có) và thông điệp giải thích.

### Nguyên tắc 2: Tag là Bất biến (Immutability)
- **Tuyệt đối KHÔNG xóa hoặc sửa tag đã push lên remote**.
- Nếu phát hiện code bị lỗi ngay sau khi tag:
  1. Fix lỗi trong nhánh tương ứng.
  2. Tạo commit mới.
  3. Bump tag `PATCH` mới (ví dụ: `v0.0.2` lỗi → tag mới `v0.0.3`).
- Không bao giờ chạy `git push --delete` hay force-push đè lên tag cũ trên origin.

### Nguyên tắc 3: Tag chỉ được đánh trên commit đã qua review và merge
- Không đánh tag trên nhánh cá nhân (`feat/*`, `fix/*`).
- Chỉ đánh tag sau khi PR đã được **Squash and merge** vào nhánh chính/nhánh release (`main`, `internal/pat`, v.v.).

### Nguyên tắc 4: Thông điệp Tag (Message) phải rõ ràng
Cú pháp message:
```text
release: <Tóm tắt thay đổi chính>

- Chi tiết 1: thêm model x_...
- Chi tiết 2: sửa bug tính sai onhand
```

---

## 5. Quy trình thực hiện (Step-by-step)

### Bước 1: Đánh Tag ở Repo Submodule (Module Dev)

Sau khi merge PR vào nhánh release (ví dụ `internal/pat`):

```bash
# 1. Chuyển vào repo submodule
cd custom_addons/odoo-inventory

# 2. Cập nhật nhánh mới nhất
git checkout internal/pat
git pull origin internal/pat

# 3. Tạo annotated tag
git tag -a internal/pat/v0.0.2 -m "release: them tinh nang onhand va cost method"

# 4. Push tag lên remote
git push origin internal/pat/v0.0.2
```

### Bước 2: Release trên Repo Cha (`odoo-prod`)

Quay về thư mục gốc `odoo-prod`:

#### Cách 1: Sử dụng script tự động (Khuyến nghị)
Script sẽ tự fetch tag mới nhất từ các submodule, cập nhật pointer, commit và tạo tag cho `odoo-prod`:
```bash
# Xem trước các thay đổi (không ghi đè)
./scripts/release.sh --dry-run

# Thực hiện bump patch và push lên remote (kích hoạt build Docker image)
./scripts/release.sh --bump patch --push
```

#### Cách 2: Thực hiện thủ công
```bash
git checkout main && git pull
git submodule update --init --recursive

# Cập nhật pointer submodule vừa tag
cd custom_addons/odoo-inventory
git fetch origin && git checkout internal/pat/v0.0.2
cd ../..

# Commit pointer mới
git add custom_addons/odoo-inventory
git commit -m "chore: bump odoo-inventory to internal/pat/v0.0.2"

# Tạo tag repo cha và push
git tag -a v0.0.13 -m "release: v0.0.13 - update odoo-inventory"
git push origin main
git push origin v0.0.13
```

---

## 6. Bảng tra cứu lệnh Git Tag thường dùng

| Lệnh | Ý nghĩa |
|---|---|
| `git tag -l -n3 --sort=-creatordate` | Liệt kê các tag mới nhất kèm 3 dòng message |
| `git tag -a <tag-name> -m "<message>"` | Tạo annotated tag mới tại commit hiện tại |
| `git show <tag-name>` | Xem chi tiết commit, tác giả và ngày tạo của tag |
| `git push origin <tag-name>` | Đẩy tag đơn lẻ lên remote repo |
| `git tag --points-at HEAD` | Kiểm tra commit hiện tại có đang gắn tag nào không |
