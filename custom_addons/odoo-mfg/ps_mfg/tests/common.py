def get_component_source_location(env, workshop_location):
    """Kho NVL internal khác kho xưởng, dùng làm nguồn cho YCCP trong test."""
    return env["stock.location"].create(
        {
            "name": "Test Component Source",
            "usage": "internal",
            "location_id": (workshop_location.location_id.id or workshop_location.id),
        }
    )


def create_received_component_request(env, production, product_qty, source_location):
    """Tạo YCCP, duyệt và nhận đủ NVL về xưởng để WO move có SL khả dụng."""
    request = env["ps.mfg.component.request"].create(
        {
            "production_id": production.id,
            "product_qty": product_qty,
            "location_id": source_location.id,
        }
    )
    request.action_approve()
    lines = request.component_line_ids
    if lines:
        lines.action_create_pick_transfer()
        pickings = lines.move_ids.picking_id
        for move in pickings.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        pickings.button_validate()
    return request


def get_operation(env, name, company=None, resources=None):
    """Find or create the shared ``ps.mfg.operation`` named ``name``.

    ``resources``: optional list of ``(resource, cost)`` set on creation.
    """
    company = company or env.company
    operation_model = env["ps.mfg.operation"]
    operation = operation_model.search(
        [("name", "=", name), ("company_id", "=", company.id)], limit=1
    )
    if operation:
        return operation
    count = operation_model.search_count([("company_id", "=", company.id)])
    return operation_model.create(
        {
            "name": name,
            "code": f"TOP{count + 1:03d}",
            "company_id": company.id,
            "resource_ids": [
                (0, 0, {"resource_id": res.id, "resource_cost": cost})
                for res, cost in (resources or [])
            ],
        }
    )


def operation_line(env, name, sequence=1, company=None, resources=None):
    """x2many create command for a BoM operation line using a shared operation."""
    operation = get_operation(env, name, company=company, resources=resources)
    return (0, 0, {"operation_id": operation.id, "sequence": sequence})
