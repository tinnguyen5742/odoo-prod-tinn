"""Create an idempotent set of sample warranty data from an Odoo shell."""

from datetime import timedelta

from odoo import fields


operator = env["res.users"].sudo().search([("login", "=", "admin")], limit=1)
if not operator:
    operator = env.user
if not operator.has_group("ps_warranty.group_warranty_administrator"):
    raise RuntimeError("The admin user must have the Warranty Administrator group.")

company = operator.company_id or env.company
today = fields.Date.context_today(operator)
partner_model = env["res.partner"].with_user(operator)
template_model = env["product.template"].with_user(operator)
policy_model = env["ps.warranty.policy"].with_user(operator)
registration_model = env["ps.warranty.registration"].with_user(operator)
claim_model = env["ps.warranty.claim"].with_user(operator)

partners = []
templates = []
created_partners = 0
created_products = 0
created_policies = 0
created_registrations = 0
created_claims = 0

for index in range(1, 11):
    partner_name = f"[MẪU] Khách hàng {index:02d}"
    partner = partner_model.search(
        [("name", "=", partner_name), ("company_id", "in", [False, company.id])],
        limit=1,
    )
    if not partner:
        partner = partner_model.create(
            {"name": partner_name, "company_type": "person", "company_id": company.id}
        )
        created_partners += 1
    partners.append(partner)

    product_name = f"[MẪU] Sản phẩm bảo hành {index:02d}"
    template = template_model.search([("name", "=", product_name)], limit=1)
    if not template:
        template = template_model.create(
            {"name": product_name, "list_price": 2500000 + index * 375000}
        )
        created_products += 1
    templates.append(template)

policy_specs = [
    ("[MẪU] Tiêu chuẩn 12 tháng", 12, "month", "free", 0),
    ("[MẪU] Mở rộng 24 tháng", 24, "month", "free", 0),
    ("[MẪU] Có phí kiểm tra 6 tháng", 6, "month", "chargeable", 150000),
]
policies = []
for name, duration, unit, coverage, fee in policy_specs:
    policy = policy_model.search(
        [("name", "=", name), ("company_id", "=", company.id)], limit=1
    )
    if not policy:
        policy = policy_model.create(
            {
                "name": name,
                "duration": duration,
                "duration_unit": unit,
                "coverage_type": coverage,
                "inspection_fee": fee,
                "company_id": company.id,
                "conditions": "<p>[MẪU] Dữ liệu minh họa, không phải điều khoản thật.</p>",
                "notes": "[MẪU] Tạo tự động để trình diễn Warranty Management.",
            }
        )
        created_policies += 1
    policies.append(policy)

case_specs = [
    ("draft", "0", "Thiết bị chưa khởi động sau khi lắp đặt.", ""),
    ("submitted", "1", "Pin sụt nhanh trong thời gian bảo hành.", ""),
    ("under_review", "2", "Bộ nguồn phát tiếng ồn bất thường.", ""),
    ("approved", "1", "Màn hình chập chờn khi sử dụng liên tục.", ""),
    ("in_progress", "2", "Cổng kết nối không nhận phụ kiện.", ""),
    ("resolved", "0", "Cảm biến hoạt động không ổn định.", "Đã thay cảm biến và kiểm tra lại thiết bị."),
    ("closed", "0", "Sản phẩm bị nóng hơn mức bình thường.", "Đã vệ sinh và thay keo tản nhiệt; khách hàng xác nhận đã nhận máy."),
    ("rejected", "1", "Vỏ thiết bị có dấu hiệu va đập.", ""),
    ("submitted", "0", "Ứng dụng điều khiển mất kết nối định kỳ.", ""),
    ("draft", "1", "Thiết bị không nhận sạc ổn định.", ""),
]

for index, (target_state, priority, problem, resolution) in enumerate(case_specs, start=1):
    reference = f"MẪU-WAR-{index:03d}"
    registration = registration_model.search([("name", "=", reference)], limit=1)
    if not registration:
        start_date = today - timedelta(days=15 + index * 9)
        registration = registration_model.create(
            {
                "name": reference,
                "partner_id": partners[index - 1].id,
                "product_id": templates[index - 1].product_variant_id.id,
                "serial_number": f"MAU-SERIAL-{index:03d}",
                "policy_id": policies[(index - 1) % len(policies)].id,
                "purchase_date": start_date,
                "start_date": start_date,
                "user_id": operator.id,
                "company_id": company.id,
                "notes": f"[MẪU] Hồ sơ bảo hành minh họa số {index:02d}.",
            }
        )
        created_registrations += 1
    if registration.state == "draft":
        registration.action_activate()
    if registration.state != "active":
        raise RuntimeError(f"Sample registration {reference} is not active.")

    claim_reference = f"MẪU-CLM-{index:03d}"
    claim = claim_model.search([("name", "=", claim_reference)], limit=1)
    if not claim:
        claim = claim_model.create(
            {
                "name": claim_reference,
                "registration_id": registration.id,
                "partner_id": registration.partner_id.id,
                "product_id": registration.product_id.id,
                "serial_number": registration.serial_number,
                "claim_date": today - timedelta(days=index),
                "description": (
                    f"<p><strong>[MẪU] CASE-{index:02d}</strong>: {problem}</p>"
                    "<p>Dữ liệu minh họa, không phải yêu cầu bảo hành thật.</p>"
                ),
                "priority": priority,
                "user_id": operator.id,
                "company_id": company.id,
            }
        )
        created_claims += 1

    if claim.state == "draft" and target_state != "draft":
        claim.action_submit()
    if claim.state == "submitted" and target_state in {
        "under_review", "approved", "in_progress", "resolved", "closed", "rejected"
    }:
        claim.action_start_review()
    if claim.state == "under_review" and target_state == "rejected":
        claim.write({"review_note": "[MẪU] Tình huống minh họa: hư hỏng do va đập."})
        claim.action_reject()
    elif claim.state == "under_review" and target_state in {
        "approved", "in_progress", "resolved", "closed"
    }:
        claim.action_approve()
    if claim.state == "approved" and target_state in {"in_progress", "resolved", "closed"}:
        claim.action_start_work()
    if claim.state == "in_progress" and target_state in {"resolved", "closed"}:
        claim.write({"resolution_note": f"[MẪU] {resolution}"})
        claim.action_resolve()
    if claim.state == "resolved" and target_state == "closed":
        claim.action_close()

env.cr.commit()
print(
    "Warranty sample data ready: "
    f"created {created_registrations} registrations and {created_claims} claims "
    "(20 sample business records total); "
    f"{created_partners} customers, {created_products} products, "
    f"{created_policies} policies. Existing sample records were reused."
)
