# Patsoft Stock

Inventory foundation module for the PatSoft suite. It enforces the required
stock configuration at install time and adds automatic, unique product codes
(`x_product_code`) generated from per-category sequences.

Users can attach a dedicated sequence to each `product.category` (built with
the segment prefix builder from `ps_sequence`) and every product automatically
receives a unique code on creation, with a per-company fallback sequence for
categories without their own sequence.

## Depends on

- `base` (via `ps_sequence`)
- `ps_sequence`
- `web`
- `stock`

## Related modules

- `ps_sequence` — provides the segment-based prefix builder and sequence
  preview used by category product-code sequences.
- `ps_purchase` — downstream purchasing module built on top of this stock
  foundation.

## Installation notes

A `post_init_hook` enables the required stock settings (lots, variants, UoM,
multi-locations, owner tracking, reception report) and backfills
`x_product_code` on all pre-existing products. Migrations 19.0.0.0.2 and
19.0.0.0.3 re-run the backfill in their own cursors.

See [doc/index.md](doc/index.md) for detailed documentation, including
[Odoo 19 Community AVCO](doc/odoo19_avco.md).
