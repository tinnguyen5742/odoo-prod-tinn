# Advance increment contract — 2026-10-20

Authority: PO's current direct approval of advance implementation within the existing D6 task and six-week release. Status: bounded implementation contract / synthetic developer testing; not company finance-policy verification, independent review, real-money admission or legal compliance assurance.

## Boundary and explicit choices

One advance record per approved trip; an explicit no-advance choice is distinct from unknown intent and from a requested/approved/paid amount of zero. The owner may choose no advance if no active advance exists. Cancelled advances remain retained. Reopening a cancelled/refused request reuses the same record, increments revision and requires fresh approval; it cannot create a second disbursement.

Before advance creation, configure an internal policy reference and distinct authorized finance reviewer and cash operator on the company. Both must be active company members with their explicit roles; neither can act on their own employee advance. These configured assignments are copied to submission and checked against current grants/configuration at action time. They do not certify professional competence or a real payment. A configuration change must not silently transfer an old authorization. The owner can withdraw an unexecuted advance for revision and resubmit with fresh configuration/policy bindings.

VND only, whole units, positive requested amount; positive approval cannot exceed requested amount. No statutory allowance, tax eligibility, overdue rule or automatic policy limit is invented. The technical input ceiling is 999,999,999,999 VND, solely to bound exact whole-unit handling and UI input, not a legal/company limit. Requested/approved/external-disbursement facts have separate actors/times and known flags. Default numeric zero in an unknown field must never serve as an approved/disbursed basis.

Draft edits use a wizard carrying the observed revision. Submission freezes the requested amount/purpose, policy reference, current roles and receipt. Finance approval/refusal/return requires the exact revision and a reason. A return/withdrawal opens a new revision and clears effective approval without erasing history. Cancellation is allowed only before any recorded cash event. After recorded disbursement no edit, reset, cancellation or second payment is permitted in this increment; outstanding money is later resolved through settlement, not deleted.

Only the assigned cash operator, distinct from owner/finance approver, can record one external disbursement equal to the approved amount. Require exact revision, amount, nonempty external reference and execution date not before approval or in the future. The same exact confirmation can be replayed without a second event; conflicting replay fails. External references are unique per company (exact trimmed, case-sensitive identity). This is an attributed operator declaration with a reference, not a bank transfer, bank reconciliation, statutory voucher or tax-deductibility verdict. A legal electronic signature/confirmation regime is not established by an Odoo button or audit row.

All mutations lock trip then advance, validate action-time access and preserve an append-only event snapshot. SQL uniqueness protects one advance per trip and unique external references. Normal public create/write/unlink cannot forge workflow/cash/history fields. Company/owner/current employee mapping and assigned role/configuration rules protect list/read/search and event access. No real invoices, receipts or bank credentials are used.

## Source classification

Primary research: official government full text of Law 56/2024/QH15, Article2(5) amends accounting-document signature/confirmation provisions; Article2(9) removes a clause of original Article16. Source: https://xaydungchinhsach.chinhphu.vn/toan-van-luat-sua-doi-bo-sung-mot-so-dieu-cua-luat-chung-khoan-luat-ke-toan-luat-kiem-toan-doc-lap-119241225125001042.htm (accessed 2026-10-20). The original-law MoJ endpoint returned502, recorded rather than treated as verified. No claim that this research is an exhaustive current consolidated-law review is made.

Consequences here are conservative product boundaries: do not certify a reference/button as a lawful accounting document or electronic signature; retain a separate external source reference and attributable history. The limits, single-payment scope, approval stages, whole-VND precision and role separation above are explicit delegated first-release choices, not quotations of Vietnamese law. Actual policy applicability and qualified verification remain open before real financial acceptance/use. Finance assurance remains NO_GO / REQUIRES_SPECIALIST_VERIFICATION.

## Checks required for this increment

Owner approved-trip create and no-advance; missing config/unapproved/foreign trip denial; one-per-trip race/uniqueness; draft edit/stale revision; approval/refusal/return/withdraw/reopen; amount/date/reference validation; owner/finance/cash separation; forged state/cash/history attempts; revoked assignments and foreign-company read/search; identical/conflicting confirmation retry; cancellation/edit blocked after disbursement; simultaneous confirmation/cancel; native wizard/form loading; install/upgrade and the preceding business-review regression suite.

Expense evidence, settlement/return/top-up, financial reversal, accounting and production admission remain downstream work; this increment cannot close a paid business/financial case.
