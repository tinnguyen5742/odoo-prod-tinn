# BoM — handover notes

Session notes for future work on `ps.mfg.bom` / `ps.mfg.bom.line` /
`ps.mfg.routing`. Ported from core `mrp.bom` with versioning added.

## Module state

- `ps.mfg.bom` (+ `ps.mfg.bom.line`) ported from core `mrp.bom`
  **with versioning**: `version >= 1` (v0 = "no BoM" sentinel, never
  stored), unique on `(product_tmpl_id, product_id, version, company_id)`.
- `_bom_find(products, company_id, version, bom_id)` resolves the latest
  enabled BoM (`version desc, sequence, product_id, id`) or a pinned
  version / exact record. Empty result = v0 leaf.
- Variant support ported: header `product_id`, per-line and per-operation
  Apply-on-Variants tags (`bom_product_template_attribute_value_ids`),
  `_skip_*` logic, variant-aware `_bom_find` and cycle check.
  **Requires** Inventory → Variants setting
  (`product.group_product_variant`); otherwise the variant UI stays hidden
  (by design, core parity).
- Deliberately **skipped**: byproducts, BoM `type` (normal/phantom),
  `picking_type_id`, `consumption`, lead times, `active` (we use
  `enabled`), chatter / catalog / attachments.
- Components pin a sub-BoM via optional `bom_version_id` (auto-defaults to
  latest, falls back to `_bom_find`); empty = v0 leaf.
- `sequence` on the BoM header is ordering-only (no form field, core
  parity); `sequence` on lines and routings drives drag handles.
  `ps.mfg.routing` gained `sequence` + `_order = 'sequence, id'`.
- Operations are a **shared master** `ps.mfg.operation` (code, name,
  description, enabled, company, resources), reused by many BoMs
  (since `19.0.0.12`). `ps.mfg.routing` is the BoM operation line:
  `bom_id` + `operation_id` + `sequence` + variant tags + `enabled`;
  `name` (stored) and `resource_ids` are related to the master, so editing
  a master's resources affects every BoM (MOs keep their WO snapshot).
- Uniqueness: routing `UNIQUE(bom_id, operation_id)` (was
  `UNIQUE(bom_id, name)`), operation `UNIQUE(code, company_id)`.
  `ondelete="restrict"`: an operation used by a BoM cannot be deleted.
- `ps.mfg.workorder.operation_id` (related, stored) allows grouping WOs by
  shared operation across BoMs.
- Migration `19.0.0.12/pre-migrate.py`: one operation per
  `(name, company_id)` of old routings (codes `OP001`…); resources of the
  oldest routing having resources are kept, the rest dropped, with a
  warning per operation whose BoMs had different resource sets.
- `action_new_version` copies the BoM with `version + 1` (both stay
  enabled); `copy()` remaps line `operation_id` to the copied operations.
- Operation codes are auto-generated from sequence
  `ps_mfg.seq_ps_mfg_operation` (`OP001`…, readonly in the form). `create()`
  skips codes already taken in the company (e.g. those created by the
  migration); `19.0.0.13/post-migrate.py` moves the sequence past them.

## Views

- `views/ps_mfg_bom_views.xml`: core-aligned list (handle,
  `sample`/`multi_edit`, optional columns) / form (no `oe_title`, qty
  `o_row` with `many2one_uom`, named pages, Components `<control>`,
  subform Operations) / kanban / search (code `filter_domain`, Component
  search, groupbys) / line-form popup / `list,kanban,form` action.
- Operations page = **inline editable** list via
  `list_view_ref: ps_mfg_routing_bom_list` (no dialog on row click), with a
  muted hint when empty. `operation_id` has no quick-create; "Create and
  edit…" opens the operation master form (full entry, auto code) and links
  the new operation to the row. The row button `action_open_routing` opens
  the BoM operation as a **full page** (breadcrumb back to the BoM).
- BoM operation page (`ps_mfg_routing_view_form`): operation + BoM as title,
  "Operation Catalog" smart button (`action_open_operation`), tabs
  Components (`bom_line_ids`, readonly), Resources (from the master,
  readonly) and Description (from the master).
- `views/ps_mfg_routing_views.xml`: standalone list pinned via `view_id`
  on the action; BoM sublist `ps_mfg_routing_bom_list` at `priority=100`
  (reachable only via `list_view_ref`, never auto-selected standalone).
- Menus: new **Products** menu → Bills of Materials; Configuration →
  **Operations** (shared master, `views/ps_mfg_operation_views.xml`)
  replaces the Routings menu (routing lines are edited inside the BoM).
- Access: user-read + manager-full rows for `ps.mfg.bom` and
  `ps.mfg.bom.line` in `security/ir.model.access.csv`.

## Odoo 19 view gotchas (don't regress)

1. No bare `<field name="version"/>` in `<search>` — the validator
   rejects it; use filters / groupbys instead.
2. Search `<group>` must be **bare** — `expand="0" string="Group By"` is
   invalid in 19 (see core `sale_order_views.xml`).
3. `column_invisible="parent.xxx"` is **only valid inside One2many
   subviews**; a standalone list carrying it crashes the OWL renderer
   (`Name 'parent' is not defined`). The action `view_id` pin + subview
   `priority=100` guard against serving the wrong arch.
4. After any XML edit: `-u ps_mfg` + browser hard-refresh; a stale
   `ir_ui_view` arch otherwise mimics a code bug.

## Pre-upgrade checks when touching UNIQUE constraints

```sql
SELECT bom_id, operation_id, COUNT(*) FROM ps_mfg_routing
GROUP BY bom_id, operation_id HAVING COUNT(*) > 1;
SELECT code, company_id, COUNT(*) FROM ps_mfg_operation
GROUP BY code, company_id HAVING COUNT(*) > 1;
SELECT product_tmpl_id, product_id, version, company_id, COUNT(*)
FROM ps_mfg_bom GROUP BY 1, 2, 3, 4 HAVING COUNT(*) > 1;
```

Both must return zero rows or constraint creation fails on upgrade.
Existing `version = 0` rows (if any) violate `_check_version` — bump to 1.

## Next steps

- `models/mfg_production.py` is an empty stub (`_name` only). Next
  workstream: MO model linking `bom_id` / `bom_version_id`, consumption
  via BoM `explode()`, outdated-BoM flagging (core
  `_set_outdated_bom_in_productions` not ported).

## BoM overview (web view)

- `report.ps.mfg.bom_structure` (`models/mfg_bom_overview_report.py`)
  serves the `ps_mfg_bom_overview` client action (OWL in
  `static/src/components/bom_overview/`, opened from the BoM form
  smart button). Pattern ported from
  `ps_mrp/models/mrp_report_bom_structure.py`, but standalone (no
  `mrp` dependency, no stock / forecast / costs).
- Per level: unassigned components first, then one group per
  operation (`1`, `2`, … with components `N.M`); sub-BoM headers show
  `vX`, leaves `v0`. All payload values are JSON primitives.
- Only the root BoM groups by operation; nested sub-BoMs list their
  components flat (no Operations section, no line codes), badges kept.
- Tests: `tests/test_bom_overview.py`.
