# Odoo Core MRP: Kiến Trúc Stock Move, Vòng Đời Ghi Nhận & Cơ Chế Lot/Serial NVL

Tài liệu kỹ thuật tổng hợp chi tiết từ mã nguồn Odoo Core (`odoo/addons/mrp`, `odoo/addons/stock`) về kiến trúc dữ liệu và vòng đời xử lý của `stock.move`, `stock.move.line` và `stock.lot`.

---

## 1. Cơ Chế Chọn Lot / Serial Của Nguyên Vật Liệu (NVL)

### 1.1. Cấu trúc dữ liệu chuẩn: Phân tầng `stock.move` và `stock.move.line`

Odoo tách biệt hoàn toàn giữa **Kế hoạch nhu cầu** và **Thực tế xuất kho theo Lô/Serial**:

```
mrp.production (Lệnh sản xuất - MO)
  └── move_raw_ids: stock.move (Kế hoạch nhu cầu NVL)
        │   - product_id: Linh kiện A
        │   - product_uom_qty: 100 kg (Nhu cầu dự kiến)
        │   - quantity: 100 kg (Số lượng thực tế đã xuất/tiêu thụ)
        │
        └── move_line_ids: stock.move.line (Thực tế chi tiết theo Lô)
              ├── Dòng 1: lot_id = LÔ-01 | quantity = 60 kg | location_id = WH/Stock
              └── Dòng 2: lot_id = LÔ-02 | quantity = 40 kg | location_id = WH/Stock
```

1. **`stock.move` (Cấp độ Nhu cầu)**:
   - Đại diện cho một dòng nguyên vật liệu trong tab **Components** (`move_raw_ids`).
   - Quản lý số lượng ở mức tổng: Nhu cầu ban đầu (`product_uom_qty`), số lượng tiêu thụ thực tế (`quantity`), trạng thái (`state`).
   - **Không lưu trực tiếp `lot_id`** (chỉ có trường `lot_ids` kiểu `Many2many` tính toán để hiển thị tóm tắt lên view).
2. **`stock.move.line` (Cấp độ Chi tiết dịch chuyển / Detailed Operations)**:
   - Nơi thực sự lưu trữ **Số Lô / Serial (`lot_id`)** và chuỗi số lô thủ công (`lot_name`).
   - Mỗi bản ghi liên kết với `move_id`, chỉ định rõ `lot_id`, `quantity`, vị trí nguồn `location_id` và đích `location_dest_id`.
   - Một dòng `stock.move` có thể gồm nhiều `stock.move.line` nếu lấy từ nhiều lô (Split Lots).

---

### 1.2. Cách chọn Lot/Serial trong quy trình Odoo chuẩn

#### A. Phân bổ tự động khi Xác nhận lệnh (Automatic Reservation)
- Khi MO được bấm **Confirm** (`action_confirm`), hệ thống gọi hàm giữ hàng `action_assign()` ➔ `_action_assign()`.
- Engine kho quét bảng `stock.quant` tại vị trí nguồn (`location_src_id`):
  - Dựa trên **Chiến lược lấy hàng (Removal Strategy)** cấu hình tại Location hoặc Product Category:
    - **FIFO** (Nhập trước xuất trước theo ngày tạo).
    - **LIFO** (Nhập sau xuất trước).
    - **FEFO** (Hết hạn trước xuất trước theo `removal_date`).
    - **Closest Location** (Vị trí gần nhất).
  - Tự động sinh ra các bản ghi `stock.move.line` giữ chỗ trước với các `lot_id` thỏa điều kiện.
  - Số lượng trong lô được tạm khóa vào `reserved_quantity` của `stock.quant`.

#### B. Thao tác thủ công trên Form Lệnh sản xuất (`mrp_production_views.xml`)
Tại tab **Components** của MO:
1. **Nút "Details" (`action_show_details`)**:
   - Nằm trên từng dòng NVL có quản lý lô (`invisible="has_tracking == 'none'"`):
     ```xml
     <button name="action_show_details" type="object" title="Show Details" string="Details"
             invisible="not show_details_visible or has_tracking == 'none'"/>
     ```
   - Nút này gọi phương thức `action_show_details()` trong `odoo/addons/stock/models/stock_move.py` (line 984), mở view popup `mrp.view_mrp_stock_move_operations` (kế thừa từ `stock.view_stock_move_operations`).
2. **Trong popup Details**:
   - Hiển thị danh sách `move_line_ids` (widget `sml_x2_many`).
   - Người dùng có thể:
     - Đổi sang `lot_id` khác đang có sẵn tồn kho.
     - Chia dòng (Split line) để nhập số lượng cho từng số lô khác nhau.
     - Dùng nút tiện ích `generate_serials` hoặc `import_lots` để tạo/nhập nhanh danh sách Serial.
3. **Cột `lot_ids` ngoài bảng chính**:
   - `lot_ids = fields.Many2many('stock.lot', ...)` hiển thị dưới dạng tag (`widget="many2many_tags"`), giúp người dùng nhìn thấy nhanh các lô đang được gán mà không cần mở popup.

#### C. Thao tác tại Lệnh công đoạn (Work Order)
- **Odoo Community (`mrp_workorder_views.xml`)**:
  - Tab *Components* trên Form Work Order chỉ có thuộc tính xem (`readonly="1"`). Việc chọn số lô NVL thực hiện tập trung trên form MO hoặc qua phiếu xuất chuyển kho.
- **Odoo Enterprise (Shop Floor / Tablet View)**:
  - Cho phép gắn các bước hướng dẫn công đoạn (Operation Steps / Quality Checks).
  - Công nhân thao tác tại trạm dùng máy quét barcode hoặc màn hình cảm ứng để quét trực tiếp mã barcode của Lot/Serial NVL khi lắp ráp vào sản phẩm.

---

## 2. Tại Sao Có Cả `production_id` và `raw_material_production_id` Trên `stock.move`?

Trong `odoo/addons/mrp/models/stock_move.py`, Odoo khai báo đồng thời:
```python
production_id = fields.Many2one(
    "mrp.production",
    "Production Order for finished products",
    check_company=True,
    index="btree_not_null",
    ondelete="cascade",
)

raw_material_production_id = fields.Many2one(
    "mrp.production",
    "Production Order for components",
    check_company=True,
    index="btree_not_null",
    ondelete="cascade",
)

created_production_id = fields.Many2one(
    "mrp.production", "Created Production Order", check_company=True, index=True
)
```

Một Lệnh sản xuất (`mrp.production`) luôn bao gồm **hai luồng dịch chuyển kho (`stock.move`) ngược chiều nhau**:
- **Luồng Đầu vào (Tiêu thụ NVL)**: Kho vật lý ➔ Vị trí ảo Sản xuất (`Virtual Locations/Production`).
- **Luồng Đầu ra (Thành phẩm / Phụ phẩm)**: Vị trí ảo Sản xuất ➔ Kho vật lý.

```
       [Kho Nguyên Liệu Vật Lý (location_src_id)]
                          │
                          │  (raw_material_production_id: move_raw_ids)
                          ▼
             [Vị trí ảo Sản xuất (Production)]
                          │
                          │  (production_id: move_finished_ids)
                          ▼
       [Kho Thành Phẩm Vật Lý (location_dest_id)]
```

### Các lý do kiến trúc cốt lõi:

### 2.1. Phân tách quan hệ One2many trên `mrp.production`
Trên model `mrp.production` (`mrp_production.py` lines 203-215):
```python
move_raw_ids = fields.One2many(
    "stock.move", "raw_material_production_id", "Components", ...
)
move_finished_ids = fields.One2many(
    "stock.move", "production_id", "Finished Products", ...
)
```
- ORM của Odoo yêu cầu mỗi trường `One2many` phải có một trường khóa ngoại `Many2one` nghịch đảo tương ứng.
- **Nếu chỉ dùng 1 trường `production_id`**: ORM không thể phân biệt dòng nào là Nguyên vật liệu (tab Components), dòng nào là Thành phẩm/Phụ phẩm (tab By-Products & Finished). Hai bảng này sẽ bị gộp chung dữ liệu, không thể dùng tính năng thêm/sửa trực tiếp trên bảng (`editable="bottom"`), và các thao tác ghi dữ liệu sẽ bị xung đột.

---

### 2.2. Tự động tính toán Location Nguồn và Đích (`_compute_location_id` / `_compute_location_dest_id`)
Nhờ tách biệt 2 trường, Odoo tự động xác định vị trí nguồn và đích mà không cần logic rườm rà (`stock_move.py` lines 88-110):

```python
@api.depends(
    "raw_material_production_id.location_src_id", "production_id.location_src_id"
)
def _compute_location_id(self):
    for move in self:
        if move.production_id:
            # Thành phẩm: Nguồn xuất phát từ Vị trí Sản xuất ảo
            move.location_id = move.product_id.with_company(
                move.company_id
            ).property_stock_production.id
        elif move.raw_material_production_id:
            # Nguyên liệu: Nguồn lấy từ Kho vật lý cấp nguyên liệu của MO
            move.location_id = move.raw_material_production_id.location_src_id


@api.depends(
    "raw_material_production_id.location_dest_id", "production_id.location_dest_id"
)
def _compute_location_dest_id(self):
    for move in self:
        if move.production_id:
            # Thành phẩm: Đích đến là Kho nhập thành phẩm của MO
            move.location_dest_id = move.production_id.location_dest_id
        elif move.raw_material_production_id:
            # Nguyên liệu: Đích đến là Vị trí Sản xuất ảo
            move.location_dest_id = move.product_id.with_company(
                move.company_id
            ).property_stock_production.id
```

---

### 2.3. Phân định rõ vai trò Cung (Supply) và Cầu (Demand) trong chuỗi cung ứng
- **`raw_material_production_id` = Nhu cầu (Demand / Consumption)**:
  - Đại diện cho việc tiêu thụ hàng.
  - Khi kho thiếu nguyên liệu, MRP Scheduler hoặc Quy tắc tái đặt hàng (Reordering Rules) dựa vào trường này để xác định MO nào đang cần hàng, từ đó tự động sinh Lệnh mua hàng (Purchase Order) hoặc MO con cấp dưới.
- **`production_id` = Nguồn cung (Supply / Production)**:
  - Đại diện cho việc bổ sung lượng thành phẩm vào kho.
- **`created_production_id` = Liên kết chuỗi cung ứng ngược (Upstream Trigger)**:
  - Lưu move nhu cầu từ chứng từ khác kích hoạt sinh ra MO này (ví dụ: Một dòng `stock.move` xuất bán của Sales Order kích hoạt tạo MO theo quy tắc MTO - Make to Order).

---

### 2.4. Hạch toán chi phí giá vốn (Valuation & Costing)
- Các move mang **`raw_material_production_id`**: Xuất kho NVL ➔ Kết chuyển chi phí vào tài khoản Chi phí sản xuất dở dang (WIP - Work in Progress).
- Các move mang **`production_id`**: Nhập kho Thành phẩm ➔ Thu nhận toàn bộ giá trị NVL đã xuất cộng với chi phí vận hành máy móc/nhân công từ các Work Order (`order._cal_price()`) để kết chuyển thành giá vốn thành phẩm (`standard_price`).

---

## 3. Vòng Đời Ghi Nhận Của `stock.move` Sau Khi Tạo MO

Một `stock.move` trong MRP trải qua **3 thời điểm ghi nhận chính**:

```
[1. Tạo MO (Draft)]
       │  _compute_move_raw_ids() ➔ _get_moves_raw_values()
       ▼
   state = 'draft'  (Chưa có tác động kho)
       │
[2. Bấm "Confirm"]
       │  action_confirm() ➔ moves_to_confirm._action_confirm()
       ▼
   state = 'confirmed' (Ghi nhận Nhu cầu dự báo - Forecast)
       │
       │  action_assign() ➔ _action_assign()
       ▼
   state = 'assigned'  (Ghi nhận Giữ hàng - Reservation trong stock.move.line)
       │
[3. Bấm "Mark as Done / Produce All"]
       │  button_mark_done() ➔ _post_inventory()
       ▼
   state = 'done'      (GHI NHẬN CHÍNH THỨC TỒN KHO THỰC TẾ & KẾ TOÁN GIÁ VỐN)
```

---

### Giai đoạn 1: Khi tạo MO & chọn BoM — Khởi tạo Move dự thảo (`draft`)

- **Thời điểm**: Khi người dùng tạo bản ghi `mrp.production`, chọn Sản phẩm và Định mức (BoM) ở trạng thái Dự thảo.
- **Mã nguồn thực thi**:
  - `mrp_production.py` (lines 822-841): Hàm compute `_compute_move_raw_ids()` gọi `_get_moves_raw_values()` (lines 1339-1360).
  - Hệ thống "rã" BoM (`bom.explode`) để tính toán định mức và tạo các bản ghi `stock.move` cho nguyên vật liệu (`raw_material_production_id = mo.id`).
  - Hàm `_compute_move_finished_ids()` tạo các bản ghi `stock.move` cho thành phẩm và phụ phẩm (`production_id = mo.id`).
- **Trạng thái**: `stock.move` có `state = 'draft'`.
- **Tác động kho**: **Hoàn toàn chưa có**. Chưa giữ hàng (`reserved_quantity = 0`), chưa trừ tồn thực tế, chưa ảnh hưởng tồn dự báo.

---

### Giai đoạn 2: Khi bấm nút "Confirm" — Ghi nhận Nhu cầu & Giữ hàng (`confirmed` / `assigned`)

- **Thời điểm**: Khi người dùng nhấn nút **Confirm** trên form MO.
- **Mã nguồn thực thi**: Phương thức `action_confirm()` trong `mrp_production.py` (lines 1625-1667):
  ```python
  # Line 1656: Đồng bộ phương thức mua sắm (MTO/MTS)
  move_raws_to_adjust._adjust_procure_method()

  # Line 1657: Xác nhận tất cả các move NVL và thành phẩm
  moves_to_confirm._action_confirm(merge=False)

  # Line 1661: Chạy scheduler nếu có nguyên liệu bị thiếu hụt
  self.move_raw_ids._trigger_scheduler()
  ```
- **Tác động 1 - Ghi nhận Nhu cầu dự báo (Forecast Quantity)**:
  - Các move chuyển sang trạng thái **`state = 'confirmed'`**.
  - Tồn dự báo (`virtual_available`) của NVL bị giảm đi tương ứng với số lượng cần tiêu thụ.
  - Tồn dự báo của Thành phẩm tăng lên tương ứng với số lượng dự kiến sản xuất.
- **Tác động 2 - Giữ hàng trong kho (Reservation)**:
  - Tiếp theo, Odoo gọi `action_assign()` ➔ `move_raw_ids._action_assign()`.
  - Nếu trong kho vật lý có đủ tồn khả dụng:
    - Trạng thái move chuyển sang **`state = 'assigned'`** (Partially Available hoặc Available).
    - Hệ thống tạo các bản ghi **`stock.move.line`**, ghi nhận số lượng giữ chỗ vào trường `reserved_quantity` của `stock.quant`.
    - Ngăn không cho các đơn hàng bán (SO) hoặc MO khác lấy mất số nguyên liệu này.

---

### Giai đoạn 3: Khi bấm "Mark as Done / Produce All" — GHI NHẬN TỒN KHO THỰC TẾ & KẾ TOÁN (`done`)

Đây là mốc **chính thức ghi nhận vào sổ kho vật lý và ghi sổ kế toán tài chính**.

- **Thời điểm**: Khi quá trình sản xuất hoàn thành và người dùng bấm **Mark as Done** hoặc **Produce All**.
- **Mã nguồn thực thi**:
  Nút gọi `button_mark_done()` trong `mrp_production.py` (line 2219), bên trong thực thi hàm cốt lõi **`_post_inventory(cancel_backorder=True)`** (lines 1907-1955):

  ```python
  def _post_inventory(self, cancel_backorder=False):
      # 1. Lọc các move NVL cần xuất kho (line 1909-1915)
      # 2. XUẤT KHO NGUYÊN VẬT LIỆU (line 1917)
      self.with_context(skip_mo_check=True).env["stock.move"].browse(
          moves_to_do
      )._action_done(cancel_backorder=cancel_backorder)

      # 3. TÍNH TOÁN GIÁ THÀNH SẢN XUẤT (line 1948)
      order.with_company(order.company_id)._cal_price(moves_to_do_by_order[order.id])

      # 4. NHẬP KHO THÀNH PHẨM VÀ PHỤ PHẨM (line 1951)
      moves_to_finish = moves_to_finish._action_done(cancel_backorder=cancel_backorder)

      # 5. LIÊN KẾT TRUY XUẤT NGUỒN GỐC (line 1954)
      order.move_finished_ids.move_line_ids.consume_line_ids = [
          (6, 0, consume_move_lines.ids)
      ]
  ```

- **Tác động thực tế**:
  1. **Tồn kho thực tế (On Hand / `stock.quant`)**:
     - Số lượng NVL thực tế (`qty_available`) tại kho nguồn bị trừ đi.
     - Số lượng Thành phẩm thực tế (`qty_available`) tại kho đích được cộng vào.
     - Trạng thái các move chuyển thành **`state = 'done'`** và bị khóa (`is_locked = True`).
  2. **Truy xuất nguồn gốc 2 chiều (Full Traceability)**:
     - Dòng 1954 liên kết `consume_line_ids` giữa move line thành phẩm và move line NVL. Cho phép người dùng bấm nút **Traceability Report** để biết chính xác chiếc bánh thành phẩm mang số lô X được làm từ bao bột mang số lô Y nào.
  3. **Hạch toán Kế toán & Định giá tồn kho**:
     - Tạo bản ghi định giá `stock.valuation.layer` cho cả đầu xuất NVL và đầu nhập Thành phẩm.
     - Nếu danh mục sản phẩm áp dụng phương pháp Kê khai thường xuyên (*Automated Inventory Valuation*):
       - **Bút toán xuất NVL**: Nợ TK Chi phí SXKD dở dang (WIP - TK 154) / Có TK Tồn kho NVL (TK 152).
       - **Bút toán nhập Thành phẩm**: Nợ TK Tồn kho Thành phẩm (TK 155) / Có TK Chi phí SXKD dở dang (WIP - TK 154) (giá trị bao gồm chi phí NVL + chi phí Workcenter).

---

## 4. Bảng Tổng Hợp Vòng Đời `stock.move` Trong MRP

| Bước thực hiện | Điểm kích hoạt mã nguồn | Trạng thái `stock.move` | Trạng thái `mrp.production` | Dữ liệu `stock.move.line` | Tồn kho (`stock.quant`) | Kế toán & Giá vốn |
| :--- | :--- | :---: | :---: | :--- | :--- | :--- |
| **1. Khởi tạo MO** | `_compute_move_raw_ids()` `_compute_move_finished_ids()` | `draft` | `draft` | Chưa có | Chưa có tác động | Chưa ghi nhận |
| **2. Bấm Confirm** | `action_confirm()` ➔ `_action_confirm()` | `confirmed` | `confirmed` | Chưa có | Cập nhật **Tồn dự báo (Forecast)** | Chưa ghi nhận |
| **3. Giữ hàng** | `action_assign()` ➔ `_action_assign()` | `assigned` | `confirmed` | Sinh các dòng giữ chỗ lô/số lượng | Khóa tồn giữ chỗ (`reserved_quantity`) | Chưa ghi nhận |
| **4. Bấm Mark Done** | `button_mark_done()` ➔ `_post_inventory()` ➔ `_action_done()` | **`done`** | **`done`** | Khóa các dòng chi tiết đã xuất/nhập | **Trừ/Cộng tồn kho thực tế (`quantity`)**, giải phóng giữ chỗ | Sinh `stock.valuation.layer`, tạo bút toán `account.move` (WIP / Kho) |
