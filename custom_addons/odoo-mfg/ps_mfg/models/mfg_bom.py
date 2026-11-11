from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class PsMfgBom(models.Model):
    _name = "ps.mfg.bom"
    _description = "Ps Manufacturing Bill of Materials"
    _check_company_auto = True
    _inherit = ["mail.thread"]

    def _get_default_product_uom_id(self):
        return self.env["uom.uom"].search([], limit=1, order="id").id

    company_id = fields.Many2one(
        "res.company", "Company", required=True, default=lambda self: self.env.company
    )
    code = fields.Char(string="Reference", tracking=True)
    version = fields.Integer(string="Version", required=True, default=1, tracking=True)
    product_tmpl_id = fields.Many2one(
        "product.template",
        "Product",
        check_company=True,
        index=True,
        tracking=True,
        domain="[('type', '=', 'consu')]",
        required=True,
    )
    product_id = fields.Many2one(
        "product.product",
        "Product Variant",
        check_company=True,
        index=True,
        tracking=True,
        domain="['&', ('product_tmpl_id', '=', product_tmpl_id), ('type', '=', 'consu')]",
        help="If a product variant is defined the BOM is available only for this product.",
    )
    product_qty = fields.Float(
        string="Quantity", required=True, default=1.0, tracking=True
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        "Unit of Measure",
        required=True,
        default=_get_default_product_uom_id,
        help="Unit of measure used for the components of the BOM. "
        "It is used to compute the quantity of components needed to produce a finished product.",
    )
    enabled = fields.Boolean(string="Enabled", default=True, tracking=True)
    sequence = fields.Integer("Sequence")
    bom_line_ids = fields.One2many("ps.mfg.bom.line", "bom_id", "Components", copy=True)
    operation_ids = fields.One2many("ps.mfg.routing", "bom_id", "Operations", copy=True)
    possible_product_template_attribute_value_ids = fields.Many2many(
        "product.template.attribute.value",
        compute="_compute_possible_product_template_attribute_value_ids",
    )

    _ps_mfg_bom_version_unique = models.Constraint(
        "UNIQUE(product_tmpl_id, product_id, version, company_id)",
        _("BOM version must be unique"),
    )

    @api.constrains("version")
    def _check_version(self):
        for bom in self:
            if bom.version < 1:
                raise ValidationError(
                    _(
                        "BoM version must be at least 1. Version 0 means the component has no BoM."
                    )
                )

    def _compute_display_name(self):
        for bom in self:
            base = bom.code or bom.product_tmpl_id.display_name or _("BoM")
            if bom.product_id:
                base = "%s [%s]" % (base, bom.product_id.display_name)
            bom.display_name = "%s v%s" % (base, bom.version)

    @api.depends(
        "product_tmpl_id.attribute_line_ids.value_ids",
        "product_tmpl_id.attribute_line_ids.attribute_id.create_variant",
        "product_tmpl_id.attribute_line_ids.product_template_value_ids.ptav_active",
    )
    def _compute_possible_product_template_attribute_value_ids(self):
        for bom in self:
            bom.possible_product_template_attribute_value_ids = bom.product_tmpl_id.valid_product_template_attribute_line_ids.product_template_value_ids._only_active()

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            warning = (
                self.bom_line_ids.bom_product_template_attribute_value_ids
                or self.operation_ids.bom_product_template_attribute_value_ids
            ) and {
                "warning": {
                    "title": _("Warning"),
                    "message": _(
                        "Changing the product or variant will permanently reset all previously encoded variant-related data."
                    ),
                }
            }
            self.bom_line_ids.bom_product_template_attribute_value_ids = False
            self.operation_ids.bom_product_template_attribute_value_ids = False
            if warning:
                return warning

    @api.constrains("product_id", "product_tmpl_id", "bom_line_ids", "operation_ids")
    def _check_bom_lines(self):
        for bom in self:
            # Staged creation: an empty draft (no lines, no operations) and an
            # operations-first draft (operations but no lines yet) are allowed
            # as intermediate steps. A line can never exist without an
            # operation because a new line cannot reference a sibling operation
            # created in the same write (chicken-and-egg on unsaved records),
            # so the UI flow is: save operations first, then add components.
            if not bom.bom_line_ids:
                continue
            if not bom.operation_ids:
                raise ValidationError(
                    _(
                        "A BoM with components must have at least one operation. Add an operation first, then link each component to it."
                    )
                )
            for line in bom.bom_line_ids:
                if not line.operation_id:
                    raise ValidationError(
                        _(
                            "Component %(component)s must belong to an operation.",
                            component=line.product_id.display_name,
                        )
                    )
                if line.operation_id.bom_id != bom:
                    raise ValidationError(
                        _(
                            "Component %(component)s belongs to an operation of another BoM.",
                            component=line.product_id.display_name,
                        )
                    )
            apply_variants = (
                bom.bom_line_ids.bom_product_template_attribute_value_ids
                | bom.operation_ids.bom_product_template_attribute_value_ids
            )
            if bom.product_id and apply_variants:
                raise ValidationError(
                    _(
                        "You cannot use the 'Apply on Variant' functionality and simultaneously create a BoM for a specific variant."
                    )
                )
            for ptav in apply_variants:
                if ptav.product_tmpl_id != bom.product_tmpl_id:
                    raise ValidationError(
                        _(
                            "The attribute value %(attribute)s set on product %(product)s does not match the BoM product %(bom_product)s.",
                            attribute=ptav.display_name,
                            product=ptav.product_tmpl_id.display_name,
                            bom_product=bom.product_tmpl_id.display_name,
                        )
                    )

    @api.constrains("enabled", "product_id", "product_tmpl_id", "bom_line_ids")
    def _check_bom_cycle(self):
        """Recursively verify that a BoM's components (through their own
        BoMs) never lead back to one of the BoM's finished products, i.e.
        that the product/BoM graph is acyclic. Raises ValidationError on a
        detected cycle."""
        subcomponents_dict = dict()

        def _check_cycle(components, finished_products):
            products_to_find = self.env["product.product"]
            for component in components:
                if component in finished_products:
                    names = finished_products.mapped("display_name")
                    raise ValidationError(
                        _(
                            "The current configuration is incorrect because it would create a cycle between these products: %s.",
                            ", ".join(names),
                        )
                    )
                if component not in subcomponents_dict:
                    products_to_find |= component
            bom_find_result = self._bom_find(products_to_find)
            for component in components:
                if component not in subcomponents_dict:
                    bom = bom_find_result[component]
                    subcomponents = bom.bom_line_ids.filtered(
                        lambda l: not l._skip_bom_line(component)
                    ).product_id
                    subcomponents_dict[component] = subcomponents
                subcomponents = subcomponents_dict[component]
                if subcomponents:
                    _check_cycle(subcomponents, finished_products | component)

        boms_to_check = self
        if self.bom_line_ids.product_id:
            boms_to_check |= self.search(
                Domain.OR(
                    self._bom_find_domain(product)
                    for product in self.bom_line_ids.product_id
                )
            )

        for bom in boms_to_check:
            if not bom.enabled:
                continue
            finished_products = (
                bom.product_id
                or bom.product_tmpl_id.with_context(
                    active_test=False
                ).product_variant_ids
            )
            if bom.bom_line_ids.bom_product_template_attribute_value_ids:
                grouped_by_components = defaultdict(lambda: self.env["product.product"])
                for finished in finished_products:
                    components = bom.bom_line_ids.filtered(
                        lambda l: not l._skip_bom_line(finished)
                    ).product_id
                    grouped_by_components[components] |= finished
                for components, finished in grouped_by_components.items():
                    _check_cycle(components, finished)
            else:
                _check_cycle(bom.bom_line_ids.product_id, finished_products)

    @api.onchange("product_tmpl_id")
    def onchange_product_tmpl_id(self):
        if not self.product_tmpl_id:
            return
        warning = (
            self.bom_line_ids.bom_product_template_attribute_value_ids
            or self.operation_ids.bom_product_template_attribute_value_ids
        ) and {
            "warning": {
                "title": _("Warning"),
                "message": _(
                    "Changing the product or variant will permanently reset all previously encoded variant-related data."
                ),
            }
        }
        default_uom_id = self.env.context.get("default_product_uom_id")
        if self.product_uom_id.id != default_uom_id:
            self.product_uom_id = self.product_tmpl_id.uom_id.id
        if self.product_id.product_tmpl_id != self.product_tmpl_id:
            self.product_id = False
        self.bom_line_ids.bom_product_template_attribute_value_ids = False
        self.operation_ids.bom_product_template_attribute_value_ids = False

        domain = [("product_tmpl_id", "=", self.product_tmpl_id.id)]
        origin = getattr(self.id, "origin", False) or False
        record_id = origin or (self.id if isinstance(self.id, int) else False)
        if record_id:
            domain.append(("id", "!=", record_id))
        number_of_bom_of_this_product = self.env["ps.mfg.bom"].search_count(domain)
        if number_of_bom_of_this_product:
            self.code = _(
                "%(product_name)s (new) %(number_of_boms)s",
                product_name=self.product_tmpl_id.name,
                number_of_boms=number_of_bom_of_this_product,
            )
        if warning:
            return warning

    @api.model_create_multi
    def create(self, vals_list):
        # Process operations before lines so a same-save line can reference a
        # same-save operation (dict order drives x2many creation order).
        for vals in vals_list:
            if "operation_ids" in vals and "bom_line_ids" in vals:
                ops = vals.pop("operation_ids")
                lines = vals.pop("bom_line_ids")
                vals["operation_ids"] = ops
                vals["bom_line_ids"] = lines
        return super().create(vals_list)

    def write(self, vals):
        if "operation_ids" in vals and "bom_line_ids" in vals:
            vals = dict(vals)
            ops = vals.pop("operation_ids")
            lines = vals.pop("bom_line_ids")
            vals["operation_ids"] = ops
            vals["bom_line_ids"] = lines
        # Sequence reordering changes which BoM is picked first by _bom_find
        # (its search order is sequence-based), so the cycle check must be
        # re-run once the full reorder batch has been written.
        res = super().write(vals)
        if "sequence" in vals and self and self[-1].id == list(self._prefetch_ids)[-1]:
            self.browse(self._prefetch_ids)._check_bom_cycle()
        return res

    def copy(self, default=None):
        """Duplicate the BoM keeping operations and components.

        ``super().copy()`` would copy lines with ``operation_id`` still
        pointing at the source BoM, tripping ``_check_bom_lines`` before any
        remap can run. So lines are excluded from the initial copy and
        re-created afterwards with ``operation_id`` remapped to the copied
        operations (matched by name, unique per BoM, with positional
        fallback). Components and operations are both kept so users can
        add/remove lines on the new version.
        """
        default = dict(default or {})
        if "bom_line_ids" in default:
            return super().copy(default)
        default["bom_line_ids"] = []
        new_boms = super().copy(default)
        for old_bom, new_bom in zip(self, new_boms):
            if not old_bom.bom_line_ids:
                continue
            old_ops = old_bom.operation_ids.sorted(key=lambda o: (o.sequence, o.id))
            new_ops = new_bom.operation_ids.sorted(key=lambda o: (o.sequence, o.id))
            new_by_name = {op.name: op for op in new_ops}
            mapping = {}
            for index, old_op in enumerate(old_ops):
                new_op = new_by_name.get(old_op.name)
                if not new_op and index < len(new_ops):
                    new_op = new_ops[index]
                if new_op:
                    mapping[old_op.id] = new_op
            commands = []
            for old_line in old_bom.bom_line_ids.sorted(
                key=lambda l: (l.sequence, l.id)
            ):
                new_op = mapping.get(old_line.operation_id.id)
                vals = old_line.copy_data(
                    default={"operation_id": new_op.id if new_op else False}
                )[0]
                vals.pop("bom_id", None)
                commands.append((0, 0, vals))
            if commands:
                # Single parent write so _check_bom_lines/_check_bom_cycle run
                # on the final state with already-remapped operations.
                new_bom.write({"bom_line_ids": commands})
        return new_boms

    @api.model
    def _skip_for_no_variant(
        self, product, bom_attribute_values, never_attribute_values=False
    ):
        """Return True if a BoM line/operation carrying ``bom_attribute_values``
        ("Apply on Variant") must be skipped for ``product``.

        Variant-creating attribute values must all match the variant. Lines
        restricted to ``no_variant`` attributes only apply when at least one of
        their attributes is also present in ``never_attribute_values``
        (attributes of a broader context, e.g. a sub-BoM line)."""
        no_variant_bom_attributes = bom_attribute_values.filtered(
            lambda av: av.attribute_id.create_variant == "no_variant"
        )
        other_attribute_valid = product._match_all_variant_values(
            bom_attribute_values - no_variant_bom_attributes
        )
        if not no_variant_bom_attributes:
            return not other_attribute_valid
        if not never_attribute_values:
            return True
        bom_values_by_attribute = no_variant_bom_attributes.grouped("attribute_id")
        never_values_by_attribute = never_attribute_values.grouped("attribute_id")
        if not any(
            never_att_id in no_variant_bom_attributes.attribute_id.ids
            for never_att_id in never_attribute_values.attribute_id.ids
        ):
            return True
        for attribute, values in bom_values_by_attribute.items():
            if never_values_by_attribute.get(attribute) and any(
                val.id in never_values_by_attribute[attribute].ids for val in values
            ):
                return not other_attribute_valid
        return True

    @api.model
    def _bom_find_domain(self, products, company_id=False, version=None, bom_id=False):
        """Build the search domain for BoMs applying to ``products``: an exact
        variant BoM when it exists, otherwise a template-level BoM, restricted
        to enabled BoMs and optionally to a version / specific BoM / company."""
        domain = (
            Domain("product_id", "in", products.ids)
            | (
                Domain("product_id", "=", False)
                & Domain(
                    "product_tmpl_id",
                    "in",
                    products.with_context(active_test=False).product_tmpl_id.ids,
                )
            )
        ) & Domain("enabled", "=", True)
        if version is not None:
            domain &= Domain("version", "=", version)
        if bom_id:
            bom = self.browse(bom_id) if isinstance(bom_id, int) else bom_id
            if bom.exists():
                domain &= Domain("id", "=", bom.id)
        if company_id or self.env.context.get("company_id"):
            domain &= Domain(
                "company_id",
                "in",
                [False, company_id or self.env.context.get("company_id")],
            )
        return domain

    @api.model
    def _bom_find(self, products, company_id=False, version=None, bom_id=False):
        """Return a dict mapping each product to the BoM to use (empty env when
        none). Variant-specific BoMs win over template-level ones; within that,
        the highest version first, then sequence. ``version`` pins a specific
        version, ``version == 0`` explicitly means "no BoM". ``bom_id`` forces
        that exact BoM (if it fits the product)."""
        bom_by_product = defaultdict(lambda: self.env["ps.mfg.bom"])
        products = products.filtered(lambda p: p.type != "service")
        if not products:
            return bom_by_product
        if version == 0:
            return bom_by_product
        if bom_id:
            bom = self.browse(bom_id) if isinstance(bom_id, int) else bom_id
            if bom.exists():
                for product in products.filtered(
                    lambda p: p.product_tmpl_id == bom.product_tmpl_id
                ):
                    if not bom.product_id or bom.product_id == product:
                        bom_by_product[product] = bom
            return bom_by_product
        domain = self._bom_find_domain(products, company_id=company_id, version=version)

        if len(products) == 1:
            order = (
                "sequence, product_id, id"
                if version is not None
                else "version desc, sequence, product_id, id"
            )
            bom = self.search(domain, order=order, limit=1)
            if bom:
                bom_by_product[products] = bom
            return bom_by_product

        boms = self.search(domain, order="version desc, sequence, product_id, id")
        bom_by_product_tmpl = defaultdict(lambda: self.env["ps.mfg.bom"])
        for bom in boms:
            if (
                bom.product_id
                and (bom.product_id.product_tmpl_id not in bom_by_product_tmpl)
                and (bom.product_id not in bom_by_product)
            ):
                bom_by_product[bom.product_id] = bom
            elif not bom.product_id and bom.product_tmpl_id not in bom_by_product_tmpl:
                bom_by_product_tmpl[bom.product_tmpl_id] = bom
        for product in products:
            if (
                product.product_tmpl_id in bom_by_product_tmpl
                and product not in bom_by_product
            ):
                bom_by_product[product] = bom_by_product_tmpl[product.product_tmpl_id]
        return bom_by_product

    def explode(self, product, quantity):
        """Fully flatten this BoM for producing ``quantity`` of ``product``.

        Walks the multi-level BoM tree breadth-first, resolving each component
        to its own BoM via ``_bom_find`` (lazy batch per new product found) and
        converting quantities through UoMs at each level.

        Returns ``(boms_done, lines_done)``: sub-BoM levels and, at the leaves,
        components without their own BoM, as ``(record, {qty, product,
        original_qty})`` tuples (leaves are rounded UP)."""
        product_ids = set()
        product_boms = {}

        def update_product_boms():
            products = self.env["product.product"].browse(product_ids)
            product_boms.update(self._bom_find(products, company_id=self.company_id.id))
            for prod in products:
                product_boms.setdefault(prod, self.env["ps.mfg.bom"])

        boms_done = [
            (self, {"qty": quantity, "product": product, "original_qty": quantity})
        ]
        lines_done = []
        bom_lines = []
        for bom_line in self.bom_line_ids:
            bom_lines.append((bom_line, product, quantity))
            product_ids.add(bom_line.product_id.id)
        update_product_boms()
        product_ids.clear()
        while bom_lines:
            current_line, current_product, current_qty = bom_lines[0]
            bom_lines = bom_lines[1:]
            if current_line._skip_bom_line(current_product):
                continue
            line_quantity = current_qty * current_line.quantity
            if current_line.product_id not in product_boms:
                update_product_boms()
                product_ids.clear()
            bom = product_boms.get(current_line.product_id)
            if bom:
                converted = current_line.product_uom_id._compute_quantity(
                    line_quantity / bom.product_qty, bom.product_uom_id, round=False
                )
                bom_lines = [
                    (line, current_line.product_id, converted)
                    for line in bom.bom_line_ids
                ] + bom_lines
                for bom_line in bom.bom_line_ids:
                    if bom_line.product_id not in product_boms:
                        product_ids.add(bom_line.product_id.id)
                boms_done.append(
                    (
                        bom,
                        {
                            "qty": converted,
                            "product": current_product,
                            "original_qty": quantity,
                        },
                    )
                )
            else:
                line_quantity = current_line.product_uom_id.round(
                    line_quantity, rounding_method="UP"
                )
                lines_done.append(
                    (
                        current_line,
                        {
                            "qty": line_quantity,
                            "product": current_product,
                            "original_qty": quantity,
                        },
                    )
                )
        return boms_done, lines_done

    def _compute_scaled_components(self, product_id, product_qty, product_uom=None):
        """Single-level BoM lines scaled for ``product_qty`` (pure BoM math).

        Converts ``product_qty`` to the BoM UoM (round=False), skips lines
        not applying to ``product_id``, and scales each line by
        ``qty * line.quantity / bom.product_qty``.
        Returns plain dicts: product_id, product_uom_id, qty_bom,
        qty_planned, operation_id, sequence. No MO/Request/WO dependency.
        """
        self.ensure_one()
        if not self.product_qty:
            return []
        from_uom = product_uom or self.product_uom_id
        qty_in_bom_uom = from_uom._compute_quantity(
            product_qty or 0.0, self.product_uom_id, round=False
        )
        vals_list = []
        for line in self.bom_line_ids:
            if line._skip_bom_line(product_id):
                continue
            vals_list.append(
                {
                    "product_id": line.product_id.id,
                    "product_uom_id": line.product_uom_id.id,
                    "qty_planned": qty_in_bom_uom * line.quantity / self.product_qty,
                    "qty_bom": line.quantity,
                    "operation_id": line.operation_id.id,
                    "sequence": line.sequence,
                }
            )
        return vals_list

    def action_new_version(self):
        self.ensure_one()
        new_bom = self.copy(
            {
                "version": self.version + 1,
                "code": _("%s v%s")
                % (self.code or self.product_tmpl_id.name, self.version + 1),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "ps.mfg.bom",
            "res_id": new_bom.id,
            "view_mode": "form",
            "target": "current",
        }


class PsMfgBomLine(models.Model):
    _name = "ps.mfg.bom.line"
    _description = "Ps Manufacturing Bill of Materials Line"
    _order = "sequence, id"
    _check_company_auto = True

    def _get_default_product_uom_id(self):
        return self.env["uom.uom"].search([], limit=1, order="id").id

    bom_id = fields.Many2one(
        "ps.mfg.bom", "Parent BoM", required=True, ondelete="cascade"
    )
    parent_product_tmpl_id = fields.Many2one(
        "product.template", "Parent Product Template", related="bom_id.product_tmpl_id"
    )
    product_id = fields.Many2one(
        "product.product", "Component", required=True, check_company=True, index=True
    )
    product_tmpl_id = fields.Many2one(
        "product.template",
        "Product Template",
        related="product_id.product_tmpl_id",
        store=True,
        index=True,
    )
    possible_bom_product_template_attribute_value_ids = fields.Many2many(
        related="bom_id.possible_product_template_attribute_value_ids"
    )
    bom_product_template_attribute_value_ids = fields.Many2many(
        "product.template.attribute.value",
        string="Apply on Variants",
        ondelete="restrict",
        domain="[('id', 'in', possible_bom_product_template_attribute_value_ids)]",
        help="BOM Product Variants needed to apply this line.",
    )
    bom_version_id = fields.Many2one(
        "ps.mfg.bom",
        "BoM Version",
        required=False,
        domain="[('product_tmpl_id', '=', product_tmpl_id), ('enabled', '=', True), ('version', '>=', 1)]",
    )
    quantity = fields.Float(string="Quantity", required=True, default=1.0)
    product_uom_id = fields.Many2one(
        "uom.uom", string="Unit", required=True, default=_get_default_product_uom_id
    )
    sequence = fields.Integer(
        "Sequence", default=1, help="Gives the sequence order when displaying."
    )
    allowed_operation_ids = fields.One2many(
        "ps.mfg.routing", related="bom_id.operation_ids"
    )
    operation_id = fields.Many2one(
        "ps.mfg.routing",
        "Consumed in Operation",
        check_company=True,
        ondelete="restrict",
        domain="[('bom_id', '=', bom_id)]",
        help="The operation where the components are consumed, or the finished products created.",
    )
    child_bom_id = fields.Many2one(
        "ps.mfg.bom", "Sub BoM", compute="_compute_child_bom_id"
    )
    child_line_ids = fields.One2many(
        "ps.mfg.bom.line",
        string="BOM lines of the referred bom",
        compute="_compute_child_line_ids",
    )

    @api.constrains("bom_version_id", "product_tmpl_id")
    def _check_bom_version(self):
        """Validate the pinned sub-BoM version: it must belong to the line's
        component product/template, be version >= 1, and, if variant-specific,
        target exactly this component variant."""
        for line in self:
            if (
                line.bom_version_id
                and line.bom_version_id.product_tmpl_id != line.product_tmpl_id
            ):
                raise ValidationError(
                    _("Pinned BoM version must belong to the component product.")
                )
            if line.bom_version_id and line.bom_version_id.version < 1:
                raise ValidationError(_("Pinned BoM version must be at least 1."))
            if (
                line.bom_version_id
                and line.bom_version_id.product_id
                and line.bom_version_id.product_id != line.product_id
            ):
                raise ValidationError(
                    _("Pinned BoM version is for a different product variant.")
                )

    def _skip_bom_line(self, product, never_attribute_values=False):
        """Return True when this line does not apply to ``product`` because of
        its "Apply on Variant" attribute values (variant-BoM only case passes
        through). Delegates to ``ps.mfg.bom._skip_for_no_variant``."""
        self.ensure_one()
        if not product or product._name == "product.template":
            return False
        return self.env["ps.mfg.bom"]._skip_for_no_variant(
            product,
            self.bom_product_template_attribute_value_ids,
            never_attribute_values,
        )

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id.id
            if not line.operation_id and len(line.allowed_operation_ids) == 1:
                line.operation_id = line.allowed_operation_ids
            if (
                line.bom_version_id
                and line.bom_version_id.product_tmpl_id != line.product_tmpl_id
            ):
                line.bom_version_id = False
            if line.product_tmpl_id:
                latest = (
                    self.env["ps.mfg.bom"]
                    ._bom_find(line.product_id)
                    .get(line.product_id, False)
                )
                line.bom_version_id = latest or False
            else:
                line.bom_version_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if "product_id" in values and "product_uom_id" not in values:
                values["product_uom_id"] = (
                    self.env["product.product"].browse(values["product_id"]).uom_id.id
                )
        return super().create(vals_list)

    @api.depends("product_id", "bom_version_id", "bom_id")
    def _compute_child_bom_id(self):
        """Resolve the sub-BoM of this component line: the pinned version when
        set, otherwise the best match found by ``_bom_find``."""
        for line in self:
            if line.bom_version_id:
                line.child_bom_id = line.bom_version_id
            elif not line.product_id:
                line.child_bom_id = False
            else:
                line.child_bom_id = (
                    self.env["ps.mfg.bom"]
                    ._bom_find(line.product_id)
                    .get(line.product_id, False)
                )

    @api.depends("child_bom_id")
    def _compute_child_line_ids(self):
        for line in self:
            line.child_line_ids = line.child_bom_id.bom_line_ids.ids or False
