# Product Code Generation

Every product automatically receives a unique code in the `x_product_code`
field. The code is readonly, not copied on duplicate, and indexed for fast
lookup.

## Fields added

### `product.product`

- `x_product_code` (Char, readonly, copy=False, index=True): the unique
  product code, generated from a sequence.

### `product.category`

- `x_code_sequence_id` (Many2one → `ir.sequence`): the sequence used to issue
  codes for products in this category. The domain restricts it to sequences
  with code `product.product.code.default`, and the context enables the
  segment prefix builder from `ps_sequence`.
- `x_sequence_preview` (Char, computed): preview of the next value the
  category sequence will produce.
- `action_create_product_code_sequence()` (button): creates a ready-to-use
  sequence named `Product Code - <category>` with a constant prefix taken
  from the first 3 uppercase characters of the category name
  (e.g. `Furniture` → `FUR`), padding 6, and segment format enabled. The
  button is visible only when no sequence is configured yet.

## Code resolution flow

On product creation (`create()` override in
`models/product_product.py`), the code is resolved as follows:

```text
create product
    -> category has x_code_sequence_id?
        yes -> next_by_id() of the category sequence
        no  -> _get_default_product_code_sequence(company)
                  -> next_by_id() of the company default sequence
```

- The category is taken from `categ_id`, or from the template's
  `categ_id` when only `product_tmpl_id` is passed.
- If the values already contain `x_product_code` (e.g. import or data
  file), the sequence is skipped.

## Default sequence

`data/ir_sequence.xml` creates the main-company fallback sequence
(noupdate=1):

- name: `PS Stock Default Product Code`
- code: `product.product.code.default`
- prefix: empty, padding: 8, implementation: `standard`

`_get_default_product_code_sequence(company_id)` lazily creates a per-company
clone of this sequence on first use, so each company keeps an independent
counter. The clone copies padding and implementation from the main-company
template when available.

## Uniqueness constraint

`_check_product_code()` enforces on every write:

- the code must not be empty;
- the code must be unique within the same company.

Violations raise a `ValidationError`.

## Backfill of historical products

`_action_assign_missing_product_codes()` assigns codes to every product
missing one:

- uses the category sequence when configured, otherwise the per-company
  default;
- issues codes one by one through `next_by_id()` so counters advance
  correctly;
- runs with `sudo()` and `active_test=False` so it can be invoked from the
  post-init hook and migration scripts regardless of the current user;
- logs per-product failures but does not abort the run; returns the number
  of products updated.

It is invoked from:

- the `post_init_hook` at install time (see [installation.md](installation.md));
- the `19.0.0.0.2` and `19.0.0.0.3` post-migration scripts, each running in
  an independent cursor so the backfill commits even if the upgrade
  transaction later fails.

## Views

- Product form (`product.product`): a readonly `Product Code` row shown
  directly under the `oe_title` block.
- Product list: an `x_product_code` column before `default_code`.
- Category form: a "Product" group with the sequence selector, a
  "Create Sequence" link button (when unset), and the sequence preview.
