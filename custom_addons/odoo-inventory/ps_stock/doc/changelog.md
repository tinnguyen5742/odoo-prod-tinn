# Changelog

## 19.0.0.4

- Remove the standalone code-prefix menu; the prefix builder is now
  integrated into the `ir.sequence` form via `ps_sequence`.
- Fix and harden the product-code uniqueness constraint (per-company check).
- Add index on `x_product_code` for faster lookup.
- Show `x_product_code` as a column in the product list view.
- Add Vietnamese (vi_VN) translations.

## 19.0.0.0.3

- Re-run the `x_product_code` backfill migration to cover databases that
  never ran 19.0.0.0.2 and products created without a code in the meantime.
- Extract the sequence prefix-builder extension into the separate
  `ps_sequence` module (`ps_ir_sequence_format` renamed).

## 19.0.0.0.2

- Post-migration backfill of `x_product_code` on historical products that
  predate the field, committed in an independent cursor.
- Allow composing sequence prefixes with the segment builder.

## 19.0.0.0.1

- Initial release.
- `x_product_code` on `product.product` with per-company uniqueness
  constraint.
- Category-level code sequences (`product.category.x_code_sequence_id`)
  with a "Create Sequence" action and sequence preview.
- Default `product.product.code.default` sequence per company.
- `post_init_hook` enforcing required stock settings and backfilling
  product codes.
