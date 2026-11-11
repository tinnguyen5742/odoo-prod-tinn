# Segment Format Builder

The module adds the following fields to `ir.sequence`:

- `x_use_segment_format` (Boolean): toggles segment-driven mode.
- `x_format_line_ids` (One2many → `ps.sequence.format`): the segment lines
  that compose the prefix.
- `x_sequence_preview` (Char, computed): rendered preview of the next value,
  e.g. `PR202608000001`.

## Behaviour

When `x_use_segment_format` is enabled:

- The standard `prefix` field becomes read-only in the form view.
- `prefix` is automatically recomputed and written whenever a segment line is
  created, updated, deleted, or when the `padding` changes.
- Saving a sequence with the flag on but no segment line raises a
  `ValidationError`.

## Segment line model: `ps.sequence.format`

- `segment_number` (Integer): ordering key, shown with a drag handle in the
  list.
- `type` (Selection): `constant`, `year_with_cent`, `year_no_cent`, `month`,
  `day`, `day_of_year`, `week`, `day_of_week`, `hour24`, `hour12`, `minute`,
  `second`.
- `value` (Char): required when `type == 'constant'`, must be empty otherwise.
- `sequence_id` (Many2one → `ir.sequence`, ondelete cascade).

## Token mapping

Each non-constant `type` maps to an `ir.sequence` interpolation token:

| Type             | Token            |
|------------------|------------------|
| `year_with_cent` | `%(year)s`       |
| `year_no_cent`   | `%(y)s`          |
| `month`          | `%(month)s`      |
| `day`            | `%(day)s`        |
| `day_of_year`    | `%(doy)s`        |
| `week`           | `%(woy)s`        |
| `day_of_week`    | `%(weekday)s`    |
| `hour24`         | `%(h24)s`        |
| `hour12`         | `%(h12)s`        |
| `minute`         | `%(min)s`        |
| `second`         | `%(sec)s`        |

## View

Inherits `base.sequence_view` and adds:

- a "Segment Format" group below the header containing the toggle and the live
  preview;
- a "Segment Format Builder" notebook page, visible only when the toggle is on,
  with an editable list of segment lines.

## Consumers

- `ps_stock` — uses this module to build product-code sequences per
  `product.category`.
