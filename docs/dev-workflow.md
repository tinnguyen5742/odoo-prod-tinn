# Hướng dẫn release

Repo `odoo-prod` pin commit addon bằng git submodule và publish image `ghcr.io/patsoft-dev/odoo-prod`. Code addon nằm ở repo submodule. Tài liệu này chỉ gồm các bước release của repo này.

- Repo cha: `odoo-prod` (Dockerfile, docker-compose, CI)
- Submodule: mọi path trong `.gitmodules`. Một submodule có thể chứa một hoặc nhiều module. Bố cục nằm ở [README](../README.md).

Repo này không sửa nội dung submodule. Không đổi file trong `custom_addons/`. Sửa addon làm ở repo addon, merge xong rồi mới bump commit SHA ở đây. Repo này chỉ pin commit và build image.

## 1. Cập nhật pointer submodule

Repo cha không lưu code addon, chỉ lưu commit SHA (`git ls-tree HEAD custom_addons/`). Sau khi repo submodule đã merge, bump pointer của **submodule vừa đổi**:

```bash
git checkout main && git pull
git submodule update --init --recursive

cd custom_addons/<submodule-vừa-đổi>
git fetch origin && git checkout main && git pull

cd ../..
git add custom_addons/<submodule-vừa-đổi>
git commit -m "chore: bump <submodule-vừa-đổi>"
git push
```

`git add` chỉ ghi SHA mới, không đưa code addon vào repo cha. Có nhiều submodule đổi thì lặp lại từng path.

Lấy repo lần đầu, khi máy chưa có bản clone:

```bash
git clone --recurse-submodules git@github.com:patsoft-dev/odoo-prod.git
```

Nếu merge repo cha conflict vì hai nhánh trỏ một submodule tới hai commit khác nhau: vào thư mục submodule, `git checkout` đúng commit, rồi `git add` path đó và commit.

## 2. Tag

Tag tạo trên repo cha, pattern `v*` (ví dụ `v0.0.2`). Push tag là trigger để GitHub Actions build, chạy thử addon, rồi push image lên GHCR.

Dùng annotated tag. Không sửa hoặc xóa tag đã push — sai thì tạo tag mới.

```bash
git tag -a vX.Y.Z -m "release: mô tả ngắn"
git push origin vX.Y.Z
```

| Tăng | Khi nào | Ví dụ |
|---|---|---|
| `vX.Y.Z` — Z (patch) | fix bug | `v0.0.1` → `v0.0.2` |
| `vX.Y.Z` — Y (minor) | thêm tính năng | `v0.0.2` → `v0.1.0` |
| `vX.Y.Z` — X (major) | thay đổi lớn, không tương thích ngược | `v0.1.0` → `v1.0.0` |

| Tag git | Image trên GHCR |
|---|---|
| `vX.Y.Z` | `ghcr.io/patsoft-dev/odoo-prod:X.Y.Z` (`{{version}}` bỏ chữ `v`) |
| cùng lần đẩy tag đó | `ghcr.io/patsoft-dev/odoo-prod:latest` |
| mọi lần build | `ghcr.io/patsoft-dev/odoo-prod:sha-<short>` |

Chỗ chạy container pull `X.Y.Z`. Xem [Hướng dẫn pull & chạy image](pull-image.md).

Commit hằng ngày và sửa docs không cần tag. Build thử không cần tag: **Actions** → **Build and push to GHCR** → **Run workflow** (tag `manual-<sha>`, có thể nhập thêm tag).

## 3. GitHub Actions

Workflow: `.github/workflows/docker-publish.yml`. Chi tiết trigger, secret, tag image, từng bước và lỗi: [docs/docker-publish.md](docker-publish.md).

1. Checkout repo cha bằng `GITHUB_TOKEN`.
2. Checkout submodule bằng secret `SUBMODULE_PAT` (rewrite URL SSH → HTTPS, rồi `git submodule update --init --recursive`).
3. Đọc mọi `path` trong `.gitmodules`. `scripts/discover-addons.sh modules` không thấy `__manifest__.py` thì dừng build.
4. `scripts/discover-addons.sh requirements` liệt kê `custom_addons/*/requirements.txt`. Dòng không trống, không phải comment, thiếu `==` thì dừng build. Version pin nằm ở repo addon.
5. Build `linux/amd64`, `load: true`, `push: false`. Image gọi `discover-addons.sh install-requirements`, `flatten` (đưa mọi module lên `/mnt/extra-addons/<tên>`), rồi `apply-config` để ghi `addons_path`.
6. Chạy `check-addon-depends.py` trong image vừa build (không Postgres). Script đọc `addons_path` trong `/etc/odoo/odoo.conf`, liệt kê module là con trực tiếp của từng mục, rồi kiểm `depends` của mọi module dưới `/mnt/extra-addons`. Thiếu module, hoặc trùng tên trên `addons_path`, thì dừng workflow.
7. Push GHCR sau bước đó. Tag image: `X.Y.Z`, `latest`, `sha-<short>`.

**Settings** → **Secrets and variables** → **Actions**:

| Secret | Giá trị | Ghi chú |
|---|---|---|
| `SUBMODULE_PAT` | Fine-grained PAT | `contents: read` trên mọi repo private trong `.gitmodules` |

`GITHUB_TOKEN` có sẵn. Workflow có quyền `contents: read`, `packages: write`.

- Log `SUBMODULE_PAT secret is missing` → secret chưa cấu hình, hoặc PAT hết hạn / thiếu quyền trên một repo submodule.
- Push tag nhưng Actions không chạy → tag phải khớp `v*` (`v0.0.2` chạy, `0.0.2` không chạy).

## 4. Checklist release

1. Merge code ở repo submodule.
2. Trên repo này: bump pointer của từng submodule vừa đổi, push `main`.
3. `git tag -a vX.Y.Z -m "..."` rồi `git push origin vX.Y.Z`.
4. Chờ workflow **Build and push to GHCR** xanh trên tab Actions.
5. Phục vụ bản mới theo [Hướng dẫn pull & chạy image](pull-image.md): backup database và filestore, pull đúng `X.Y.Z`, chạy một lần `odoo -u <modules> --stop-after-init`.
