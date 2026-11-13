"""Chỉ dẫn thao tác, không cấp quyền hay thay thế kiểm tra nghiệp vụ trên máy chủ."""
from odoo import api, fields, models, _


class TripGuidance(models.Model):
    _inherit = 'ps.te.trip.request'

    workflow_next_step = fields.Text(string='Next Step', compute='_compute_workflow_next_step')
    is_current_owner = fields.Boolean(string='Current User Is Owner', compute='_compute_current_owner')

    @api.depends_context('uid')
    @api.depends('owner_id')
    def _compute_current_owner(self):
        for record in self:
            record.is_current_owner = record.owner_id == self.env.user

    @api.depends_context('lang')
    @api.depends('state', 'cancellation_status', 'case_status', 'correction_hold', 'advance_choice')
    def _compute_workflow_next_step(self):
        for record in self:
            if record.correction_hold:
                message = _('Correction hold: assigned finance must resolve the case. Reconcile any existing uncertain cash first; do not start new execution.')
            elif record.cancellation_status == 'requested':
                message = _('Assigned manager: decide the cancellation. Retain costs and funding; do not assume a zero balance.')
            elif record.case_status == 'workflow_closed':
                message = _('Workflow closed. External accounting is still not verified; retained history must not be overwritten.')
            elif record.cancellation_status == 'approved':
                message = _('Travel cancelled. Owner: declare retained costs or explicitly declare no expenses. Finance and cash must reconcile obligations before closure.')
            elif record.state == 'preparing':
                message = _('Owner: save the facts, then submit. If the response is lost, reload this same request and check the displayed revision before retrying; never create a replacement request.')
            elif record.state == 'awaiting_business_review':
                message = _('Assigned manager: review this submitted revision. Submission receipt confirms sending, not approval. Owner must wait for the decision.')
            elif record.state == 'refused':
                message = _('Business request refused. Read the decision reason; do not request funding or overwrite the submitted facts.')
            else:
                message = _('Owner: choose advance or explicit no advance, then record expenses. Finance reviews the expense basis; cash confirms actual funding separately before settlement.')
            record.workflow_next_step = message


class AdvanceGuidance(models.Model):
    _inherit = 'ps.te.trip.advance'

    workflow_next_step = fields.Text(string='Next Step', compute='_compute_workflow_next_step')

    @api.depends_context('lang')
    @api.depends('state', 'payment_outcome', 'trip_id.correction_hold', 'trip_id.cancellation_status')
    def _compute_workflow_next_step(self):
        for record in self:
            if record.payment_outcome == 'uncertain':
                message = _('Cash operator: verify the existing attempt against external evidence. Record the exact actual movement or confirm non-execution; never blindly pay again, cancel or reset.')
            elif record.trip_id.correction_hold or record.trip_id.cancellation_status != 'none':
                message = _('Trip held or cancelled. Do not start new disbursement. Reconcile existing cash and use the correction/cancellation process; recorded movements remain immutable.')
            elif record.state == 'draft':
                message = _('Owner: check the requested amount and purpose, then submit this revision to assigned finance.')
            elif record.state == 'submitted':
                message = _('Assigned finance: approve, refuse or return this exact revision with a reason. Approval is not a payment.')
            elif record.state == 'approved':
                message = _('Cash operator: prepare one referenced external attempt before acting, then record verified execution. Recheck current policy and authority; the application does not transfer money.')
            elif record.state == 'disbursed':
                message = _('Actual disbursement is recorded. Owner: continue expenses and settlement; this does not close the trip or verify accounting.')
            else:
                message = _('Read the refusal/cancellation reason. No disbursement is implied; retain history and use only an authorized revision path.')
            record.workflow_next_step = message


class ExpenseGuidance(models.Model):
    _inherit = 'ps.te.expense.report'

    workflow_next_step = fields.Text(string='Next Step', compute='_compute_workflow_next_step')

    @api.depends_context('lang')
    @api.depends('state', 'basis_locked', 'accepted_basis_ready', 'correction_hold', 'adjustment_id.state')
    def _compute_workflow_next_step(self):
        for record in self:
            if record.adjustment_id and not record.basis_locked:
                if record.state == 'submitted':
                    message = _('Assigned finance: review each line and its private proof, or the explicit zero-expense declaration. Give reasons; unresolved items are not accepted or zero.')
                elif record.accepted_basis_ready:
                    message = _('Assigned finance: propose the reviewed adjustment basis for independent cumulative cash verification; do not reopen the original settlement.')
                else:
                    message = _('Owner: add or correct lines and private proofs, then submit. A cancelled trip with no costs requires an explicit zero-expense declaration and finance review; an empty report is not a zero basis.')
            elif record.correction_hold:
                message = _('Correction hold: assigned finance must route or resolve the case before a new expense decision. Do not replace accepted or executed facts.')
            elif record.basis_locked:
                message = _('Expense basis locked by settlement. Do not edit lines or proofs; use the authorized correction process. Claimed and accepted totals remain distinct.')
            elif record.state == 'submitted':
                message = _('Assigned finance: review each line and its private proof, or the explicit zero-expense declaration. Give reasons; unresolved items are not accepted or zero.')
            elif record.accepted_basis_ready:
                message = _('Owner: open or refresh settlement from this reviewed revision. Cash must establish actual funding separately; an accepted expense basis is not payment or accounting completion.')
            else:
                message = _('Owner: add or correct lines and private proofs, then submit. A cancelled trip with no costs requires an explicit zero-expense declaration and finance review; an empty report is not a zero basis.')
            record.workflow_next_step = message


class SettlementGuidance(models.Model):
    _inherit = 'ps.te.settlement'

    workflow_next_step = fields.Text(string='Next Step', compute='_compute_workflow_next_step')

    @api.depends_context('lang')
    @api.depends('state', 'funding_known', 'cash_outcome', 'remaining_amount', 'correction_hold', 'trip_id.cancellation_status', 'trip_id.latest_completed_adjustment_id')
    def _compute_workflow_next_step(self):
        for record in self:
            if record.cash_outcome == 'uncertain':
                message = _('Cash operator: reconcile the existing settlement attempt using external evidence before any retry or closure. A lost response does not prove non-execution.')
            elif record.correction_hold:
                message = _('Correction hold remains even if the original workflow was closed. Assigned finance must resolve the case; actual post-execution changes require qualified external handling.')
            elif record.trip_id.latest_completed_adjustment_id:
                message = _('Historical settlement — consult the latest completed adjustment for the current financial outcome.')
            elif record.state == 'closed':
                message = _('Workflow closed. External accounting is still not verified; retained history must not be overwritten.')
            elif record.trip_id.cancellation_status == 'requested':
                message = _('Assigned manager: decide cancellation before new settlement approval, execution or closure. Reconcile already uncertain operations separately.')
            elif not record.funding_known:
                message = _('Cash operator: establish actual funding or explicitly confirm no funding with evidence. No-advance intent alone is insufficient; no final difference is known yet.')
            elif record.state == 'draft':
                message = _('Owner: verify the saved expense and funding revision, refresh if needed, then submit settlement. Finance must review the exact current basis.')
            elif record.state == 'submitted':
                message = _('Assigned finance: check current policy, authority, expense and funding bases before approval; return stale or incorrect sources for revision.')
            elif record.remaining_amount:
                message = _('Cash operator: resolve the exact remaining top-up or employee return with one prepared, evidenced external movement. Partial or uncertain cash cannot close the case.')
            else:
                message = _('Assigned finance: verify all obligations and current bindings, then explicitly close the workflow. Equality alone never verifies accounting or authorizes closure.')
            record.workflow_next_step = message
