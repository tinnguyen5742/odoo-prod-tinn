# Hướng Dẫn Code Style, Setup Môi Trường & Linter (Odoo 19)

Tài liệu này hướng dẫn cách thiết lập môi trường linter/formatter cho dự án Odoo 19 và quy trình tự động quét, sửa (auto-fix) các file mã nguồn hiện có theo chuẩn **Odoo Core & OCA Guidelines**.

---

## 1. Thiết lập môi trường (Chọn 1 trong 2 cách)

---

### Cách 1: Thiết lập tự động 100% với `mise` (Khuyến nghị)

Nếu máy bạn đã cài đặt [`mise`](https://mise.jdx.dev/), toàn bộ quy trình đã được tự động hoá trong [`mise.toml`](../mise.toml). Bạn chỉ cần đứng tại thư mục gốc dự án và chạy đúng **1 lệnh**:

```bash
# Đứng tại thư mục gốc dự án (odoo-prod)
mise install
```

`mise` sẽ tự động thực hiện:
1. **Cài đặt công cụ CLI (`[tools]`)**: Cài `python 3.12`, `uv`, và `ruff` (binary độc lập, có thể gõ lệnh `ruff` ngay trong terminal).
2. **Khởi tạo `.venv`**: Tự động tạo virtualenv Python tại `.venv`.
3. **Cài đặt Odoo Core & deps (`[deps.odoo]`)**: Tự động chạy `uv pip install -r odoo/requirements.txt` và liên kết editable `uv pip install --no-deps -e ./odoo`.
4. **Cài đặt Linter & Dev tools (`[deps.dev]`)**: Tự động cài `ruff`, `pylint-odoo`, `pylint` vào `.venv` từ nhóm `dev` trong `pyproject.toml`.
5. **Tự động đồng bộ khi `cd` (`[hooks] enter = "mise deps"`)**: Mỗi khi file `odoo/requirements.txt` hoặc `pyproject.toml` thay đổi, `mise` tự cập nhật các gói thiếu.

---

### Cách 2: Thiết lập thủ công không qua `mise` (Dùng thuần `uv` / `.venv`)

Nếu bạn không sử dụng `mise` hoặc muốn tự thiết lập bằng tay từng bước với `uv`:

```bash
# Đứng tại thư mục gốc dự án (odoo-prod)

# 1. Tạo môi trường ảo .venv với Python 3.12 (nếu chưa có):
uv venv .venv --python 3.12

# 2. Cài đặt các thư viện phụ thuộc của Odoo:
uv pip install -r odoo/requirements.txt

# 3. Liên kết Odoo Core vào .venv ở chế độ editable (tránh lỗi import 'odoo'):
uv pip install --no-deps -e ./odoo

# 4. Cài đặt các công cụ Linter & Dev tools (ruff, pylint-odoo) từ pyproject.toml:
uv pip install --group dev
```

*(Lưu ý: Không dùng `uv sync` vì `uv sync` sẽ gỡ bỏ các thư viện Odoo cài từ `requirements.txt`).*

---

### 1.3. Cấu hình PyCharm IDE (Áp dụng cho cả 2 cách)

Sau khi môi trường đã được chuẩn bị xong:
1. **Sources Root**:
   - Trong cây thư mục dự án bên trái, chuột phải vào thư mục `odoo` -> **Mark Directory as** -> **Sources Root**.
2. **Kích hoạt Ruff có sẵn trong PyCharm (Tích hợp Native)**:
   - PyCharm (từ bản 2024.2 trở đi) đã **tích hợp sẵn Ruff trực tiếp trong lõi IDE**, **không cần cài thêm bất kỳ plugin bên ngoài nào**.
   - Mở `Settings` (`Ctrl + Alt + S`) -> `Tools` -> **Ruff**.
   - Tick chọn **Enable**.
   - PyCharm sẽ tự động nhận diện file `pyproject.toml` và binary `ruff` trong `.venv` (`.venv/bin/ruff`).
3. **Bật Tự động Format & Lint khi Lưu file**:
   - Mở `Settings` -> `Tools` -> **Actions on Save**:
     - Tick chọn: **Run ruff format**
     - Tick chọn: **Run ruff linter --fix** (hoặc tích chọn chạy on save ngay trong mục `Tools` -> `Ruff`).
4. **Cấu hình dự án ([pyproject.toml](../pyproject.toml))**:
   Dự án đã có sẵn file cấu hình chuẩn:
   - `[tool.ruff]`: Quy định `line-length = 88`, exclude `odoo` core.
   - `[tool.ruff.lint]`: Bỏ qua `ignore = ["E501"]` (để không bắt lỗi độ dài dòng trên comment/docstring).
   - `[tool.ruff.lint.isort]`: Sắp xếp import theo chuẩn Odoo (`odoo` trước `odoo.addons`).
   - `[tool.pylint.messages_control]`: Tắt các cảnh báo thừa của Pylint.

---

## 2. Hướng dẫn quét và Auto-Fix trên các file sẵn có

### 2.1. Tự động format & sửa lỗi cú pháp (Ruff)

#### Quét và kiểm tra lỗi (Dry-run):
```bash
# Cách 1 (Dùng trực tiếp lệnh ruff của mise):
ruff check custom_addons/odoo-mfg/ps_mfg/models/mfg_component_request.py

# Cách 2 (Không dùng mise - qua uvx hoặc binary trong .venv):
uvx ruff check custom_addons/odoo-mfg/ps_mfg/models/mfg_component_request.py
# hoặc:
.venv/bin/ruff check custom_addons/odoo-mfg/ps_mfg/models/mfg_component_request.py

# Kiểm tra toàn bộ 1 module:
ruff check custom_addons/odoo-mfg/ps_mfg/
```

#### Tự động Format & Sắp xếp Import (Auto-fix):
Chạy 2 lệnh sau để tự động căn dòng, ngắt dòng dài và chuẩn hóa khối import:
```bash
# 1. Format căn chỉnh lề, khoảng trắng, xuống dòng:
ruff format <đường_dẫn_file_hoặc_thư_mục>
# (Nếu không dùng mise: uvx ruff format <đường_dẫn>)

# 2. Tự động sửa lỗi import và các lỗi auto-fixable:
ruff check --fix <đường_dẫn_file_hoặc_thư_mục>
# (Nếu không dùng mise: uvx ruff check --fix <đường_dẫn>)
```

*Ví dụ áp dụng cho toàn bộ addon `ps_mfg`:*
```bash
ruff format custom_addons/odoo-mfg/ps_mfg
ruff check --fix custom_addons/odoo-mfg/ps_mfg
```

---

### 2.2. Quét chuẩn Odoo chuyên sâu (`pylint-odoo`)

Để kiểm tra các lỗi nghiệp vụ đặc thù của Odoo (thứ tự method, quy chuẩn dịch thuật, thừa thuộc tính):

```bash
# Quét 1 file:
.venv/bin/python -m pylint --load-plugins=pylint_odoo <đường_dẫn_file>

# Quét 1 module:
.venv/bin/python -m pylint --load-plugins=pylint_odoo custom_addons/odoo-mfg/ps_mfg
```

---

## 3. Checklist các điểm cần fix tay trên các file cũ

Sau khi chạy `ruff format` và `ruff check --fix`, có 3 nhóm cảnh báo bạn cần lưu ý kiểm tra và chỉnh tay nhanh:

| Lỗi / Cảnh báo | Cách viết cũ (Chưa chuẩn) | Cách viết mới (Chuẩn Odoo 19 / OCA) |
| :--- | :--- | :--- |
| **Biến mơ hồ `l`** (`E741`) | `lambda l: l.state == 'done'`<br>`for l in lines:` | Đổi thành `line`:<br>`lambda line: line.state == 'done'`<br>`for line in lines:` |
| **Dịch thuật i18n** (`prefer-env-translation`) | `from odoo import _`<br>`raise UserError(_("Message"))` | Không import `_`<br>`raise UserError(self.env._("Message"))`<br>*(hoặc `record.env._("...")`)* |
| **Thừa `string=`** (`attribute-string-redundant`) | `request_date = fields.Datetime(string="Request Date")`<br>`product_id = fields.Many2one(..., string="Product")` | Bỏ `string=` vì Odoo tự tạo nhãn:<br>`request_date = fields.Datetime(...)`<br>`product_id = fields.Many2one(...)` |
| **Gọi hàm nội bộ** (`protected-access`) | `mo.bom_id._compute_scaled_components(...)` | Thêm ghi chú bỏ qua ở cuối dòng:<br>`mo.bom_id._compute_scaled_components(...)  # pylint: disable=protected-access` |

---

## 4. Thứ tự phương thức chuẩn trong một Model Odoo

Khi viết mới hoặc refactor các file model cũ, hãy sắp xếp các khối code theo đúng thứ tự sau:

1. **Model Attributes**: `_name`, `_description`, `_inherit`, `_order`, `_rec_name`, `_check_company_auto = True`.
2. **Default Methods**: `def _default_xxx(self): ...`
3. **Fields Declaration**: Fields cơ bản -> Relational fields (`Many2one`, `One2many`, `Many2many`) -> Computed fields.
4. **Compute & Inverse Methods**: `@api.depends(...) def _compute_xxx(self): ...`
5. **Onchange Methods**: `@api.onchange(...) def _onchange_xxx(self): ...`
6. **Constrains Methods**: `@api.constrains(...) def _check_xxx(self): ...`
7. **CRUD Methods**: `create()`, `write()`, `unlink()`.
8. **Action Methods**: `action_approve()`, `action_confirm()`, `action_view_xxx()`.
9. **Private Business Helpers**: `def _do_calculation(self): ...`
