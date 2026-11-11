# AGENTS.md — ps_mfg

PatSoft Manufacturing module. Versioned BoMs with variant support,
routings, resources, cost items. Core reference: `mrp/mrp_bom.py`,
`mrp/mrp_bom_views.xml`, `mrp/mrp_routing_views.xml` (Odoo 19).

Full context: [`doc/specs/bom.md`](doc/specs/bom.md).
Workorder move (workshop consume / price / shift): [`doc/specs/workorder-move.md`](doc/specs/workorder-move.md).
Proposal finish (FG/scrap receipt, lots, WIP): [`doc/specs/proposal-finish.md`](doc/specs/proposal-finish.md).
Component pick (pick by source location, replaces material proposal): [`doc/specs/component-pick.md`](doc/specs/component-pick.md).
Status vocabulary (approval documents, `ps_approval` alignment): [`doc/specs/status-vocabulary.md`](doc/specs/status-vocabulary.md).

## Scope rules

- BoM `version >= 1`; v0 means "no BoM" and is never stored.
- Unique: BoM on `(product_tmpl_id, product_id, version, company_id)`;
  routing on `(bom_id, operation_id)`; operation on `(code, company_id)`.
- Operations (công đoạn) are a shared master `ps.mfg.operation` reused by
  many BoMs. `ps.mfg.routing` is only the BoM line (sequence, variants,
  enabled); its `name` / `resource_ids` are related to the operation.
  Resources / costs live on the operation only.
- Deliberately NOT ported from core: byproducts, BoM `type`,
  `picking_type_id`, `consumption`, lead times, `active` (we use
  `enabled`), chatter / catalog / attachments. Don't re-add without
  asking.
- `sequence` on BoM header is ordering-only (no form field).
  `sequence` on lines / routings drives drag handles.

## Odoo 19 view rules (hard-won, don't regress)

1. No bare `<field name="version"/>` in `<search>`.
2. Search `<group>` must be bare — no `expand` / `string` attrs.
3. `column_invisible="parent.xxx"` only inside One2many subviews.
   Standalone lists must never carry it.
4. Routing action pins `view_id`; BoM sublist stays at `priority=100`.

## Workflow

- After any XML/model edit: `-u ps_mfg` + browser hard-refresh before
  debugging. Stale `ir_ui_view` arch mimics code bugs.
- Variant UI requires the Inventory Variants setting
  (`product.group_product_variant`); invisible otherwise, by design.
- Before touching UNIQUE constraints, run the dupe-check SQL in
  `doc/specs/bom.md`.
