# Installation & Configuration

## Dependencies

The manifest declares:

```python
'depends': ['ps_sequence', 'web', 'stock']
```

`ps_sequence` must be available in the addons path; it provides the
segment-based prefix builder used by category product-code sequences.

## post-init hook

At install time, `post_init_hook(env)` performs two tasks.

### 1. Enforce required stock settings

The hook creates a `res.config.settings` record and enables the following
options if they are not already on:

| Setting                        | Feature enabled                    |
|--------------------------------|------------------------------------|
| `group_stock_tracking_lot`     | Lots                               |
| `group_stock_production_lot`   | Production lots                    |
| `group_stock_reception_report` | Reception report                   |
| `group_product_variant`        | Product variants                   |
| `group_uom`                    | Units of measure                   |
| `group_stock_tracking_owner`   | Owner tracking                     |
| `group_stock_multi_locations`  | Multiple storage locations         |

- If any of these setting fields no longer exist in the installed Odoo
  version, installation aborts with a `UserError` listing the missing
  fields.
- Settings that are already enabled are left untouched.

### 2. Backfill product codes

The hook calls `product.product._action_assign_missing_product_codes()` to
assign `x_product_code` to all pre-existing products. See
[product_code.md](product_code.md#backfill-of-historical-products). Failures
during backfill are logged and do not roll back the installation.

## Migrations

- `migrations/19.0.0.0.2/post-migrate.py` — first backfill of codes for
  products that predate `x_product_code`. Runs in its own cursor so the
  backfill commits independently of the upgrade transaction.
- `migrations/19.0.0.0.3/post-migrate.py` — re-runs the backfill to cover
  databases that skipped 19.0.0.0.2 (fresh install of an older version then
  direct upgrade) and products created without a code in the meantime.

## Category sequence setup

For each product category that should have its own code range:

1. Open Inventory ▸ Configuration ▸ Product Categories (category form).
2. In the "Product" group, click **Create Sequence** — this builds a
   sequence with the category's 3-character prefix and segment format
   enabled.
3. Optionally refine the segment lines on the `ir.sequence` form (see the
   `ps_sequence` [Segment Format Builder](../../ps_sequence/doc/segment_format.md)).
4. New products in the category will now draw codes from this sequence.

Categories without a sequence fall back to the per-company default
sequence (padding 8).
