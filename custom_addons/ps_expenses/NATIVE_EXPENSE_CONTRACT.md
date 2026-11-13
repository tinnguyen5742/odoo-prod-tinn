# Native Expenses source contract — 2026-10-21

PO approved native-first for the internship demo in the current chat. This is a local implementation contract, not independent review, product acceptance, finance/legal assurance or permission to migrate original data. Native Odoo19 Community `hr_expense` is now a dependency of the PS addon. Do not install the separate PoC addon together with this implementation.

## One source per expense/version

`hr.expense` owns the claim (`name`, `date`, `total_amount_currency`) and PS decision extension fields (`ps_decision`, `ps_accepted_amount`, review reason/actor/time/revision). `ps.te.expense.line` is a one-to-one identity/projection: claim and decision fields are readonly, non-stored related fields pointing to native expense. `ps.te.expense.report` is the PS batch/version/readiness aggregate used by settlement and adjustment, not an independent expense ledger.

Report actions create and invoke actual native Expenses methods under a private non-serializable Python capability. Each normal PS line has one native record; zero-expense declarations have no invented native rows. Claim100000/accepted80000/refused20000 remain distinct. Native approval and standard native totals retain the employee claim, not the PS accepted amount. Do not use generic native totals, especially historical adjustment versions, as current PS approved spending. `ps_basis_status` explicitly distinguishes current/proposed/historical versions; PS financial summaries consume only their exact effective version. Prior snapshots/events/proofs remain immutable.

Actual cash remains in `ps.te.cash.event`; native posting/payment are blocked for PS expenses. A closed PS workflow is not native Paid or confirmed accounting/tax treatment. Ordinary unrelated native expenses retain standard behavior and defaults; the global PS privacy restriction applies only when `ps_report_id` is set.

## Standard UI, exact versions

The PS Expenses menu and trip/adjustment entry open inherited native form/list views. Create through the trip's native action or versioned PS Add Expense wizard. The native creation form carries an explicitly observed `ps_expected_revision` with force_save; the server validates it under the report lock. Generic native Submit/Approve/Reset/Refuse/Split/attachment upload are not accepted for PS records. Use the native Odoo **Thao tác PS theo phiên** wizard, whose displayed revision must still match at mutation. An old native button must never substitute the latest server revision for the revision the person actually saw.

Edits on existing PS claims also go through that wizard; native claim fields are readonly on existing PS records. Submission executes native submission after PS revision/policy/role/funding-intent validation. Finance decisions execute native approval/refusal; withdrawal under an unlocked report resets native approval only after PS authorization and history capture. Native receipt previews use controlled proof bytes; direct attachment creation/reparent/public/token/overwrite routes are denied. Proof reuse can authorize a specific immutable old proof without granting its old expense/other files. Broad native-manager rights do not grant access to private PS claims.

## Legacy data and bounds

The80-file version1.16 source is preserved in the project evidence. Old SQL columns are not silently migrated or promoted. A legacy line without `native_expense_id` fails readiness and mutations explicitly; it must never become an accepted zero basis. No original application database has been migrated/upgraded by this transition. Any real migration requires a separate exact plan and authorization.

Current bounded demo: whole VND, one-company scenarios, employee-paid expenses, fixed zero-cost/no-tax category; proof PDF/PNG/JPEG up to5MiB, hash uniqueness, supersession and controlled reuse. No paid dependencies, OCR/e-invoice, bank integration, tax/accounting certification, custom frontend, SaaS/billing or real-money operation. Existing manager reapproval, settlement, correction, independent cash verification and adjustment requirements are not waived. Fresh source-specific tests/HTTP/browser/recovery evidence and whole-product independent review remain mandatory before claiming review-ready/completed.
