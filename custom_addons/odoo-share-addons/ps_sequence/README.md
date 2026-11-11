# Patsoft IR Sequence Format

Function module that extends `ir.sequence` with a segment-based prefix builder.

Users compose the sequence prefix from ordered segment lines (constant text or
date/time tokens) instead of typing a raw prefix string. A live preview of the
next value is shown on the `ir.sequence` form.

## Depends on

- `base`

## Consumers

- `ps_stock` — product-code sequences per `product.category`.

See [doc/index.md](doc/index.md) for detailed documentation.
