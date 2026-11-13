"""Nhãn lịch sử theo ngôn ngữ; giữ nguyên mã và dữ kiện kiểm toán đã lưu."""
from odoo import api, fields, models, _


def _labels(self):
    # self chỉ cung cấp môi trường/ngôn ngữ cho hàm dịch chuẩn Odoo.
    return {
        'created': _('History: draft created'),
        'line_added': _('History: expense line added'),
        'line_edited': _('History: expense line revised'),
        'submitted': _('History: submitted for review'),
        'zero_declared': _('History: no expenses explicitly declared'),
        'zero_accepted': _('History: zero-expense declaration accepted'),
        'zero_returned': _('History: zero-expense declaration returned'),
        'line_accepted': _('History: expense amount accepted'),
        'line_refused': _('History: expense refused'),
        'line_returned': _('History: expense returned for correction'),
        'reviewed': _('History: expense basis reviewed'),
        'withdrawn': _('History: withdrawn for revision'),
        'evidence_uploaded': _('History: private proof uploaded'),
        'evidence_reused': _('History: existing private proof linked'),
        'evidence_superseded': _('History: proof superseded and retained'),
        'prepared': _('History: settlement bases prepared'),
        'preparation_replaced': _('History: prior preparation retained'),
        'refreshed': _('History: source snapshot refreshed'),
        'no_funding_confirmed': _('History: no funding explicitly confirmed'),
        'approved': _('History: exact settlement approved'),
        'returned': _('History: returned before cash execution'),
        'cash_started': _('History: external cash attempt prepared'),
        'cash_not_executed': _('History: external non-execution confirmed'),
        'cash_recorded': _('History: actual external movement recorded'),
        'workflow_closed': _('History: workflow closed, accounting separate'),
        'returned_by_correction': _('History: unexecuted settlement returned by correction'),
        'opened': _('History: correction case opened'),
        'snapshot_replaced': _('History: previous source snapshot retained'),
        'returned_for_revision': _('History: sources routed for fresh review'),
        'external_required': _('History: external resolution required, hold retained'),
        'no_change_proposed': _('History: finance proposed no source change'),
        'no_change_cash_checked': _('History: independent unchanged-cash check recorded'),
        'resolved_without_source_change': _('History: investigation resolved without source change'),
        'cash_fact_approved': _('History: cash fact correction approved'),
        'cash_fact_refused': _('History: cash fact correction refused'),
        'cash_fact_verified': _('History: cash fact correction independently verified'),
        'cash_fact_proposal_withdrawn': _('History: unverified cash fact proposal withdrawn'),
        'adjustment_closed': _('History: financial adjustment completed'),
    }


class ExpenseEventLabel(models.Model):
    _inherit = 'ps.te.expense.event'

    event_label = fields.Char(string='History Action', compute='_compute_event_label')

    @api.depends_context('lang')
    @api.depends('event_type')
    def _compute_event_label(self):
        labels = _labels(self)
        for event in self:
            event.event_label = labels.get(event.event_type, _('Unrecognized history event; inspect the retained code.'))


class SettlementEventLabel(models.Model):
    _inherit = 'ps.te.settlement.event'

    event_label = fields.Char(string='History Action', compute='_compute_event_label')

    @api.depends_context('lang')
    @api.depends('event_type')
    def _compute_event_label(self):
        labels = _labels(self)
        for event in self:
            event.event_label = labels.get(event.event_type, _('Unrecognized history event; inspect the retained code.'))


class CorrectionEventLabel(models.Model):
    _inherit = 'ps.te.correction.event'

    event_label = fields.Char(string='History Action', compute='_compute_event_label')

    @api.depends_context('lang')
    @api.depends('kind')
    def _compute_event_label(self):
        labels = _labels(self)
        for event in self:
            event.event_label = labels.get(event.kind, _('Unrecognized history event; inspect the retained code.'))
