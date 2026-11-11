# Status vocabulary (approval documents)

Document states of `ps_mfg` follow the `ps_approval` engine vocabulary
(`ps.approval.mixin.approval_state`) so plugging the engine in later changes
the mechanism, not keys, labels or meaning. Labels below are the Vietnamese
(`vi_VN`) terms; use them unchanged in new models and in `ps_approval`.

| Key | English label | Tiếng Việt | Meaning |
|---|---|---|---|
| `draft` | Draft | Nháp | Being prepared. |
| `pending` | Pending Approval | Chờ duyệt | Sent for approval (button **Submit** / "Gửi duyệt"). |
| `approved` | Approved | Đã duyệt | Approved; the document takes effect (stock moves, cost, …). |
| `rejected` | Rejected | Từ chối | Refused by the approver. |
| `cancelled` | Cancelled | Đã hủy | Recalled / cancelled. Add only when the model needs it (component request has it). |

## Applies to

| Model | States | Submit method |
|---|---|---|
| `ps.mfg.workorder.move` | draft → pending → approved / rejected | `action_submit_approval` |
| `ps.mfg.proposal` | draft → pending → approved / rejected | `action_submit_approval` |
| `ps.mfg.proposal.finish` | draft → pending → approved | `action_submit_approval` |
| `ps.mfg.component.request` | draft → pending → approved → done; cancelled | `action_submit_approval` |

Not part of this vocabulary (production lifecycle, not document approval):
`ps.mfg.production` (`draft / confirmed / in_progress / done / cancel`) and
`ps.mfg.wip` (`draft / complete`).

## Rules

- Steps **after** approval are business steps, not approval steps: the
  component request keeps `done` ("Hoàn thành") once everything is transferred.
- Name the "send for approval" method `action_submit_approval` (same as the
  mixin) and put validation in it; it only moves `draft → pending` for now.
- Do not add per-model verbs to labels ("Incomplete", "Complete", "Confirmed"
  for a pending document). The button says the action, the status bar says the
  state.

## Plugging in `ps_approval` (later)

- Inherit `ps.approval.mixin`; the engine writes `approval_state` itself and
  calls `_on_approval_approved/_rejected/_cancelled`. Move today's
  `action_approve` side effects (stock moves, price snapshot, …) into
  `_on_approval_approved`; do not set the state in the hooks.
- Approvers act from the Inbox (`ps.approval.entry`), so the in-form
  **Approve** / **Reject** buttons are temporary and go away; keep **Submit**
  and add `action_recall_approval`.
- `state` and `approval_state` then collapse into one field (the keys already
  match); `done` of the component request stays a business state.
- `ps_approval` ships no `i18n/vi_VN.po` yet; use the labels above there too.
