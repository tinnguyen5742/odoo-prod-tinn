# ps_mfg documentation

PatSoft Manufacturing module: versioned bills of materials with variant
support, routings, resources and cost items.

## Documentation topics

### 1. Technical Specifications (`specs/`)
- [BoM (versions, variants, views)](specs/bom.md) — Định mức NVL, phiên bản, biến thể và views.
- [Workorder move (workshop consume, price, shift)](specs/workorder-move.md) — Phiếu giao ca, tiêu hao kho xưởng, chuẩn giá `standard_price`.
- [Proposal finish (FG/scrap receipt, lots, WIP)](specs/proposal-finish.md) — Phiếu nhập thành phẩm/phế phẩm, phân rã dòng và quản lý lô.
- [Component pick (lấy NVL theo kho nguồn)](specs/component-pick.md) — Hướng dẫn quy trình lấy NVL theo kho, phiếu chuyển + phiếu in, và ghi chú kỹ thuật (thay Proposal NVL).
- [Status vocabulary (bộ trạng thái chứng từ duyệt)](specs/status-vocabulary.md) — Trạng thái `draft / pending / approved / rejected / cancelled`, nhãn tiếng Việt và cách gắn `ps_approval`.

### 2. Architectural & Reference Documentation (`reference/`)
- [Odoo MRP stock move lifecycle & lot/serial architecture](reference/odoo-mrp-stock-move-lifecycle.md) — Vòng đời `stock.move`, `stock.move.line` và cơ chế quản lý lô NVL trong Odoo MRP chuẩn đối chiếu với `ps_mfg`.
- [Design: Functional core & shell refactoring for Production](reference/design-functional-core-production.md) — Bản thiết kế Functional Core & Imperative Shell cho Lệnh sản xuất.
- [Design: Pragmatic fDDD & C4 model for Production (Baseline)](reference/design-pragmatic-fddd-production.md) — Mô hình C4 và bối cảnh fDDD tổng thể (bản đối chiếu).

## System requirements

QR code on the production report (`/report/barcode`, rendered by
`reportlab`) needs the `rlPyCairo` renderPM backend:

- Python: `rlPyCairo==0.4.0` (see `requirements.txt`, also declared in
  `__manifest__.py` `external_dependencies` so Odoo warns at
  install/upgrade when missing).
- OS: `libcairo2` system library that `rlPyCairo` links against.
  - venv: `sudo apt install libcairo2` (needed before/with
    `pip install -r custom_addons/ps_mfg/requirements.txt`, otherwise
    the `rlPyCairo` build fails).
  - docker: installed in `Dockerfile` (root); just rebuild the image —
    per-addon `requirements.txt` files are pip-installed by the existing
    loop there.

Symptom when missing: broken QR image on the report + log
`RenderPMError: cannot import desired renderPM backend rlPyCairo`.
