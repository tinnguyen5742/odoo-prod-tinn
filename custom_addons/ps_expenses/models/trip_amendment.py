"""Đề xuất thay đổi chuyến đã duyệt: không ghi đè phê duyệt hay tiền cũ."""
import hashlib
import json
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError
from .trip_request import PsTeTripRequest


class TripAmendment(models.Model):
    _name = 'ps.te.trip.amendment'
    _description = 'PS T&E Approved Trip Amendment'
    _rec_name = 'reference'
    _order = 'id desc'
    _one_pending = models.Constraint('UNIQUE(active_trip_id)', 'Only one active trip amendment is allowed.')

    reference = fields.Char(readonly=True, required=True)
    trip_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True, ondelete='restrict')
    active_trip_id = fields.Many2one('ps.te.trip.request', readonly=True, ondelete='restrict')
    owner_id = fields.Many2one('res.users', readonly=True, required=True)
    company_id = fields.Many2one('res.company', readonly=True, required=True)
    manager_id = fields.Many2one('res.users', readonly=True, required=True)
    manager_mapping_valid = fields.Boolean(related='trip_id.manager_mapping_valid', store=True)
    purpose = fields.Char(required=True, readonly=True)
    destination = fields.Char(required=True, readonly=True)
    start_date = fields.Date(required=True, readonly=True)
    end_date = fields.Date(required=True, readonly=True)
    reason = fields.Text(required=True, readonly=True)
    original_facts = fields.Text(required=True, readonly=True)
    source_digest = fields.Char(required=True, readonly=True)
    source_revision = fields.Integer(required=True, readonly=True)
    revision = fields.Integer(default=1, required=True, readonly=True)
    state = fields.Selection([
        ('manager', 'Awaiting Fresh Manager Review'), ('finance', 'Manager Approved — Finance Revalidation Required'),
        ('applied', 'Amendment Applied'), ('refused', 'Amendment Refused'),
    ], default='manager', required=True, readonly=True)
    requested_at = fields.Datetime(required=True, readonly=True)
    decision_reason = fields.Text(readonly=True)
    decided_by_id = fields.Many2one('res.users', readonly=True)
    decided_at = fields.Datetime(readonly=True)
    applied_at = fields.Datetime(readonly=True)

    @api.model
    def _snapshot(self, trip):
        trip = trip.sudo()
        data = {name: str(trip[name]) for name in ('purpose', 'destination', 'start_date', 'end_date',
                'preparing_revision', 'submitted_revision', 'state', 'approver_id', 'cancellation_status',
                'case_status', 'advance_id', 'expense_report_id', 'settlement_id')}
        # Monetary data stays outside the manager-visible amendment. Their
        # revisions still participate in the opaque freshness digest.
        heads = [(r._name, r.id, r.revision, r.state) for r in
                 (trip.advance_id, trip.expense_report_id, trip.settlement_id) if r]
        serialized = json.dumps(data, sort_keys=True)
        return serialized, hashlib.sha256((serialized + json.dumps(heads, sort_keys=True)).encode()).hexdigest()

    @api.model_create_multi
    def create(self, vals_list):
        self.browse().check_access('create')
        allowed = {'trip_id', 'purpose', 'destination', 'start_date', 'end_date', 'reason', 'expected_revision'}
        prepared = []
        trips = []
        for source in vals_list:
            if set(source) != allowed:
                raise AccessError(_('Amendment identity, decisions and snapshots are server controlled.'))
            trip = self.env['ps.te.trip.request'].browse(source['trip_id']).exists()
            if len(trip) != 1:
                raise ValidationError(_('Select one approved trip for amendment.'))
            trip.check_access('read')
            trip._assert_current_membership()
            trips.append(trip)
            prepared.append((trip, source))
        if len({r.id for r in trips}) != len(trips):
            raise ValidationError(_('Only one amendment per trip is allowed in a batch.'))
        self.env['ps.te.trip.request'].browse(sorted(r.id for r in trips)).lock_for_update()
        values = []
        for trip, source in prepared:
            trip.invalidate_recordset()
            trip._assert_current_membership()
            trip._assert_no_active_correction()
            if trip.state != 'approved' or trip.cancellation_status != 'none':
                raise ValidationError(_('Amend only an approved trip without pending or approved cancellation.'))
            if type(source['expected_revision']) is not int or source['expected_revision'] != trip.preparing_revision:
                raise ValidationError(_('Stale or conflicting preparing revision.'))
            manager = trip._current_approver()
            if manager != trip.approver_id:
                raise ValidationError(_('Manager assignment changed; resolve authority before an amendment.'))
            helper = self.env['ps.te.trip.advance']
            purpose = helper._text(source['purpose'], _('Purpose'))
            destination = helper._text(source['destination'], _('Destination'))
            reason = helper._text(source['reason'], _('Amendment reason'))
            start, end = fields.Date.to_date(source['start_date']), fields.Date.to_date(source['end_date'])
            if not start or not end or end < start:
                raise ValidationError(_('End date cannot be before start date.'))
            if (purpose, destination, start, end) == (trip.purpose, trip.destination, trip.start_date, trip.end_date):
                raise ValidationError(_('An amendment must propose changed trip facts.'))
            original, digest = self._snapshot(trip)
            values.append({'reference': 'AMD-' + uuid.uuid4().hex.upper(), 'trip_id': trip.id,
                'active_trip_id': trip.id, 'owner_id': trip.owner_id.id, 'company_id': trip.company_id.id,
                'manager_id': manager.id, 'purpose': purpose, 'destination': destination,
                'start_date': start, 'end_date': end, 'reason': reason, 'original_facts': original,
                'source_digest': digest, 'source_revision': trip.preparing_revision, 'revision': 1,
                'state': 'manager', 'requested_at': fields.Datetime.now()})
        safe = self.with_context({k: v for k, v in self.env.context.items() if not k.startswith('default_')})
        records = super(TripAmendment, safe).create(values)
        for record in records:
            record.trip_id._bind_amendment(record)
        return records

    def write(self, vals):
        raise AccessError(_('Use amendment decisions; proposals and prior facts cannot be edited.'))

    def unlink(self):
        raise AccessError(_('Trip amendments and their decisions must be retained.'))

    def _lock(self):
        self.ensure_one()
        self.check_access('write')
        self.trip_id.lock_for_update()
        self.trip_id.invalidate_recordset()
        self.lock_for_update()
        self.invalidate_recordset()

    def _fresh(self):
        trip = self.trip_id
        if self.source_digest != self._snapshot(trip)[1]:
            raise ValidationError(_('Amendment sources changed; resolve and submit a fresh reviewed proposal.'))
        if trip.cancellation_status != 'none':
            raise ValidationError(_('The trip is cancelled; do not apply this amendment.'))
        return trip

    def action_decide(self, decision, reason, expected_revision):
        self._lock()
        trip = self.trip_id
        trip._assert_manager()
        if self.manager_id != self.env.user:
            raise AccessError(_('Only the currently assigned amendment manager may decide.'))
        if type(expected_revision) is not int or expected_revision != self.revision:
            raise ValidationError(_('Stale amendment revision.'))
        reason = self.env['ps.te.trip.advance']._text(reason, _('Decision reason'))
        if decision not in ('approved', 'refused'):
            raise ValidationError(_('Unsupported business decision.'))
        if self.state != 'manager':
            if self.decided_by_id == self.env.user and self.decision_reason == reason and (
                    self.state == 'refused' if decision == 'refused' else self.state in ('finance', 'applied')):
                return True
            raise ValidationError(_('This amendment version has already been decided.'))
        self._fresh()
        values = {'decided_by_id': self.env.uid, 'decision_reason': reason, 'decided_at': fields.Datetime.now()}
        if decision == 'refused':
            values.update(state='refused', active_trip_id=False)
        elif trip.sudo().advance_id or trip.sudo().expense_report_id or trip.sudo().settlement_id:
            # No reuse of the old financial approval. Full downstream adjustment
            # consumes this manager decision in a separate exact-source step.
            values.update(state='finance')
        else:
            trip._apply_approved_amendment(self)
            values.update(state='applied', active_trip_id=False, applied_at=fields.Datetime.now())
        super().write(values)
        return True

    def action_open_review(self):
        self.ensure_one()
        self.check_access('read')
        self.trip_id._assert_manager()
        return {'type': 'ir.actions.act_window', 'name': _('Trip Amendment'),
                'res_model': 'ps.te.amendment.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_trip_id': self.trip_id.id, 'default_amendment_id': self.id,
                            'default_expected_revision': self.revision}}


class TripAmendmentBinding(models.Model):
    _inherit = 'ps.te.trip.request'

    amendment_id = fields.Many2one('ps.te.trip.amendment', readonly=True, copy=False)
    amendment_hold = fields.Boolean(compute='_compute_amendment_hold')

    @api.depends('amendment_id.active_trip_id')
    def _compute_amendment_hold(self):
        for trip in self:
            trip.amendment_hold = bool(trip.sudo().amendment_id.active_trip_id)

    @api.depends('correction_case_id.active_trip_id', 'amendment_id.active_trip_id')
    def _compute_correction_hold(self):
        return super()._compute_correction_hold()

    def _has_active_correction(self):
        return super()._has_active_correction() or bool(self.sudo().amendment_id.active_trip_id)

    def _bind_amendment(self, amendment):
        self.ensure_one()
        if amendment.trip_id != self:
            raise ValidationError(_('Amendment source mismatch.'))
        return super(PsTeTripRequest, self).write({'amendment_id': amendment.id})

    def _apply_approved_amendment(self, amendment):
        self.ensure_one()
        if amendment.trip_id != self or self.amendment_id != amendment or amendment.state != 'manager':
            raise ValidationError(_('Amendment source mismatch.'))
        self._assert_manager()
        amendment._fresh()
        revision = self.preparing_revision + 1
        values = {name: amendment[name] for name in ('purpose', 'destination', 'start_date', 'end_date')}
        values.update(preparing_revision=revision, submitted_revision=revision,
            submission_intent=self._intent_for_revision(revision),
            submission_receipt='PTR-RCPT-' + uuid.uuid4().hex.upper(),
            submitted_by_id=self.owner_id.id, submitted_at=amendment.requested_at,
            decision_by_id=self.env.uid, decision_at=fields.Datetime.now())
        values['decision_reason'] = _('Fresh manager approval of amendment %s') % amendment.reference
        values.update({'submitted_' + name: amendment[name] for name in ('purpose', 'destination', 'start_date', 'end_date')})
        super(PsTeTripRequest, self).write(values)
        self._record_event('approved', values['decision_reason'])
        return True

    def action_open_amendment(self):
        self.ensure_one()
        self.check_access('read')
        self._assert_current_membership()
        if self.amendment_id and self.amendment_id.active_trip_id:
            return {'type': 'ir.actions.act_window', 'res_model': 'ps.te.trip.amendment',
                    'res_id': self.amendment_id.id, 'view_mode': 'form'}
        return {'type': 'ir.actions.act_window', 'name': _('Trip Amendment'), 'res_model': 'ps.te.amendment.wizard',
                'view_mode': 'form', 'target': 'new',
                'context': {'default_trip_id': self.id, 'default_purpose': self.purpose,
                    'default_destination': self.destination, 'default_start_date': self.start_date,
                    'default_end_date': self.end_date, 'default_expected_revision': self.preparing_revision}}


class TripAmendmentWizard(models.TransientModel):
    _name = 'ps.te.amendment.wizard'
    _description = 'Trip Amendment'

    trip_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True)
    amendment_id = fields.Many2one('ps.te.trip.amendment', readonly=True)
    expected_revision = fields.Integer(required=True, readonly=True)
    purpose = fields.Char()
    destination = fields.Char()
    start_date = fields.Date()
    end_date = fields.Date()
    reason = fields.Text(required=True)
    decision = fields.Selection([('approved', 'Approve'), ('refused', 'Refuse')])
    operation = fields.Selection([('review', 'Manager Review'), ('financial', 'Start Financial Adjustment'),
                                  ('withdraw', 'Withdraw Unapplied Amendment')], default='review', required=True)

    def action_apply(self):
        self.ensure_one()
        if self.amendment_id:
            if self.amendment_id.trip_id != self.trip_id:
                raise ValidationError(_('Amendment source mismatch.'))
            if self.operation == 'financial':
                return self.amendment_id.action_start_financial_adjustment(self.reason, self.expected_revision)
            if self.operation == 'withdraw':
                self.amendment_id.action_withdraw_unapplied(self.reason, self.expected_revision)
                return {'type': 'ir.actions.act_window_close'}
            self.amendment_id.action_decide(self.decision, self.reason, self.expected_revision)
            return {'type': 'ir.actions.act_window_close'}
        record = self.env['ps.te.trip.amendment'].create({
            'trip_id': self.trip_id.id, 'purpose': self.purpose, 'destination': self.destination,
            'start_date': self.start_date, 'end_date': self.end_date,
            'reason': self.reason, 'expected_revision': self.expected_revision})
        return {'type': 'ir.actions.act_window', 'res_model': record._name, 'res_id': record.id, 'view_mode': 'form'}
