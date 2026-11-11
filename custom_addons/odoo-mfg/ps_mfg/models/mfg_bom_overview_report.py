from odoo import api, models


class PsMfgBomOverviewReport(models.AbstractModel):
    """BoM overview data provider for the ``ps_mfg_bom_overview`` web client
    action. Mirrors the approach of ``ps_mrp``'s
    ``report.mrp.report_bom_structure`` override (components grouped per
    parent operation, ``N`` / ``N.M`` line codes, sub-BoM versions), but is
    standalone: ``ps.mfg`` models carry no stock / workcenter / route data,
    so availability, costs, byproducts and attachments are intentionally out
    of scope. All values in the returned tree are JSON-safe primitives."""

    _name = "report.ps.mfg.bom_structure"
    _description = "ps.mfg BoM Overview"

    @api.model
    def get_html(self, bom_id=False, searchQty=1, searchVariant=False):
        bom = self.env["ps.mfg.bom"].browse(bom_id)
        if not bom.exists():
            return {"lines": False}
        if searchVariant:
            product = self.env["product.product"].browse(int(searchVariant))
        else:
            product = (
                bom.product_id
                or bom.product_tmpl_id.with_context(
                    active_test=False
                ).product_variant_ids[:1]
            )
        qty = searchQty or bom.product_qty or 1
        lines = self._get_bom_data(bom, product=product, line_qty=qty)
        variants = {}
        if not bom.product_id:
            for variant in bom.product_tmpl_id.with_context(
                active_test=False
            ).product_variant_ids:
                variants[variant.id] = variant.display_name
        return {
            "lines": lines,
            "variants": variants,
            "bom_uom_name": bom.product_uom_id.name,
            "bom_qty": qty,
            "is_variant_applied": self.env.user.has_group(
                "product.group_product_variant"
            )
            and len(variants) > 1,
            "is_uom_applied": self.env.user.has_group("uom.group_uom"),
            "precision": self.env["decimal.precision"].precision_get("Product Unit"),
        }

    @api.model
    def _get_bom_data(
        self,
        bom,
        product=False,
        line_qty=False,
        bom_line=False,
        level=0,
        index=0,
        visited=None,
    ):
        """Recursively build the overview tree for ``bom``.

        ``line_qty`` is the total units of this BoM to produce (in its UoM);
        each line scales as ``line_qty / bom.product_qty * line.quantity``.
        ``product`` is the finished product of this level (display + variant
        filtering of operations); lines are filtered against the immediate
        parent component (``bom_line.product_id``), like ``explode()``."""
        if line_qty is False:
            line_qty = bom.product_qty or 1.0
        if visited is None:
            visited = set()
        visited = visited | {bom.id}
        if not product:
            product = (
                bom.product_id
                or bom.product_tmpl_id.with_context(
                    active_test=False
                ).product_variant_ids[:1]
            )

        ratio = (line_qty or 0.0) / (bom.product_qty or 1.0)
        skip_product = bom_line.product_id if bom_line else product
        components = []
        for i, line in enumerate(
            bom.bom_line_ids.sorted(key=lambda l: (l.sequence, l.id))
        ):
            if skip_product and line._skip_bom_line(skip_product):
                continue
            child_index = f"{index}{i}"
            child = line.child_bom_id
            if child and child.id in visited:
                child = self.env["ps.mfg.bom"]
            if child:
                need_child = line.product_uom_id._compute_quantity(
                    ratio * line.quantity, child.product_uom_id, round=False
                )
                components.append(
                    self._get_bom_data(
                        child,
                        product=line.product_id,
                        line_qty=need_child,
                        bom_line=line,
                        level=level + 1,
                        index=child_index,
                        visited=visited,
                    )
                )
            else:
                components.append(
                    self._get_component_data(
                        line, ratio * line.quantity, level + 1, child_index
                    )
                )

        # Only the top-level BoM groups components by operation. Nested
        # sub-BoMs list their components flat (no Operations section).
        operations = []
        if level == 0:
            for i, operation in enumerate(
                bom.operation_ids.sorted(key=lambda o: (o.sequence, o.id))
            ):
                if product and operation._skip_routing(product):
                    continue
                operations.append(
                    {
                        "type": "operation",
                        "index": f"{index}{i}",
                        "level": level + 1,
                        "operation_id": operation.id,
                        "name": operation.display_name,
                        "link_id": operation.id,
                        "link_model": "ps.mfg.routing",
                        "line_code": False,
                    }
                )

        node = {
            "type": "bom",
            "index": index,
            "level": level,
            "bom_id": bom.id,
            "bom_version": bom.version,
            "bom_code": bom.code or False,
            "bom_line_id": bom_line.id if bom_line else False,
            "name": product.display_name
            if product
            else bom.product_tmpl_id.display_name,
            "product_id": product.id if product else False,
            "link_id": self._link_id(product, bom),
            "link_model": self._link_model(product),
            "quantity": line_qty,
            "uom_name": bom.product_uom_id.name,
            "code": bom.display_name,
            "operation_id": bom_line.operation_id.id
            if bom_line and bom_line.operation_id
            else False,
            "operation_name": bom_line.operation_id.display_name
            if bom_line and bom_line.operation_id
            else False,
            "operations": operations,
            "components": components,
            "line_code": False,
        }
        node["foldable"] = bool(operations) or bool(components)
        if level == 0:
            self._ps_group_components_by_operation(node)
            self._ps_assign_line_codes(node)
        return node

    @api.model
    def _get_component_data(self, bom_line, line_quantity, level, index):
        operation = bom_line.operation_id
        product = bom_line.product_id
        return {
            "type": "component",
            "index": index,
            "level": level,
            "bom_id": False,
            "bom_version": 0,
            "bom_line_id": bom_line.id,
            "product_id": product.id,
            "name": product.display_name,
            "link_id": self._link_id(product, False),
            "link_model": self._link_model(product),
            "quantity": line_quantity,
            "uom_name": bom_line.product_uom_id.name,
            "operation_id": operation.id if operation else False,
            "operation_name": operation.display_name if operation else False,
            "line_code": False,
        }

    @api.model
    def _link_id(self, product, bom):
        if not product:
            return bom.product_tmpl_id.id if bom else False
        if len(product.product_tmpl_id.product_variant_ids) > 1:
            return product.id
        return product.product_tmpl_id.id

    @api.model
    def _link_model(self, product):
        if product and len(product.product_tmpl_id.product_variant_ids) > 1:
            return "product.product"
        return "product.template"

    def _ps_group_components_by_operation(self, node):
        """Split node components into unassigned + per-operation lists.
        Sub-BoM headers (type 'bom') carry their parent bom_line's operation
        via 'operation_id'. (Ported from ps_mrp.)"""
        op_map = {op.get("operation_id"): op for op in node.get("operations") or []}
        unassigned = []
        for comp in node.get("components") or []:
            op = op_map.get(comp.get("operation_id"))
            if op is not None:
                op.setdefault("ps_components", []).append(comp)
            else:
                unassigned.append(comp)
        node["ps_unassigned_components"] = unassigned
        for component in node.get("components") or []:
            if component.get("type") == "bom":
                self._ps_group_components_by_operation(component)

    def _ps_assign_line_codes(self, node):
        """Number per operation group: operations get '1', '2', ... and each
        operation's components get 'N.M'. Unassigned components stay
        unnumbered. (Ported from ps_mrp.)"""
        for i, operation in enumerate(node.get("operations") or [], start=1):
            operation["line_code"] = str(i)
            for j, comp in enumerate(operation.get("ps_components") or [], start=1):
                comp["line_code"] = f"{i}.{j}"
        for component in node.get("components") or []:
            if component.get("type") == "bom":
                self._ps_assign_line_codes(component)
