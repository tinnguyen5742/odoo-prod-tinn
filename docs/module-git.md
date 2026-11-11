# Làm việc trên repo module

Mỗi thay đổi đi theo: **Issue → nhánh → Pull Request → squash vào `main`**.

Không commit thẳng lên `main`. Làm việc trong **repo của module**. Trước khi tạo nhánh, `git status` phải ở nhánh `main` (không phải *detached HEAD*).

Hai người không sửa cùng một file trong hai PR đang mở. Các file dễ đụng:

- `__manifest__.py`
- `i18n/*.po`
- cùng một file trong `models/`

File dịch (`.po`) để PR riêng, sau khi phần tính năng đã vào `main`.

---

## 1. Lấy việc

Mở Issue trên repo module.

- Gán **một** người
- Viết rõ sẽ sửa gì, file nào

Chỉ bắt đầu khi Issue đã gán cho mình.

## 2. Tạo nhánh từ `main` mới nhất

```bash
git checkout main
git pull
git checkout -b feat/<số-issue>-ten-ngan
```

| Loại việc | Tên nhánh |
|---|---|
| Tính năng | `feat/12-hop-dong-hang-loat` |
| Sửa lỗi | `fix/34-depends` |

Một nhánh = một việc.

## 3. Mở Draft PR ngay

```bash
git push -u origin HEAD
```

Trên GitHub: **Compare & pull request** → chọn **Draft**.

PR nháp cũng được. Tab **Files changed** cho cả đội biết file nào đang được sửa, tránh làm trùng.

Trong mô tả PR ghi `Fixes #<số-issue>`.

## 4. Sửa code và commit

Commit nhỏ, đúng việc (`feat:`, `fix:`, `docs:`, `chore:`).

- `__manifest__.py`: một PR đang mở được đụng file này. Bump `version` để PR merge sau cùng.
- `models/__init__.py`: chỉ **thêm** dòng import, giữ thứ tự cũ.
- `security/ir.model.access.csv`: thêm hàng mới, không format lại cả file.

## 5. Cập nhật `main` rồi mới Ready

Trước khi bấm **Ready for review**:

```bash
git fetch origin
git rebase origin/main
git push --force-with-lease
```

Hoặc trên GitHub bấm **Update branch**.

Nhờ một người xem PR. GitHub báo *This branch is out-of-date* thì cập nhật `main` trước, rồi mới merge.

## 6. Squash vào `main`

Khi PR đã duyệt:

1. **Squash and merge** (không dùng *Create a merge commit*).
2. Tiêu đề PR chính là commit trên `main`.
3. GitHub xóa nhánh sau khi merge.

Force-push lên `main` không dùng. Nhánh việc được `--force-with-lease` sau bước rebase.

## 7. Xong

`main` của repo module đã có thay đổi. Việc tiếp theo trên repo này: kéo `main` mới rồi làm Issue khác.

```bash
git checkout main
git pull
```
