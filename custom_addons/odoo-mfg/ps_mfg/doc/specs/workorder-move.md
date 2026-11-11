# Workorder move — handover notes

`ps.mfg.workorder.move` is the shift document for transferring quantity
between work orders. It records issued value for WIP closing, carries the
cumulative operation cost **and** consumes workshop stock on Complete. Do
not add a hidden location per work center.

## Files

- `models/mfg_work_order_move.py`
- `models/mfg_work_order.py` (`consumed_lot_ids`)
- `views/ps_mfg_workorder_move_views.xml`
- `tests/test_workorder_move.py`

## Form flow

Pick **Work Center** first, then the **Manufacturing Order** (domain
`state=in_progress` and `workcenter_id = workcenter_id`), then **To** work
order (any work order of the MO); **From** is derived. `workcenter_id` is a
regular required field (it used to be related to the MO). Changing it
clears a MO of another work center; constraint `_check_workcenter_production`
enforces the match. `create` fills `workcenter_id` from the MO when callers
(import, old code, tests) omit it.

### From / To (issue #10)

- **Empty From = "Bắt đầu" (Start).** Valid only when To is the first work
  order (`_check_workorder_move`). From, when set, must come before To by
  `(sequence, id)`. `from_label` shows the work order name or "Start" (list).
- Flow is To-first: `_onchange_to_workorder_id` sets From to the previous
  work order (empty for the first one). It is defined **before**
  `_onchange_default_move_qty` so shift / `move_qty` see the new From. From
  stays editable afterwards (domain `allowed_from_workorder_ids` = work
  orders before To); `allowed_to_workorder_ids` is all work orders of the MO.
- `previous_qty` = 0 when From is empty (Start), otherwise the remaining
  upstream quantity. `available_qty` is always `_get_remaining_qty()` — the
  real cap used by `_check_move_qty` and the `move_qty` default (see
  *Available quantity*).
- `routing_progress` (Json, not stored) feeds the `ps_mfg_workorder_stepper`
  widget (`static/src/components/workorder_stepper`): Start → WO1 (done/MO qty)
  → … ; highlights From / To; clicking a step sets To while editable.
- MO form, Work Orders tab: button `action_create_workorder_move` opens the
  shift form with work center / MO / To prefilled (defaults do not trigger
  onchange, so `move_qty` and `shift` keep their field defaults).

## Stock flow

```
NVL warehouse --[component pick: internal picking]--> workshop (workcenter.location_id)
workshop     --[workorder move Complete: consumption stock.move, no picking]--> Production (usage=production)
```

Complete is a **consumption issue** (xuất tiêu hao), like `mrp`
`move_raw_ids`: not an internal transfer.

- Line `location_id` (component + extra) is related
  `workorder_move_id.workcenter_id.location_id` (workshop). Do **not**
  search `proposal.source_location_id` (NVL warehouse): materials already
  sit at the work center after the component proposal.
- Complete (`action_approve`) snapshots prices and the transferred-in
  unit cost, then `_create_and_done_consumption_moves`: one `stock.move`
  per line, workshop → company Production, **no `picking_id` / no
  `picking_type_id`**, linked by `stock.move.ps_workorder_move_id`
  (`consumption_move_ids`). `_action_confirm` → lots / quantity →
  `picked` → `_action_done`. Idempotent: skip if consumption moves (or
  legacy `picking_ids`) exist. Skip when no positive `actual_qty`.
- Shift smart button **Stock Moves** (`action_view_stock_moves`) opens
  `stock.move.line` in `stock.view_move_line_tree` (the Moves History view),
  domain `move_id.ps_workorder_move_id`, same as mrp **Product Moves**
  (`mrp.action_mrp_production_moves`). There is
  no consumption tab/button on the work order (removed as redundant).
- No picking → core leaves `stock.move.reference` empty. `stock_move.py`
  overrides `_compute_reference`: moves with `ps_workorder_move_id` use the
  shift code `_consumption_origin()` (`MO/WO code/shift`), so Moves History /
  Moves Analysis show and search it (move line `reference` is related).
  The shift `display_name` is the same code. `action_open_reference` on the
  move (and so on its move lines) opens the shift form, so clicking a row in
  Moves History goes back to the shift.
- `picking_ids` is legacy (shifts completed before 19.0.0.9 through an
  internal picking). Read-only, button hidden when empty. Don't create new
  ones.
- Destination must be `usage='production'` so the move is OUT: workshop
  quants decrease and `ps_stock.onhand` counts issued. Internal→internal
  keeps NVL inside company inventory and double-counts vs WIP.
- Odoo 19 has **no** xmlid `stock.location_production`. Resolve via
  `product.template.with_company(...).default_get(['property_stock_production'])`,
  fallback search `usage='production'`.
- Storable shortfall at the workshop: `UserError`, state stays
  draft/pending. Non-storable products still get moves; no quant check.
- Tracked components (`product.tracking` lot/serial): Complete requires
  `ps.mfg.workorder.move.lot` rows whose qty sums to `actual_qty`. Each
  row becomes a `stock.move.line` with `lot_id`. Do **not** create lots
  at consume — pick lots already on workshop quants (proposal picking).
  Serial: qty 1, unique on the shift. Untracked lines stay as before.
- No un-approve. Reject / reset-to-draft does **not** reverse a done
  picking.

Workorder move is **not** an internal transfer between workshops. Every
operation on one MO shares the same workshop warehouse.

## Available quantity (material-gated)

`previous_qty` / `_get_remaining_qty` come from `_get_available_qty`,
gated by the effective component request (YCCP, not cancelled) through
`ps.mfg.component.request._get_producible_qty(to_workorder)`:

- YCCP draft / pending → **0** (no material issued yet). Only
  approved / done requests unlock quantity.
- `legacy_transfer` YCCP → full `product_qty`.
- Otherwise `product_qty × min(qty_transferred / qty_planned)` over the
  YCCP lines of that work order (lines without `workorder_id` belong to the
  first WO). Only `is_from_bom` lines count; manual non-BoM lines never
  block a work order (record them as Extra Components on the shift).
- First WO (no `from`): the material figure above. Later WO:
  `min(approved upstream output, material figure)`.
- Shift component lines are still scaled from the BoM, not copied from
  YCCP lines.

## One price: `product.standard_price`

Odoo OUT sets `stock.move.value = standard_price × qty`. Line `amount`
must use the same source.

- `price_unit` is readonly. On Complete, `_refresh_line_prices` writes
  `product.with_company(company).standard_price`. Extra-line `write`
  pops `price_unit` unless context `ps_mfg_refresh_price`.
- Do **not** reintroduce `_get_warehouse_price` / `force_cost_method`.
  `standard_price` is already company-dependent; warehouse cost method
  only changes the `_set_value` formula, not the stored unit price.
- `ps_stock.onhand.issued_amount` is period-average (VAS 02, report),
  not the document unit price.

WIP closing still reads `amount_total` on the workorder move.

## Costing (cumulative)

Per shift (all stored):

| Field | Rule |
|---|---|
| `material_amount` / `extra_amount` | Sum of BoM / extra line `amount`. |
| `amount_total` | material + extra. **WIP reads this** — keep its meaning. |
| `resource_line_ids` | `ps.mfg.workorder.move.resource`. Defaults from `to_workorder_id.resource_ids` (`planned_cost`, `actual_cost = planned`); user enters actual per shift. Locked when approved. |
| `resource_amount` | Sum of resource `actual_cost`. |
| `stage_cost` / `stage_unit_cost` | Own operation cost = `amount_total + resource_amount` (and / `move_qty`). |
| `transferred_in_unit_cost` | `from_workorder_id.unit_cost` (0 for the first WO). Compute depends **only** on `production_id`, `from_workorder_id`, and is re-snapshotted in `action_approve`. Approved shifts keep the price even when upstream gets new shifts. |
| `total_cost` / `unit_cost` | `transferred_in_unit_cost × move_qty + stage_cost` (and / `move_qty`). |

Per work order (`_compute_totals`, approved inbound shifts):
`total_amount` = own cost (material + resource from **shifts**;
`workorder.resource_ids` is only the plan), `transferred_in_cost`,
`total_cost`, `stage_unit_cost`, `unit_cost = total_cost / total_qty`.

`unit_cost` of the work order is the receipt price of finished goods
(`proposal.finish.line._get_finish_price_unit`, see
[`proposal-finish.md`](proposal-finish.md)).

Upgrade 19.0.0.9: `post-migrate` walks work orders in routing order and
sets `transferred_in_unit_cost` of old shifts from the upstream's current
unit cost (no historical snapshot existed). Old shifts have no resource
lines (`resource_amount = 0`).

## Shift

UNIQUE `(company_id, production_id, from_workorder_id, to_workorder_id, shift)`.

- **New record only:** onchange on `production_id` / `from_workorder_id` /
  `to_workorder_id` sets `shift = max(same from→to) + 1` when
  `not rec._origin.id`. Field default is `1`.
- **Existing record:** never rewrite `shift` on save / onchange. User may
  still edit it while draft.
- Do not put `shift` in that onchange trigger (assigning it would re-fire).
- `_get_next_shift` and `_get_remaining_qty` exclude the current row via
  `self._origin.id`. Form onchange wraps the row in `NewId`;
  `isinstance(self.id, int)` misses it and used to increment shift on
  every save.

## Lot / serial

Lots are recorded on the **shift** (`ps.mfg.workorder.move.lot`), not on
the work-order header. `ps.mfg.workorder.consumed_lot_ids` is the union
of lots from approved inbound shifts (display only).

UI matches Inventory Operations: pick lots as `many2many_tags` on the
Components / Extra Components lists (`lot_ids`, no create). Split qty
per lot in the Details popup (`action_show_lot_details`). There is no
separate Lot/Serial tab. Tags and Details hide when
`tracking not in ('lot', 'serial')`; the column hides when the shift has
no tracked components. Both tags and Details only list lots with
available quantity (`quantity - reserved > 0`) at the workshop
(`workcenter.location_id`); lots at NVL or other locations stay hidden.

- Parent XOR: a lot row belongs to a BoM component line **or** an extra
  line.
- BoM line with `tracking == 'lot'` seeds one lot row (`qty = planned`,
  empty `lot_id`). Serial is not seeded.
- Writing `lot_ids` inverse (`_set_lot_ids`): serial creates qty=1 rows
  and sets `actual_qty` to the serial count; lot keeps existing qty per
  kept lot and dumps remaining `actual_qty` on the first new lot.
- Complete checks qty match, then availability per `(product, lot)` at
  the workshop (`strict=True`). Missing lot / short lot qty →
  `UserError`, no picking.
- After `_action_confirm`, match each consume line to a `stock.move` by
  product + qty, unlink reservation sml, and create `stock.move.line`
  with `lot_id` (done must not see an sml without a lot).

## Out of scope (do not "fix" unless asked)

- `mfg_proposal.py` (NVL proposal; warehouse assigns lots on the draft
  NVL→workshop picking).
- Finished goods receipt (Production → stock moves, lots via the Odoo
  Details popup): see [`proposal-finish.md`](proposal-finish.md).
- Auto-FIFO when the user leaves lot rows empty.
- Creating lots at consume.
- Work-center master (no extra hidden location).
- `workcenter.expense_account_id` / `wip_account_id` are unused; Complete
  does not post consume to WIP accounts.

## Tests / upgrade

`TestMfgWorkOrderMove`: workshop location (not proposal NVL), consumption
moves workshop → Production without picking, resource defaults, cumulative
cost snapshot, work center ↔ MO constraint, `line.amount == stock.move.value`, shift
defaults only on new records, lot/serial consume writes `move_line.lot_id`
and decreases that lot's workshop quant. Inline `lot_ids` inverse (lot
and serial, extra line) writes `lot_line_ids`; the shift form has no
Lot/Serial tab. `allowed_lot_ids` is only lots with available qty at the
workshop (not other locations, not zero leftover quants).

After pulling: `-u ps_mfg` on the target DB, then reload the form.
