# Build and push to GHCR

Workflow: [`.github/workflows/docker-publish.yml`](../.github/workflows/docker-publish.yml)

Job `build-push` build image `ghcr.io/patsoft-dev/odoo-prod` từ `Dockerfile`, kiểm `depends` của addon trong image vừa load, rồi mới push lên GHCR. Repo private nên package trên GHCR cũng private.

Release (tag, bump submodule) nằm ở [Hướng dẫn release](dev-workflow.md). Pull và chạy image nằm ở [Hướng dẫn pull & chạy image](pull-image.md).

## Trigger

| Sự kiện | Khi nào | Tag image |
|---|---|---|
| `push` tag `v*` | `git push origin vX.Y.Z` | `X.Y.Z`, `latest`, `sha-<short>` |
| `workflow_dispatch` | Actions → **Build and push to GHCR** → **Run workflow** | `manual-<sha>`, `sha-<short>`, cộng input `tag` nếu điền |

Tag git phải khớp `v*` (`v0.0.8` chạy, `0.0.8` không chạy). `type=semver,pattern={{version}}` bỏ chữ `v` trên git tag: `v0.0.8` thành image tag `0.0.8`.

`workflow_dispatch` chạy trên ref chọn trên form (nhánh hoặc tag). Chọn tag `v*` thì metadata cũng bật `X.Y.Z` và `latest` vì `github.ref` bắt đầu bằng `refs/tags/v`.

Input:

| Input | Bắt buộc | Mặc định | Dùng khi |
|---|---|---|---|
| `tag` | không | `""` | `workflow_dispatch`, gắn thêm một tag tùy chọn |

## Quyền

```yaml
permissions:
  contents: read
  packages: write
```

`GITHUB_TOKEN` checkout repo cha và `docker login` GHCR (`username: github.actor`). Token này chỉ có quyền trên `odoo-prod`.

## Secret

**Settings** → **Secrets and variables** → **Actions**:

| Secret | Loại | Quyền |
|---|---|---|
| `SUBMODULE_PAT` | Fine-grained PAT | `contents: read` trên mọi repo **private** trong [`.gitmodules`](../.gitmodules) |
| `GITHUB_TOKEN` | có sẵn | checkout repo cha, push GHCR |

Tạo PAT: GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**. Resource owner `patsoft-dev`. Repository access: từng repo private trong `.gitmodules`. Permissions → Repository → **Contents: Read-only**.

`.gitmodules` giữ URL SSH cho máy dev. CI rewrite `git@github.com:` thành `https://x-access-token:${SUBMODULE_PAT}@github.com/` rồi `git submodule update --init --recursive`.

Submodule hiện tại:

| Path | Remote | Clone URL |
|---|---|---|
| `custom_addons/ps_project_management` | `patsoft-dev/odoo19_ps_project_dev` | SSH |
| `custom_addons/ps_employee` | `patsoft-dev/odoo_19_ps_employee_dev` | SSH |
| `custom_addons/ps_home_layout` | `patsoft-dev/ps_home_layout` | SSH |
| `custom_addons/ps_vn_address` | `patsoft-dev/ps_vn_address` | SSH |
| `custom_addons/odoomates-apps` | `odoomates/odooapps` | HTTPS public |

Thêm submodule private: cấp `contents: read` cho PAT trên repo đó, cập nhật secret nếu token cũ không cover repo mới. Gỡ hết submodule thì bước Verify submodules dừng vì `.gitmodules` không còn `path`.

## Concurrency

```yaml
concurrency:
  group: docker-publish-${{ github.ref }}
  cancel-in-progress: false
```

Cùng một ref, job mới chờ job đang chạy. Hai tag khác nhau chạy song song.

## Image và tag

```text
REGISTRY=ghcr.io
IMAGE_NAME=patsoft-dev/odoo-prod
```

[`docker/metadata-action@v5`](https://github.com/docker/metadata-action) gắn tag:

| Nguồn | Điều kiện | Ví dụ |
|---|---|---|
| `type=semver,pattern={{version}}` | `github.ref` là `refs/tags/v*` | `ghcr.io/patsoft-dev/odoo-prod:0.0.8` |
| `type=raw,value=latest` | cùng điều kiện | `…:latest` |
| `type=sha,prefix=sha-,format=short` | mọi lần | `…:sha-c1c7387` |
| `type=raw,value=manual-{{sha}}` | `workflow_dispatch` | `…:manual-<sha>` |
| `type=raw,value=${{ inputs.tag }}` | `workflow_dispatch` và `inputs.tag` khác rỗng | tag người chạy nhập |

Chỗ phục vụ pull `X.Y.Z` (cùng số với git tag, không có chữ `v`). `latest` chỉ cập nhật khi đẩy tag `v*`.

## Các bước

Một job `build-push`, `runs-on: ubuntu-latest`.

### 1. Checkout (without submodules)

`actions/checkout@v4`, `submodules: false`, `token: GITHUB_TOKEN`, `persist-credentials: true`. Repo cha clone xong; thư mục submodule còn trống.

### 2. Checkout submodules via PAT

Secret trống thì job dừng (`SUBMODULE_PAT secret is missing or empty`). Rewrite SSH → HTTPS bằng PAT, rồi:

```bash
git submodule update --init --recursive
git submodule status --recursive
```

### 3. Verify submodules

Đọc mọi `submodule.*.path` trong `.gitmodules`. Không có path thì dừng. Với từng path, [`scripts/discover-addons.sh`](../scripts/discover-addons.sh) `modules` phải thấy ít nhất một `__manifest__.py`. Thư mục trống hoặc clone lỗi (PAT thiếu quyền) thì dừng: `Submodule <path> has no __manifest__.py`.

### 4. Reject unpinned requirements

`discover-addons.sh requirements custom_addons` liệt kê `custom_addons/*/requirements.txt` (con trực tiếp của `custom_addons`, tức root từng submodule). Không có file thì bước này pass.

Mỗi dòng không trống, không phải comment, phải chứa `==`. Thiếu pin thì dừng trước khi build. Version pin nằm ở repo addon.

### 5. Set up Docker Buildx

`docker/setup-buildx-action@v3`.

### 6. Log in to GHCR

`docker/login-action@v3`, registry `ghcr.io`, password `GITHUB_TOKEN`.

### 7. Docker metadata

Bước `id: meta`. Output `tags` và `labels` dùng cho build và push.

### 8. Build

`docker/build-push-action@v6`:

| Key | Giá trị | Lý do |
|---|---|---|
| `context` | `.` | root repo |
| `file` | `./Dockerfile` | |
| `platforms` | `linux/amd64` | `load` chỉ một platform |
| `load` | `true` | image vào Docker local để bước 9 `docker run` |
| `push` | `false` | chưa đẩy; kiểm `depends` trước |
| `provenance` / `sbom` | `false` | `load` không đi cùng attestation |
| `cache-from` / `cache-to` | `type=gha` | cache GitHub Actions |

Dockerfile copy `custom_addons/`, chạy `discover-addons.sh install-requirements`, `flatten` (mọi module lên `/mnt/extra-addons/<tên>`), rồi `apply-config` ghi `addons_path` vào `/etc/odoo/odoo.conf`. Bố cục module nằm ở [README](../README.md).

### 9. Check addon depends

Lấy tag đầu tiên khác rỗng từ `steps.meta.outputs.tags`. Không có tag thì dừng.

```bash
docker run --rm --entrypoint python3 \
  "${tag}" \
  /usr/local/bin/check-addon-depends.py
```

[`scripts/check-addon-depends.py`](../scripts/check-addon-depends.py) đọc `addons_path` trong `/etc/odoo/odoo.conf` (cùng path container sẽ dùng). Không Postgres. Script:

1. Liệt kê module là con trực tiếp của từng mục `addons_path`.
2. Trùng tên trên `addons_path` thì fail.
3. Với mọi module dưới `/mnt/extra-addons`, từng phần tử `depends` trong `__manifest__.py` phải có trên `addons_path`. Thiếu thì fail.

Job dừng trước khi push.

### 10. Push to GHCR

Mỗi dòng trong `steps.meta.outputs.tags`:

```bash
docker push "${tag}"
```

## Chạy tay

1. Tab **Actions** → **Build and push to GHCR** → **Run workflow**.
2. Chọn nhánh hoặc tag.
3. Để trống **Extra tag** thì image có `manual-<sha>` và `sha-<short>`. Điền thêm thì có thêm tag đó.

Dùng khi thử bump submodule trên `main` mà chưa cắt release.

## Thêm hoặc gỡ submodule

Thêm: ghi vào `.gitmodules`, cấp `contents: read` cho `SUBMODULE_PAT` nếu repo private, commit gitlink.

Gỡ một path:

```bash
git rm -f custom_addons/<name>
rm -rf .git/modules/custom_addons/<name>
git commit -m "Remove submodule custom_addons/<name>"
```

Workflow đọc `.gitmodules` lúc chạy. Gỡ một path, các path còn lại vẫn được clone và verify. Gỡ hết path thì bước Verify submodules fail (` .gitmodules has no submodule path`).

## Lỗi thường gặp

| Log / hiện tượng | Việc cần làm |
|---|---|
| `SUBMODULE_PAT secret is missing or empty` | Thêm secret, hoặc PAT hết hạn |
| `Submodule <path> has no __manifest__.py` | PAT thiếu `contents: read` trên repo đó, hoặc submodule chưa có module |
| `.gitmodules has no submodule path` | Không còn `path` trong `.gitmodules` |
| `Unpinned requirement in …` | Pin `==` trong `custom_addons/<submodule>/requirements.txt` ở repo addon, rồi bump pointer |
| `Missing depends (module -> required)` | Thêm module thiếu vào image (submodule hoặc core), hoặc bỏ `depends` sai |
| `Duplicate module names on addons_path` | Hai thư mục module trùng tên sau flatten |
| `Docker metadata produced no image tag` | metadata-action không ra tag; kiểm ref và input |
| Push tag nhưng Actions không chạy | Tag phải khớp `v*` |
| Job mới đứng chờ | Cùng `github.ref` đang có job; `cancel-in-progress: false` |

## File liên quan

| File | Vai trò |
|---|---|
| [`.github/workflows/docker-publish.yml`](../.github/workflows/docker-publish.yml) | workflow |
| [`.gitmodules`](../.gitmodules) | danh sách submodule CI clone |
| [`Dockerfile`](../Dockerfile) | image `odoo:19.0` + flatten addon |
| [`scripts/discover-addons.sh`](../scripts/discover-addons.sh) | tìm module, `requirements.txt`, flatten, ghi `addons_path` |
| [`scripts/check-addon-depends.py`](../scripts/check-addon-depends.py) | kiểm `depends` trong image |
| [`config/odoo.conf.example`](../config/odoo.conf.example) | `addons_path` gốc, copy vào `/etc/odoo/odoo.conf` |
