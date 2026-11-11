# Odoo 19 Community — Average Cost (AVCO)

Tham chiếu nhanh costing method **Average Cost (AVCO)** của core Community 19,
so với sổ tồn `ps.stock.onhand`, và chuỗi cập nhật `standard_price` khi nhập.

Module: `stock_account` (`odoo/addons/stock_account`). Không phải Enterprise.

## Kết luận

Odoo 19 Community **có** bình quân gia quyền (AVCO): bình quân **liên hoàn**,
grain **công ty + sản phẩm** (thêm lot nếu bật lot valuation).

Core **không** có sổ tồn tháng theo kho/vị trí, và **không** tính một đơn giá
xuất cho cả kỳ như `ps.stock.onhand` (bình quân cuối kỳ VAS 02).

| | `ps.stock.onhand` | Odoo 19 AVCO |
|---|---|---|
| Phương pháp | BQGQ **cuối kỳ** | BQGQ **liên hoàn** (moving average) |
| Grain | company + warehouse + location + product + year/month | company + product (+ lot) |
| Giá xuất | Một giá cho cả tháng | `standard_price` tại từng phiếu xuất |
| Snapshot tồn đầu / nhập / xuất / cuối | Có | Không |

Đóng kỳ (`inventory_period`: manual / daily / monthly,
`inventory_valuation`: periodic / perpetual) chỉ quyết định **khi nào hạch toán**,
không đổi công thức giá.

## Cấu hình costing

Trên công ty (`res.company`) và nhóm sản phẩm (`product.category`,
company-dependent):

- `cost_method` / `property_cost_method`: `standard` | `fifo` | `average`
- `inventory_valuation` / `property_valuation`: `periodic` | `real_time`
- `inventory_period`: `manual` | `daily` | `monthly`

Sản phẩm kế thừa: `categ_id.property_cost_method` hoặc `company.cost_method`.

Giá đang dùng để xuất: `product.product.standard_price` (company-dependent).

## Khi nhập: `standard_price` mới

`product.value` **không** tính giá bình quân lúc nhận hàng. File đó là nhật ký
chỉnh giá / chỉnh giá trị phiếu **thủ công**.

Giá mới được ghi lúc stock move **nhập** sang `done`.

### Thời điểm

`stock.move._action_done()` — Validate picking.

Thứ tự:

1. Định giá phiếu **xuất** trước (`moves_out._set_value()`), dùng
   `standard_price` hiện tại.
2. `super()._action_done()` — `qty_available` đã gồm SL nhập.
3. Định giá phiếu **nhập** rồi cập nhật `standard_price`.

```177:189:odoo/addons/stock_account/models/stock_move.py
    def _action_done(self, cancel_backorder=False):
        # Use _is_out() instead of is_out since the move is not done
        # It's called before action_done since we need the current fifo
        # stack. Limitation when validating at same time out and ins
        moves_out = self.filtered(lambda m: m._is_out())
        moves_out._set_value()
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        moves_out = moves_out.exists()
        moves_in = moves.filtered(lambda m: m.is_in or m.is_dropship)
        moves_in.with_context(std_price_incremental_recompute=not moves_out)._set_value()
        moves._create_account_move()
        # Update standard price on outgoing fifo or lot valuated average products
        moves_out.product_id.filtered(lambda p: p.cost_method == 'fifo' or (p.cost_method == 'average' and p.lot_valuated))._update_standard_price()
```

Post hóa đơn mua liên kết move nhập: `account.move._post()` gọi lại
`_set_value()` trên move `is_in` / `is_dropship`. Lúc này `move.value` thường
lấy từ bill, rồi `standard_price` tính lại.

Sửa SL dòng nhập sau `done`: `stock.move.line._update_stock_move_value()` →
`_set_value()` (không bật fast path).

### Chuỗi gọi

```text
Validate picking
  stock.move._action_done()
    moves_out._set_value()                         # xuất: value = standard_price × SL
    super()._action_done()                         # tồn kho đã gồm SL nhập
    moves_in._set_value()                          # nhập: gán move.value, rồi update giá
      move.value = move._get_value()
      product._update_standard_price(extra_value, extra_quantity)
        standard_price = ...                       # disable_auto_revaluation=True
```

`move.value` khi nhập (`_get_value_data`), theo thứ tự:

1. Chỉnh tay: `product.value` có `move_id`
2. Bill / invoice (`_get_value_from_account_move`)
3. MO (`_get_value_from_production`)
4. PO / SO (`_get_value_from_quotation`)
5. Return (`_get_value_from_returns`)
6. `standard_price` cũ (`_get_value_from_std_price`)
7. Landed cost / extra (`_get_value_from_extra`)

### Hai đường tính giá

Context `std_price_incremental_recompute=not moves_out`:

- Chỉ validate **nhập** → fast path.
- Validate **nhập lẫn xuất** cùng lúc → full replay.

**Fast path** (`_update_standard_price` với `extra_value` / `extra_quantity`):

```text
SL cũ = qty_available − SL nhập
nếu SL cũ > 0 và SL sau nhập > 0:
    standard_price mới = (SL cũ × standard_price cũ + giá trị nhập) / SL sau nhập
nếu SL cũ ≤ 0:
    standard_price mới = giá trị nhập / SL nhập
```

```661:674:odoo/addons/stock_account/models/product.py
                    previous_qty = product.qty_available - added_qty
                    if (
                            product.uom_id.compare(previous_qty, 0) > 0
                            and product.uom_id.compare(product.qty_available, 0) > 0
                    ):
                        new_avg_cost = (previous_qty * product.standard_price + added_value) / product.qty_available
                    elif not product.uom_id.is_zero(added_qty):
                        new_avg_cost = added_value / added_qty
                    product.with_context(disable_auto_revaluation=True).sudo().standard_price = new_avg_cost
```

**Full replay** (`_run_average_batch(force_recompute=True)`): duyệt mọi IN/OUT
của sản phẩm theo `date, id`, tích lũy số lượng và giá trị. Dùng khi:

- Validate nhập cùng xuất
- Post bill
- Sửa SL sau done
- Đổi `cost_method` trên category
- Fast path không áp dụng được (sản phẩm không nằm trong `extra_value`)

Gán `standard_price` luôn kèm `disable_auto_revaluation=True` → **không** tạo
`product.value` khi nhập.

Khi xuất (AVCO, không lot valuation):

```text
move.value = product.standard_price × SL xuất
```

Không cập nhật `standard_price` vì đơn giá không đổi; chỉ giảm giá trị tồn.

## `product.value` — nhật ký thủ công

Model `product.value`: lịch sử sửa giá sản phẩm / lot / giá trị phiếu. Không
phải ledger từng lần nhập.

| Tạo record với | `create()` gọi |
|---|---|
| `move_id` (Adjust Valuation trên phiếu) | `stock.move._set_value()` → có thể kéo `_update_standard_price` |
| `lot_id` + `product_id` | `_update_standard_price()` |
| chỉ `product_id` (sửa Cost trên form sản phẩm) | không tính lại; ghi nhận giá đã đổi |

Sửa Cost trên form sản phẩm: `product.product.write()` → `_change_standard_price()`
→ tạo `product.value` (không `move_id`).

`_run_average_batch` dùng bản ghi `product.value` **không** `move_id` làm
điểm neo: replay move chỉ từ thời điểm chỉnh tay gần nhất.

## Grain và warehouse

`_run_average_batch` lọc `company_id` + `product_id`. Không tách warehouse /
location.

Context `warehouse_id` trên `total_value` / `avg_cost`: **chia tỷ lệ** giá trị
toàn công ty theo SL kho đang xem. Vẫn một `standard_price` cho cả công ty.

Location được định giá: `usage` in `internal`, `transit` và có `company_id`
(`stock.location._should_be_valued`).

## File nguồn

| Việc | File |
|---|---|
| Validate, `_set_value`, `_get_value` | `odoo/addons/stock_account/models/stock_move.py` |
| `_update_standard_price`, `_run_average_batch`, `_change_standard_price` | `odoo/addons/stock_account/models/product.py` |
| Nhật ký chỉnh tay | `odoo/addons/stock_account/models/product_value.py` |
| Post bill → revalue move nhập | `odoo/addons/stock_account/models/account_move.py` |
| Sửa SL sau done | `odoo/addons/stock_account/models/stock_move_line.py` |
| `inventory_period` / đóng sổ | `odoo/addons/stock_account/models/res_company.py` |
| Location có định giá | `odoo/addons/stock_account/models/stock_location.py` |
| Sổ tồn tháng (custom, chưa import) | `custom_addons/odoo-inventory/ps_stock/models/stock_onhand.py` |
