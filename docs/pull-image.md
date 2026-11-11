# Hướng dẫn pull & chạy image odoo-prod

Image private trên GHCR: `ghcr.io/patsoft-dev/odoo-prod`

Chỗ chạy container pull tag release `X.Y.Z` (git tag `vX.Y.Z`; `docker/metadata-action` bỏ chữ `v`). Workflow vẫn gắn thêm `latest` mỗi lần đẩy tag `v*`, nhưng stack đang phục vụ không dùng `latest`.

## Yêu cầu

- Docker + Docker Compose đã cài
- Tài khoản GitHub thuộc org `patsoft-dev`, có quyền đọc repo `odoo-prod`

## Bước 1 — Tạo Personal Access Token (PAT)

GitHub → **Settings** → **Developer settings** → **Personal access tokens**
→ **Tokens (classic)** → **Generate new token (classic)**

- Note: `odoo-prod pull image`
- Expiration: chọn phù hợp (khuyến nghị 90 ngày)
- Scopes: tick **`read:packages`**
- **Generate token** → copy lại (chỉ hiện 1 lần)

## Bước 2 — Đăng nhập GHCR

```bash
echo <PASTE_TOKEN> | docker login ghcr.io -u <github-username> --password-stdin
```

Thấy `Login Succeeded` là OK. Chỉ cần chạy 1 lần.

## Bước 3 — Pull image

```bash
docker pull ghcr.io/patsoft-dev/odoo-prod:X.Y.Z
```

Thay `X.Y.Z` bằng tag image đã release (cùng số với git tag, không có chữ `v`). Danh sách tag:

https://github.com/orgs/patsoft-dev/packages/container/package/odoo-prod

## Bước 4 — Chạy

```bash
git clone git@github.com:patsoft-dev/odoo-prod.git
cd odoo-prod
cp .env.example .env
```

Sửa `.env`: `ODOO_IMAGE_TAG=X.Y.Z`, cùng tag vừa pull.

```bash
docker compose up -d
```

- HTTP: **http://localhost:8070** (container `8069`)
- Gevent / websocket: host **8072** (container `8072`)

Image đã gắn `workers = 2` và `gevent_port = 8072`, nên cả hai cổng phải tới được container. `list_db = False`. Image không chứa `dbfilter`, master password, hay mật khẩu database. `HOST`, `USER`, `PASSWORD` do compose đưa vào lúc chạy.

Compose của repo này lọc database tên `odoo` (`--db-filter=^odoo$`). Tạo database lần đầu (thay `<modules>` bằng tên các thư mục chứa `__manifest__.py`, phân tách bằng dấu phẩy):

```bash
docker compose run --rm odoo-19 odoo -d odoo -i base,<modules> --stop-after-init --without-demo
docker compose up -d
```

Master password không có trong image. Odoo dùng mặc định `admin` khi file cấu hình không ghi `admin_passwd`. Trước khi mở service ra ngoài máy, đặt mật khẩu đó trong file cấu hình lúc chạy:

```bash
cp config/odoo.conf.example config/odoo.local.conf
```

Thêm vào `config/odoo.local.conf` (file này bị gitignore vì đuôi `.conf`):

```
admin_passwd = <master-password>
dbfilter = ^odoo$
```

File mount thay cả `/etc/odoo/odoo.conf` trong image, nên dòng `addons_path` phải là dòng build đã ghi. Lấy dòng đó rồi ghi đè dòng tương ứng trong `odoo.local.conf`:

```bash
docker run --rm --entrypoint grep ghcr.io/patsoft-dev/odoo-prod:X.Y.Z '^addons_path' /etc/odoo/odoo.conf
```

Image flatten mọi module lên `/mnt/extra-addons/<tên-module>`, nên dòng đó thường trùng `config/odoo.conf.example`. Quy ước bố cục nằm ở [README](../README.md). Base image khai báo VOLUME `/mnt/extra-addons`: sau lần chạy đầu, volume ẩn danh giữ bản copy cũ. Image mới hiện addon mới khi recreate volume: `docker compose up -d --force-recreate --renew-anon-volumes` (named volume database/filestore không bị xóa).

Rồi mount đè file trong image, ví dụ trong `docker-compose.override.yaml` (cũng bị gitignore):

```yaml
services:
  odoo-19:
    volumes:
      - ./config/odoo.local.conf:/etc/odoo/odoo.conf:ro
```

Dừng: `docker compose down`

Dừng + xóa data: `docker compose down -v`

## Lên bản mới

Image mới không tự nâng schema. Trước khi phục vụ bản mới, backup database cùng filestore, đổi tag, rồi chạy một lần cập nhật module.

```bash
mkdir -p backups
docker compose exec -T db-19 pg_dump -U odoo -Fc odoo > backups/odoo.dump
docker compose cp odoo-19:/var/lib/odoo/filestore backups/filestore
```

Sửa `ODOO_IMAGE_TAG` trong `.env` thành tag mới, rồi:

```bash
docker compose pull
docker compose run --rm odoo-19 odoo -d odoo -u <modules> --stop-after-init
docker compose up -d
```

`<modules>` là tên các thư mục có `__manifest__.py`, phân tách bằng dấu phẩy. Lệnh `-u` mới nâng schema. Khởi động container không làm việc đó.

## Lỗi thường gặp

| Lỗi | Nguyên nhân / cách sửa |
|---|---|
| `not found` khi pull | Sai tag, **hoặc** chưa `docker login` |
| `unauthorized` / `403` | PAT thiếu scope `read:packages`, hoặc chưa được add vào org |
| `ODOO_IMAGE_TAG` trống | Chưa có `.env`, hoặc chưa gán tag `X.Y.Z` |
| Cổng 8070 hoặc 8072 bị trùng | Đổi cổng bên trái trong `ports` của `docker-compose.yaml` |
| Web không thấy database | Chưa tạo database `odoo`, hoặc `dbfilter` không khớp tên database |

## Ghi chú

- Image đã bao gồm code addon (build từ `Dockerfile`), chỉ cần pull là chạy.
- Cần thêm quyền: liên hệ admin org `patsoft-dev`.
