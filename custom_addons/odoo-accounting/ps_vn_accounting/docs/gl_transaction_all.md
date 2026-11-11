# Transaction All — luồng dữ liệu

`gl.transaction.all` là sổ nhật ký chung (snapshot) các bút toán **đã posted**, định dạng kế toán Việt Nam. Mỗi dòng là **một cặp Nợ/Có** (tài khoản nợ, tài khoản có, số tiền), không còn một dòng = một `account.move.line`.

Cột hiển thị: Ngày, Số chứng từ, Khách hàng/Nhà cung cấp, Cost center, Tài khoản nợ, Tài khoản có, Số tiền, Diễn giải. Nút **Xuất Excel** trên list xuất đúng các cột này.

Nguồn sự thật lúc tạo chứng từ vẫn là `account.move` / `account.move.line`. Bảng này chỉ nhận dữ liệu khi chứng từ vào sổ.

Menu: **Accounting → Transactions → Transaction All** (chỉ đọc).

File chính: `models/gl_transaction_all.py`.

## 1. Post — đưa bút toán vào sổ

Mọi sổ (hóa đơn, phiếu kho, tiền, misc…) đều đi qua `account.move._post()`. Hook copy chạy **sau** `super()._post()`, lúc `state = posted` và số chứng từ đã có.

```mermaid
sequenceDiagram
    actor User
    participant UI as Invoice / Journal Entry
    participant Move as account.move
    participant CorePost as account.move._post (core)
    participant AML as account.move.line
    participant GL as gl.transaction.all
    participant DB as gl_transaction_all

    User->>UI: Confirm / Post
    UI->>Move: action_post()
    Move->>Move: _post(soft=False)
    Note over Move: inherit ps_vn_accounting<br/>gán TK 521/131 nếu out_refund
    Move->>CorePost: super()._post()
    CorePost->>AML: kiểm tra line, cân đối Nợ/Có
    CorePost->>Move: write state=posted, posted_before=True
    CorePost->>AML: parent_state = posted
    CorePost-->>Move: posted moves
    Move->>GL: _sync_from_moves(posted)
    GL->>GL: lọc state=posted
    GL->>AML: _get_sync_lines(moves)
    Note over GL,AML: bỏ line_section / subsection / note<br/>bỏ line không có account_id
    loop mỗi cặp Nợ/Có (waterfall)
        GL->>GL: _prepare_vals_from_pair()
        GL->>DB: create snapshot
    end
    GL-->>Move: recordset GL mới
    Move-->>UI: posted
    UI-->>User: chứng từ vào sổ
```

Điểm móc:

| Bước | Hàm | Việc |
|---|---|---|
| Nút Post | `account.move.action_post()` | Gọi `_post(soft=False)` |
| Vào sổ Odoo | `account.move._post()` (core) | `state = posted` |
| Copy sang sổ VN | `gl.transaction.all._sync_from_moves()` | Xóa snapshot cũ của move, insert cặp Nợ/Có |
| Ghép Nợ-Có | `gl.transaction.all._iter_debit_credit_pairs()` | Waterfall theo số tiền còn lại |
| Map 1 cặp | `gl.transaction.all._prepare_vals_from_pair()` | Dict cột VN từ 2 AML |

Hóa đơn tương lai (`soft=True` và `date` > hôm nay) **chưa** vào Transaction All. Cron post thật sự xong mới copy.

## 2. Sync một chứng từ — chi tiết `_sync_from_moves`

Mỗi chứng từ posted được tạo lại toàn bộ cặp Nợ/Có. Unique theo `(debit_move_line_id, credit_move_line_id)`.

Ví dụ hóa đơn: Nợ 131 1.100, Có 511 1.000, Có 33311 100 → hai dòng GL: `131/511 = 1.000` và `131/33311 = 100`.

```mermaid
sequenceDiagram
    participant Move as account.move (posted)
    participant GL as gl.transaction.all
    participant AML as account.move.line
    participant DB as gl_transaction_all

    Move->>GL: _sync_from_moves(moves)
    GL->>GL: sudo()
    GL->>Move: lọc state == posted
    alt không có move posted
        GL-->>Move: rỗng
    else có move posted
        GL->>AML: line_ids
        GL->>GL: _get_sync_lines()
        GL->>DB: xóa snapshot cũ theo move_id
        GL->>GL: _prepare_vals_from_move()
        loop từng cặp Nợ/Có
            GL->>GL: _prepare_vals_from_pair()
            GL->>DB: create
        end
        GL-->>Move: recordset vừa create
    end
```

## 3. Reset draft / Cancel — ra khỏi sổ

`button_cancel()` của core gọi `button_draft()` với chứng từ posted, nên cancel cũng xóa snapshot.

```mermaid
sequenceDiagram
    actor User
    participant UI as Journal Entry
    participant Move as account.move
    participant CoreDraft as button_draft (core)
    participant GL as gl.transaction.all
    participant DB as gl_transaction_all

    User->>UI: Reset to draft / Cancel
    UI->>Move: button_draft()
    Move->>CoreDraft: super().button_draft()
    CoreDraft->>Move: state = draft
    CoreDraft-->>Move: done
    Move->>GL: _unlink_from_moves(self)
    GL->>DB: search move_id in moves
    GL->>DB: unlink snapshot
    GL-->>Move: done
    Move-->>UI: draft
```

Post lại sau draft: quay về luồng 1, copy mới.

Xóa chứng từ: `move_line_id` / `move_id` `ondelete=cascade` → snapshot bị xóa theo.

## 4. Backfill khi upgrade module

Chứng từ posted trước khi có feature này chưa có dòng GL. `init()` chạy lúc `-u ps_vn_accounting` (và khi load registry): tìm move posted còn thiếu snapshot, gọi lại `_sync_from_moves` từng lô 200.

```mermaid
sequenceDiagram
    participant Odoo as Odoo registry / -u
    participant GL as gl.transaction.all.init
    participant SQL as PostgreSQL
    participant Sync as _sync_from_moves

    Odoo->>GL: init()
    GL->>SQL: xóa dòng cũ thiếu TK nợ/TK có
    GL->>SQL: SELECT DISTINCT move posted chưa có GL
    SQL-->>GL: danh sách move_id
    loop từng lô 200 move
        GL->>Sync: _sync_from_moves(moves)
        Sync->>SQL: create snapshot thiếu
    end
    GL-->>Odoo: xong
```

## 5. Xem sổ (menu chỉ đọc)

Không tạo bút toán từ màn này. User chỉ đọc snapshot.

```mermaid
sequenceDiagram
    actor User
    participant Menu as Accounting / Transactions
    participant Action as ps_action_gl_transaction_all
    participant GL as gl.transaction.all
    participant DB as gl_transaction_all

    User->>Menu: Transaction All
    Menu->>Action: act_window (create/edit/delete = False)
    Action->>GL: search list
    GL->>DB: SELECT snapshot
    DB-->>GL: rows
    GL-->>User: list Ngày, Số CT, KH/NCC, Cost center, TK nợ, TK có, Số tiền, Diễn giải
    opt xuất Excel
        User->>GL: Export Excel
        GL-->>User: file .xlsx cột tiếng Việt
    end
    opt mở form
        User->>GL: click dòng
        GL-->>User: form readonly + link sang account.move
    end
```

## 6. Toàn cảnh vòng đời một chứng từ

```mermaid
sequenceDiagram
    actor User
    participant Move as account.move
    participant AML as account.move.line
    participant GL as gl.transaction.all

    User->>Move: tạo draft (invoice / entry / stock / payment)
    Move->>AML: create line Nợ/Có
    Note over GL: draft chưa vào Transaction All

    User->>Move: Post
    Move->>AML: parent_state = posted
    Move->>GL: copy line → snapshot

    User->>Move: Reset to draft
    Move->>GL: xóa snapshot
    Note over AML: line vẫn còn, state = draft

    User->>Move: Post lại
    Move->>GL: copy lại snapshot mới
```

## Ghi chú

- Draft **không** vào Transaction All. Sổ này chỉ có bút toán đã vào sổ.
- Mọi journal đều vào chung một bảng (đúng nghĩa Transaction All).
- Custom cột VN sửa `_prepare_vals_from_pair()`. Hook `_post` giữ nguyên.
- User post không cần quyền create trên GL: `_sync_from_moves` chạy `sudo()`.
- Cost center lấy từ line Nợ, rồi line Có, rồi header chứng từ (`account.move.cost_center_id`).
