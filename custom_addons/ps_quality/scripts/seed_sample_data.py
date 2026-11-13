"""Create 30 clearly marked QMS sample records; safe to run more than once.

Run with:
    odoo shell -d admin < /mnt/extra-addons/ps_quality/scripts/seed_sample_data.py

The 30 counted QMS records are 5 standards, 5 plans, 10 inspections, 4 NCRs,
3 CAPAs, 2 measurement devices and 1 calibration. Supporting products,
partners and inspection criteria are created as linked sample data too.
"""

from datetime import timedelta

from odoo import api, fields


PREFIX = "[MẪU]"
MARKER = "ps_quality_sample_data_v1"
admin = env.ref("base.user_admin")
env = api.Environment(env.cr, admin.id, env.context)
company = env.company
today = fields.Date.context_today(env["ps.quality.standard"])
created = {"standard": 0, "plan": 0, "inspection": 0, "ncr": 0, "capa": 0, "equipment": 0, "calibration": 0}


def _find_by_name(model_name, name):
    return env[model_name].with_context(active_test=False).search(
        [("name", "=", name), ("company_id", "=", company.id)], limit=1
    )


def _sample_product(index):
    name = f"{PREFIX} QMS Product {index:02d}"
    template = env["product.template"].search(
        [("name", "=", name), ("company_id", "in", [company.id, False])], limit=1
    )
    return template.product_variant_id if template else env["product.template"].create(
        {"name": name, "company_id": company.id}
    ).product_variant_id


def _sample_partner(index):
    name = f"{PREFIX} QMS Supplier {index:02d}"
    partner = env["res.partner"].search([("name", "=", name)], limit=1)
    return partner or env["res.partner"].create({"name": name, "company_type": "company"})


products = [_sample_product(index) for index in range(1, 6)]
partners = [_sample_partner(index) for index in range(1, 5)]

# Five standards, each with numeric limits and a pass/fail check.
standards = []
for index, product in enumerate(products, start=1):
    name = f"{PREFIX} QMS Standard {index:02d} - {product.display_name}"
    standard = _find_by_name("ps.quality.standard", name)
    if not standard:
        standard = env["ps.quality.standard"].create(
            {"name": name, "product_id": product.id, "company_id": company.id}
        )
        env["ps.quality.standard.line"].create(
            [
                {
                    "standard_id": standard.id,
                    "name": "Critical dimension",
                    "criterion_type": "numeric",
                    "has_minimum": True,
                    "min_value": 9.5 + index / 10,
                    "has_maximum": True,
                    "max_value": 10.5 + index / 10,
                    "unit": "mm",
                    "method": "measure",
                    "instruction": "[MẪU] Check with a calibrated measuring instrument.",
                },
                {
                    "standard_id": standard.id,
                    "name": "Visual finish",
                    "criterion_type": "pass_fail",
                    "method": "visual",
                    "instruction": "[MẪU] No visible defects on the sample.",
                },
            ]
        )
        standard.action_activate()
        created["standard"] += 1
    standards.append(standard)

# Five active plans cover the three inspection stages and recurrence options.
inspection_types = ["iqc", "ipqc", "oqc", "iqc", "oqc"]
frequencies = ["per_receipt", "per_lot", "daily", "weekly", "monthly"]
plans = []
for index, standard in enumerate(standards, start=1):
    name = f"{PREFIX} QMS Plan {index:02d} - {inspection_types[index - 1].upper()}"
    plan = _find_by_name("ps.quality.plan", name)
    if not plan:
        values = {
            "name": name,
            "product_id": standard.product_id.id,
            "standard_id": standard.id,
            "inspection_type": inspection_types[index - 1],
            "frequency": frequencies[index - 1],
            "frequency_interval": index,
            "sample_size": 5,
            "inspector_id": admin.id,
            "company_id": company.id,
            "description": f"{MARKER} {PREFIX} training plan.",
        }
        if frequencies[index - 1] in ("daily", "weekly", "monthly"):
            values["next_date"] = today
        plan = env["ps.quality.plan"].create(values)
        plan.action_activate()
        created["plan"] += 1
    plans.append(plan)

# Ten completed inspection records: eight pass and two fail. Failed inspections
# automatically create two of the four NCRs counted below.
inspections = []
for index in range(1, 11):
    plan = plans[(index - 1) % len(plans)]
    marker = f"{MARKER}:inspection:{index:02d}"
    inspection = env["ps.quality.inspection"].search(
        [("description", "ilike", marker), ("company_id", "=", company.id)], limit=1
    )
    if not inspection:
        failed = index in (4, 9)
        inspection = env["ps.quality.inspection"].create(
            {
                "name": f"{PREFIX} QMS Inspection {index:02d}",
                "plan_id": plan.id,
                "standard_id": plan.standard_id.id,
                "product_id": plan.product_id.id,
                "partner_id": partners[(index - 1) % len(partners)].id,
                "inspection_type": plan.inspection_type,
                "inspector_id": admin.id,
                "inspection_date": today - timedelta(days=index),
                "planned_date": today - timedelta(days=index),
                "quantity_to_inspect": 20 + index,
                "quantity_sampled": 5,
                "quantity_passed": 4 if failed else 5,
                "quantity_failed": 1 if failed else 0,
                "disposition": "quarantine" if failed else "release",
                "company_id": company.id,
                "description": f"<p>{PREFIX} QMS training record; {marker}.</p>",
            }
        )
        inspection.action_confirm()
        inspection.action_start()
        for line in inspection.line_ids:
            if line.criterion_type == "numeric":
                observed = str(line.min_value - 1 if failed else (line.min_value + line.max_value) / 2)
                line.write({"observed_value": observed})
            else:
                line.write({"result": "pass", "observed_value": f"{PREFIX} visual check passed"})
        inspection.action_complete()
        if failed:
            ncr = inspection.ncr_ids[:1]
            ncr.write(
                {
                    "name": f"{PREFIX} QMS NCR {ncr.name}",
                    "title": f"{PREFIX} QMS NCR - {inspection.name}",
                    "description": f"<p>{MARKER} linked to sample inspection {inspection.name}.</p>",
                }
            )
            created["ncr"] += 1
        else:
            inspection.action_approve()
            inspection.action_close()
        created["inspection"] += 1
    inspections.append(inspection)

# Two additional sample NCRs; failed inspections above supply the other two.
ncrs = list(env["ps.quality.ncr"].search(
    [("title", "ilike", f"{PREFIX} QMS NCR -"), ("company_id", "=", company.id)],
    order="id",
))
for index in range(1, 3):
    title = f"{PREFIX} QMS NCR - Supplier / Customer Case {index:02d}"
    ncr = env["ps.quality.ncr"].search(
        [("title", "=", title), ("company_id", "=", company.id)], limit=1
    )
    if not ncr:
        ncr = env["ps.quality.ncr"].create(
            {
                "title": title,
                "source_type": "supplier" if index == 1 else "customer",
                "severity": "major" if index == 1 else "minor",
                "product_id": products[index - 1].id,
                "partner_id": partners[index - 1].id,
                "assigned_id": admin.id,
                "due_date": today + timedelta(days=7 * index),
                "company_id": company.id,
                "description": f"<p>{MARKER} training example. Not a real incident.</p>",
            }
        )
        created["ncr"] += 1
    ncrs.append(ncr)

# Three draft CAPAs linked to sample NCRs, with illustrative actions and due dates.
for index in range(1, 4):
    marker = f"{MARKER}:capa:{index:02d}"
    capa = env["ps.quality.capa"].search(
        [("description", "ilike", marker), ("company_id", "=", company.id)], limit=1
    )
    if not capa:
        capa = env["ps.quality.capa"].create(
            {
                "name": f"{PREFIX} QMS CAPA {index:02d}",
                "ncr_id": ncrs[index - 1].id,
                "action_type": ["corrective", "preventive", "both"][index - 1],
                "root_cause": f"<p>{PREFIX} Example root cause for training.</p>",
                "corrective_action": f"<p>{PREFIX} Example corrective action.</p>",
                "preventive_action": f"<p>{PREFIX} Example preventive action.</p>",
                "assigned_id": admin.id,
                "due_date": today + timedelta(days=14 + index),
                "company_id": company.id,
                "description": f"<p>{PREFIX} {marker}; illustrative CAPA, not a real action.</p>",
            }
        )
        created["capa"] += 1

# Two sample measurement devices and one completed calibration certificate.
equipment_records = []
for index in range(1, 3):
    name = f"{PREFIX} QMS Measurement Device {index:02d}"
    equipment = _find_by_name("ps.quality.equipment", name)
    if not equipment:
        equipment = env["ps.quality.equipment"].create(
            {
                "name": name,
                "manufacturer": f"{PREFIX} Metrology Works",
                "model_number": f"DEMO-M{index:02d}",
                "serial_number": f"DEMO-QMS-{index:02d}",
                "technical_details": f"{PREFIX} Training device; not production equipment.",
                "calibration_interval_days": 365,
                "warning_days": 30,
                "responsible_id": admin.id,
                "company_id": company.id,
                "description": f"<p>{MARKER}; demonstration only.</p>",
            }
        )
        created["equipment"] += 1
    equipment_records.append(equipment)

calibration_marker = f"{MARKER}:calibration:01"
calibration = env["ps.quality.calibration"].search(
    [("notes", "ilike", calibration_marker), ("company_id", "=", company.id)], limit=1
)
if not calibration:
    calibration = env["ps.quality.calibration"].create(
        {
            "name": f"{PREFIX} QMS Calibration 01",
            "equipment_id": equipment_records[0].id,
            "calibration_date": today,
            "result": "pass",
            "calibrated_by_id": admin.id,
            "provider": f"{PREFIX} Metrology Works",
            "certificate_reference": "DEMO-CERT-0001",
            "company_id": company.id,
            "notes": f"<p>{PREFIX} {calibration_marker}; illustrative certificate only.</p>",
        }
    )
    calibration.action_confirm()
    created["calibration"] += 1

env.cr.commit()
print("Created sample QMS records:", created)
print("Total primary records created in this run:", sum(created.values()))
print("Sample records are labeled [MẪU]; no real production records were changed.")
