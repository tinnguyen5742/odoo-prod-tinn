# Costing method theo kho

Module `ps_stock_account` kế thừa `stock_account` của Odoo 19 Community. Tài liệu này giải thích những gì PatSoft thay đổi: **khi validate phiếu kho, method tính giá lấy từ kho**, không còn từ nhóm sản phẩm.

Công thức bình quân liên hoàn của core nằm ở [Odoo 19 Community AVCO](../../ps_stock/doc/odoo19_avco.md).

## Core định giá thế nào

Odoo 19 định giá theo cặp **công ty + sản phẩm**. Method không gắn trên từng phiếu hay từng kho, mà khai báo trên nhóm sản phẩm (`product.category.property_cost_method`) hoặc trên công ty (`res.company.cost_method`). Field `product.cost_method` chỉ *tính* ra từ hai nguồn đó. `standard_price` là company-dependent: một đơn giá cho cả công ty. AVCO và FIFO khi chạy sẽ duyệt mọi phiếu nhập–xuất của sản phẩm trong công ty, không lọc theo kho.

Lúc bấm Validate picking, `stock.move._set_value()` đọc `move.product_id.cost_method` rồi chọn nhánh:

| Method | Phiếu nhập | Phiếu xuất | `standard_price` |
|---|---|---|---|
| `standard` | `move.value` lấy từ PO, hóa đơn, hoặc giá chuẩn | `standard_price × số lượng` | Không đổi khi nhập |
| `average` (AVCO) | Cùng nguồn giá với Standard | `standard_price × số lượng` | Cập nhật bình quân liên hoàn |
| `fifo` | Cùng nguồn giá với Standard | Lấy từ stack các lần nhập còn lại | Cập nhật theo stack còn lại |

Với AVCO, khi còn tồn trước lúc nhập:

```text
giá mới = (tồn cũ × giá cũ + số lượng nhập × giá nhập) / tồn sau nhập
```

Hai phiếu cùng đơn giá thì bình quân không đổi. Nhập 100 cái giá 20.000 rồi 50 cái giá 20.000, `standard_price` vẫn 20.000. Muốn thấy AVCO chạy, lần nhập sau phải khác giá: thêm 50 cái giá 30.000 thì thành 22.500.

## PatSoft đổi gì

Cả ba phần dưới đây nằm trong `ps_stock_account`.

### Cấu hình trên kho

Mỗi kho có field `x_property_cost_method`, chọn một trong hai:

- `average` — Average Cost (AVCO), đây là mặc định
- `standard` — Standard Price

FIFO không mở trên kho. Form nhóm sản phẩm ẩn `property_cost_method`: field vẫn còn trong database vì core cần, nhưng người dùng không sửa được trên UI. Chỗ đổi method là **Inventory → Configuration → Warehouses**.

### Mặc định AVCO

Công ty mới nhận `res.company.cost_method = average`, kho mới nhận `x_property_cost_method = average`, nhóm sản phẩm mới nhận `ir.default` của `property_cost_method` là `average`.

Khi cài module hoặc nâng lên `19.0.0.3`, hook ghi đè những company và kho đang khác AVCO sang `average`. Nhóm sản phẩm đã tồn tại thì không đụng tới, để tránh revalue hàng loạt.

### Lúc tính giá: method của kho

Thay vì sửa từng dòng `product.cost_method` trong core, override `_set_value` gắn method của kho vào context `force_cost_method`. Compute của `product.cost_method` đọc context đó, nên cả nhánh core phía dưới (`_get_value`, FIFO, `_update_standard_price`) tự theo kho.

Form sản phẩm không có `force_cost_method` trong context, nên ô Costing Method trên form vẫn hiện method của nhóm hoặc công ty. Context chỉ được gắn trong lúc validate phiếu.

## Kho nào được lấy method

`_get_valuation_warehouse()` chọn kho ở phía đang được định giá:

| Loại phiếu | Kho dùng | Lý do |
|---|---|---|
| Nhập (`is_in` / `_is_in()`) | `location_dest_id.warehouse_id` | Hàng đang vào kho đích |
| Xuất (`is_out` / `_is_out()`) | `location_id.warehouse_id` | Hàng đang ra từ kho nguồn |
| Còn lại (dropship, …) | kho đích, rồi kho nguồn, rồi `picking_type_id.warehouse_id` | Fallback |

Phiếu xuất không lấy kho đích vì đích thường là khách hoặc nhà cung cấp, không có `x_property_cost_method`. Nếu không gắn được kho nào, không set `force_cost_method` và core dùng method nhóm hoặc công ty như cũ.

## Chuỗi gọi lúc validate

```text
Validate picking
  stock.move._action_done()                          # core
    moves_out._set_value()                           # override: group theo kho, gắn context
      super(StockMove, moves)._set_value()           # core; product.cost_method = method kho
    super()._action_done()                           # phiếu done, tồn đã gồm số lượng nhập
    moves_in._set_value()                            # giống trên, cho phiếu nhập
      product._update_standard_price()               # AVCO cập nhật giá; Standard bỏ qua
    moves_out.product_id._update_standard_price()    # core, theo method nhóm
  ps_stock_account._action_done()                    # chạy lại update giá xuất theo method kho
```

`super(StockMove, moves)._set_value()` gọi thẳng `_set_value` của core, không quay lại override của `ps_stock_account`. Vì vậy không cần flag chống đệ quy.

### `_set_value` tách phiếu theo method rồi gọi core

```27:31:ps_stock_account/models/stock_move.py
    def _set_value(self, correction_quantity=None):
        for method, moves in self.grouped(lambda move: move._get_warehouse_cost_method()).items():
            if method:
                moves = moves.with_context(force_cost_method=method)
            super(StockMove, moves)._set_value(correction_quantity)
```

Hai kho cùng AVCO được gộp thành một lần gọi core. Một kho AVCO và một kho Standard thì core chạy hai lần, mỗi lần một giá trị `force_cost_method`.

### Compute đọc context

```9:14:ps_stock_account/models/product_template.py
    def _compute_cost_method(self):
        forced = self.env.context.get('force_cost_method')
        if forced:
            self.cost_method = forced
            return
        super()._compute_cost_method()
```

`@api.depends_context('force_cost_method')` tách cache theo method. `product.product.cost_method` related từ `product_tmpl_id.cost_method` nên kế thừa depends_context đó.

### Cập nhật giá sau phiếu xuất

Sau `_set_value`, core còn gọi:

```python
moves_out.product_id.filtered(
    lambda p: p.cost_method == 'fifo' or (p.cost_method == 'average' and p.lot_valuated)
)._update_standard_price()
```

Đoạn này đọc `product.cost_method` trên env của `moves_out`, chưa có `force_cost_method`, nên thấy method nhóm chứ không phải method kho. Override `_action_done` chạy lại cùng bộ lọc, lần này có context, để FIFO hoặc AVCO có lot valuation cập nhật đúng theo kho.

## Ví dụ

Kho WH/Stock để AVCO. Sản phẩm Bánh Quy tồn 0, `standard_price` ban đầu 0.

| Phiếu | Số lượng | Đơn giá PO | `move.value` | `standard_price` sau phiếu |
|---|---|---|---|---|
| P00001 nhập | 100 | 20.000 | 2.000.000 | 20.000 |
| P00002 nhập | 50 | 20.000 | 1.000.000 | 20.000 (cùng đơn giá) |
| P00003 nhập | 50 | 30.000 | 1.500.000 | **22.500** |

```text
(150 × 20.000 + 50 × 30.000) / 200 = 22.500
```

Xuất 20 cái từ kho AVCO thì `move.value = 22.500 × 20`. `standard_price` không đổi vì xuất AVCO chỉ lấy đơn giá hiện tại, không kéo bình quân.

Nếu cùng sản phẩm còn một kho để Standard, phiếu nhập kho đó không cập nhật `standard_price` công ty. Xem mục giới hạn bên dưới.

## Giới hạn: grain vẫn là công ty

Thay đổi hiện tại chỉ chọn **nhánh thuật toán** (Standard hay AVCO) theo kho. Core vẫn giữ một `standard_price` cho cả công ty, và `_run_average_batch` vẫn cộng nhập–xuất mọi kho.

Hệ quả: kho A AVCO, kho B Standard, nhập vào A vẫn ghi `product.standard_price`. Xuất từ B (Standard) dùng đúng giá đó, nên giá chuẩn kho B bị kéo theo bình quân của kho A.

Chuyển kho nội bộ cũng chưa được định giá riêng. Khi cả hai location `_should_be_valued`, core không tạo phiếu IN/OUT nên costing không chạy.

Tách giá theo kho — AVCO từng kho, chuyển kho thành xuất nguồn cộng nhập đích — là bước sau, chưa làm trong version này.

## File liên quan

| Việc | File |
|---|---|
| Field method trên kho | `models/stock_warehouse.py`, `views/stock_warehouse_views.xml` |
| Ẩn method nhóm sản phẩm | `views/product_category_views.xml` |
| Default AVCO, backfill company và kho | `models/res_company.py`, `data/cost_method_defaults.xml`, `migrations/19.0.0.3/post-migrate.py` |
| Context `force_cost_method` | `models/product_template.py` |
| Group phiếu và gắn context | `models/stock_move.py` |

Nâng cấp: `-u ps_stock_account` (version `19.0.0.3`).
