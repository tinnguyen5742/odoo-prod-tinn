# Local release contract — travel business review foundation

Date: 2026-10-20. Parent task: TE-D6-FIRST-SLICE-LOCAL-IMPLEMENTATION-001.
Basis: current PO delegated implementation and the six-week replan in D:/ps-expenses-te/docs/reports/pl/TE_CORE_V1_SIX_WEEK_REPLAN_20261020.md. This implementation contract covers nonfinancial travel review, not finance/legal sign-off or completed release acceptance.

## Implemented business choices for this increment

Employee owns a request within an active company and an unambiguous active employee mapping. The employee's current active parent employee supplies the assigned manager; that manager must be an active user, belong to the request company and have the explicit Trip Manager group. No self-approval or automatic approval. Missing/invalid assignment blocks submission with an actionable error.

Submission freezes the exact facts/revision, records the assigned manager and appends a submission event. Only that assigned manager, while still the employee's current manager and authorized in the active company, may approve, refuse or return that exact submitted revision. Each decision requires a nonempty reason. Manager title alone and the technical superuser flag do not bypass business authorization. Manager reassignment/revocation blocks the former manager rather than silently rerouting an already submitted request.

Approval/refusal are final in this increment. Return opens a new preparing revision, preserves prior submitted facts/receipt/history and allows the owner to correct/resubmit. Resubmission records a new event and refreshes assignment from the current employee hierarchy. Historical approval never applies to a corrected version. No delete/copy or financial completion is added.

Employees may read their own history; managers may read the currently assigned/current-hierarchy requests and their history within current company scope. Neither may rewrite/delete events or forge protected fields. Employee mappings must remain active and belong to the recorded owner/company; active-company filtering applies to both request and event routes. Technical maintenance access is not a guarantee against privileged database access.

Native form edits carry the client-observed revision through per-field onchange context and a changed, nonpersistent revision token. A readonly unchanged revision alone is not reliably sent on save. The token nonce only makes the field dirty; it is not an access grant. Server writes still compare the transported revision after locking. Unsupported existing-record onchange calls without a client revision fail rather than reading a fresh revision and allowing a stale overwrite. Form creation accepts only the fixed initial revision 1 and assigns owner/company/employee on the server.

All submit/decision/return changes are transactional and lock the request. Duplicate submission of the same committed version retains one receipt. An identical repeated decision retains one event; contradictory/stale decisions are refused. Lock contention is not an approval or confirmed submission. This increment does not claim full response-loss/recovery or all financial concurrency coverage.

## Observable acceptance scenarios

- Valid owner draft/edit/submit, date validation and stale-edit refusal remain covered.
- Missing manager, manager self-assignment, inactive or out-of-company manager cannot enable submission.
- Assigned manager can read and decide; unassigned manager, other employee/company and revoked hierarchy/group cannot.
- Employee cannot forge manager/decision/state or decide their own request.
- Approve/refuse require the exact revision and reason; duplicate identical action creates no second event.
- Return keeps submitted snapshot/event, increments the revision, and resubmit creates a distinct submitted version; stale prior decisions fail.
- Manager cannot replace employee facts; event create/write/delete via public ORM is refused.
- Fresh install and upgrade XML/ACL/view/model graph must load on the exact TEST Odoo version.

Advance, expense/evidence, settlement, cancellation after financial activity, independent review and deployment are not implemented or accepted by this increment. They remain required work in the selected full-release scope.
