# Proposal finish — handover notes

`ps.mfg.proposal.finish` is the receipt of finished goods (and scrap)
from manufacturing orders. Header + lines: several MOs on one document,
any completed work order (not only the last), split qty / dest / lot per
line. Do not put `production_id` / `finish_qty` back on the header.

## Files

- `models/mfg_proposal_finish.py` (header + `ps.mfg.proposal.finish.line`)
- `views/ps_mfg_proposal_finish_views.xml`
- `models/mfg_wip.py` (`_get_available_proposals` reads **lines**)
- `migrations/19.0.0.6/post-migrate.py`
- `tests/test_proposal_finish.py` (`TestMfgProposalFinish`, post_install)
- `tests/test_wip.py` (`_make_finished_proposal` creates `line_ids`)

Manifest version `19.0.0.6`.

## Header vs line

Header keeps `code`, dates, `state`, chatter, optional
`dst_location_id` (default dest for new lines), `line_ids`,
`move_ids` (computed from `line_ids.move_id`) and legacy `picking_ids`
(receipts created before 19.0.0.11).

Removed from header (do not restore): `production_id`, `product_id`,
`product_uom_id`, `last_workorder_qty`, `finish_qty`, `workcenter_id`,
`source_location_id`, `picking_id`. Search MOs via computed
`production_ids` (`_search_production_ids` → `line_ids.production_id`).

Sequence: first line's workcenter `receipt_request_sequence_id` when
`line_ids` are in create vals, else `ir.sequence` `ps.mfg.proposal.finish`
(`DNF.`).

## Lines

| Field | Rule |
|---|---|
| `production_id` | `state=in_progress`, same company. **No** `all_workorders_done`. |
| `workorder_id` | Belongs to the MO, `total_qty > 0` (approved inbound shifts). |
| `product_id` | Related `production_id.product_id`, stored, **readonly**. |
| `x_product_code` | Char snapshot of `product.x_product_code` (ps_stock). User may edit on the line. **Does not write** the product master (unique + readonly there). Copied again when MO changes. Used as the move `description_picking` (no longer as lot name). |
| `finish_qty` | Positive. Sum of non-rejected lines for the same work order (this doc + others, including unsaved siblings) ≤ `workorder.total_qty`. Rejected proposals do not occupy remaining. |
| `dst_location_id` | Required, `usage=internal`. Default from header (`context default_dst_location_id` + create fallback). Scrap = another internal location, not Odoo `scrap_location`. |
| `move_id` | One `stock.move` per line, created/kept in sync while draft/pending (`_sync_finish_move`): Production → `dst_location_id`, no picking. Change MO → move recreated; change qty/dest/code → move updated; unlink line / reject → move cancelled. |
| Lots | Tracked products: **Details** button (`action_show_lot_details`) opens Odoo's *Detailed Operations* popup on `move_id` (Generate Serials / Import Lots / type `lot_name`; suggestions follow the product Lot/Serial sequence). `lot_names` / `lot_ids` / `lot_qty` are computed from the move lines. Submit/approve require every move line to have a lot and the total to equal `finish_qty`; serial lines qty 1. `lot_id` is legacy (single lot per line, migrated into the move line). |

Onchange production: reset lot / qty, copy `x_product_code`, default dest
from header, default work order = last WO that still has remaining.

Same work order may appear on several lines (good vs scrap, different
lots). That is the split-qty design.

## Remaining qty

`remaining_qty` = `workorder.total_qty` minus other non-rejected finish
lines of that WO, excluding self. Use `_origin.id` for the open form
record (NewId); also add unsaved sibling lines on the same header.

Finish receipt does **not** drain `ps.mfg.workorder.move` remaining and
does **not** set MO `done` / `qty_produced`. It is an inventory receipt,
not a routing transition.

## Approve / stock moves

Finished goods are received like mrp `move_finished_ids`: **no picking**.

- Operation type: per warehouse "Manufacturing Receipts" (Nhập thành phẩm
  SX), `stock.picking.type.ps_mfg_finish_type`, created lazily by
  `stock.warehouse._ps_mfg_get_finish_picking_type()` (code `incoming`,
  sequence `FG`, Production → `lot_stock_id`, `use_create_lots=True`,
  `use_existing_lots=False`). Warehouse = `dst_location_id.warehouse_id`.
  `use_create_lots` is what makes the Details popup show Generate/Import
  and makes `_action_done` create lots from `lot_name`.
- `stock.move._should_be_assigned` is False for MFG moves
  (`ps_finish_line_id` / `ps_workorder_move_id`) so confirm never builds a
  picking. `stock.move.line._compute_picking_type_id` takes the move's type
  when there is no picking (same as mrp).
- Production source is non-internal, so confirm reserves at once (state
  `assigned` with a lot-less move line).
- Submit and approve require at least one line and complete lots
  (`_check_finish_lots`).
- Approve: `price_unit` = cumulative `unit_cost` of the line's work order
  (`_get_finish_price_unit`, converted to the line UoM); untracked
  `quantity = demand`; `picked`; `_action_done`. Stock is in the
  destination **at once** — there is no draft receipt left for the
  warehouse to validate any more.
- Already `approved`: no-op. Legacy receipt with `picking_ids`: just set
  `approved`.
- Smart button **Stock Moves** (`action_view_stock_moves`) opens
  `stock.move.line` in the Moves History view. Move `reference` = receipt
  `code`; `action_open_reference` on the move/move line opens the receipt.
- Migration 19.0.0.11: draft/submitted lines get their move; legacy
  `lot_id` replaces the reserved move line.

## WIP

`_get_available_proposals` searches `ps.mfg.proposal.finish.line`
(`proposal_id.state=approved`, `transaction_date` ≤ period month-end),
**sums** `finish_qty` per production (partial receipts + scrap count),
description = latest proposal `code` for that MO. Productions already on
another WIP are skipped; own lines are ignored so refill keeps the
current record.

Old behaviour (latest header per production, `proposal.finish_qty`) is
gone. `_refill_lines` consumes dicts `{production, receipt_qty, description}`,
not header records.

## Migration `19.0.0.6`

`post-migrate.py` (line table already exists):

- Copy header `production_id` / qty / dest / product into one line:
  last work order by `sequence desc`.
- `picking_id` → `ps_mfg_proposal_finish_picking_rel`.

Old header columns stay in PostgreSQL (Odoo does not drop them).

## Tests

`TestMfgProposalFinish`: intermediate WO before `all_workorders_done`,
`x_product_code` edit without touching master, last-WO onchange,
split qty / remaining across proposals, line move Production → dest
without picking and kept in sync, lots required on submit (via move
lines), Details popup = Odoo move operations, generate serials + approve,
approve done moves + lots + reference + idempotent re-approve, reject
cancels moves, WIP sums lines / two MOs on one doc.

Run from `odoo/` (config `addons_path` is relative):

```
.venv/bin/python odoo-bin -c ../config/odoo.conf -d ps_mfg_wo_test \
  -u ps_mfg --test-enable --stop-after-init \
  --test-tags /ps_mfg:TestMfgProposalFinish \
  --http-port=18073 --data-dir=/tmp/odoo-ps-mfg-test
```

`TestMfgWip` on `ps_mfg_wo_test` can fail from leftover unique periods
and header amount defaults (`total_debit` etc.); that is DB pollution,
not finish-line logic. Fetch tests that use `_make_finished_proposal`
expect `line_ids`.

## Out of scope (do not "fix" unless asked)

- Drain workorder-move remaining when receiving scrap mid-routing.
- Bump `qty_produced` / close the MO on receipt.
- Dest domain `usage=inventory` / `scrap_location`.
- Write `x_product_code` back to `product.product`.
- i18n `vi_VN.po` / `ps_mfg.pot`.

After XML/model edits: `-u ps_mfg` + browser hard-refresh.
