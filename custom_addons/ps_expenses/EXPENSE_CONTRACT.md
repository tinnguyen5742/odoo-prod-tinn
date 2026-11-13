# Current native-first adaptation — 2026-10-21

PO approved actual `hr_expense` inheritance for the internship demo. [Native source/UI/version/legacy contract](NATIVE_EXPENSE_CONTRACT.md) supersedes the old attachment-only reuse disposition below. Native expense now owns claim/PS decision values; line records are readonly projections and reports are version aggregates for settlement/adjustment. Native posting/payment remain blocked, and no original-data migration or financial assurance follows. Historical increment evidence below is retained, not relabelled as verification of this changed source.

# Historical expense/evidence increment — 2026-10-20

Authority: PO's current “duyet tien hanh di” for employee expense/evidence submission and finance line review, within the existing D6 release. This is a local implementation contract and synthetic test scope, not finance/legal sign-off or production acceptance. Whole-product fresh independent review stays after the complete local workflow, per the PO's latest correction; none is dispatched here.

## Product choices and meaning

One expense report per approved trip, VND whole units. The owner declares advance intent explicitly before submission; a pending or missing cash record never becomes an assumed zero advance. Expenses can be reviewed independently of funding execution; settlement must later resolve the actual advance basis separately.

Configure a company expense-policy reference and an active assigned finance reviewer distinct from the requester. No statutory allowance, receipt validity, tax deductibility or automatic accounting entry is inferred. Each line has employee description/date/claimed amount; finance records its own accept/refuse/return decision, reason and accepted amount against the exact report revision. Accepted amount is positive and no greater than the claim; refusal is a known zero accepted amount, not missing data. A reduced acceptance preserves the original claim and explicit difference. Owner-paid expenses only in this increment; direct-company-paid accounting/integration is not silently included.

Report states: draft → submitted → reviewed after every line is accepted/refused. A returned line opens a correction-required state. Owner withdrawal/revision resets all effective line decisions and advances the report revision; historical submitted facts, proof hashes and finance decisions remain append-only. Any change requires fresh submission and review; prior acceptance does not silently apply to revised facts. A reviewed subtotal is not a final settlement basis while any line is pending/returned. A final accepted basis has its own readiness flag and exact reviewed revision. Later settlement must lock this basis; expense code cannot itself close a financial case.

Missing evidence is allowed to be submitted honestly, but finance can only return or refuse that line until active evidence exists. Presence of a file is not legal invoice validation. Evidence replacement in a draft marks an old proof superseded with reason; it never overwrites/deletes the original binary. History snapshots include original amount, description/date, policy and proof IDs/hashes.

Technical bounds (not law/company limits): at most100 lines/report, five active proofs/line, five MiB/proof; whole-VND amounts up to999,999,999,999 per line. PDF/PNG/JPEG only, extension and header checks; no HTML/SVG/URL uploads. These checks do not certify malware-free or authentic receipts. A SHA256 proof fingerprint is unique per company in this bounded release; splitting/reusing one invoice across lines is deferred rather than double-counted silently.

## Access and protected native attachments

Only current owner and currently assigned/currently configured finance reviewer may access the report, lines, events and proofs in their permitted active company. A manager title, cash role, old assignment, guessed ID, public URL or token gives no proof access. Native ir.attachment remains the storage/stream primitive; controlled proofs are bound to a protected evidence record. Public/URL attachments, access-token generation, reparenting, public direct attachment create/write/unlink and binary overwrite are refused for protected expenses. Normal unrelated Odoo attachments retain their native behavior.

The native binary lookup/stream path must recheck the actual user even when native helpers sudo a record for streaming. Protected files are served as downloads with non-executable content type; links carry no bearer tokens. Ordinary search/read/export and direct reference/binary paths must share the same owner/finance boundaries. Technical administrator/database access remains a disclosed maintenance capability, not a claimed impossible bypass.

Mutations lock trip then report, including line edits, proof upload/supersession, submit/review and revision. Public normal CRUD cannot forge workflow/review/history values. Submission and identical line-decision retries are idempotent; stale and contradictory actions fail. No receipt image/content, bank secret or real personal information is placed in test logs.

## Native-source disposition and remaining gates

Inspected the exact cached Odoo19 image dd9013e669caaa23d26765dc55814655eaeecca7cfc2c265dbabae913bce22fd: native hr_expense manifest depends on account/web_tour/hr and describes posting/accounting flow; ir.attachment access/search/token/stream hooks and ir.binary lookup/stream source were read. Reuse native private attachment storage; do not install/integrate the accounting-dependent expense flow without a separate exact mapping and financial contract. No new dependency or OCA addon is adopted by this increment.

Recovery of matched DB/filestore, full HTTP/browser/security validation, real-policy specialist verification, partial/disputed settlement and external cash uncertainty remain release gates. These implementation choices are not a Vietnamese-law conclusion or a waiver of frozen D2 requirements. Finance assurance remains NO_GO / REQUIRES_SPECIALIST_VERIFICATION until actually evidenced.
