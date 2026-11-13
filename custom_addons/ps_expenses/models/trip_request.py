import hashlib
import json
import uuid

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, LockError, ValidationError


class PsTeTripRequest(models.Model):
    _name = 'ps.te.trip.request'
    _description = 'PS T&E Trip Request'
    _rec_name = 'reference'
    _order = 'id desc'

    reference = fields.Char(
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: self._new_reference(),
    )
    owner_id = fields.Many2one(
        'res.users', required=True, readonly=True, copy=False, index=True,
        default=lambda self: self.env.user,
    )
    employee_id = fields.Many2one(
        'hr.employee', required=True, readonly=True, copy=False, index=True,
        default=lambda self: self._current_employee(self.env.company).id,
    )
    company_id = fields.Many2one(
        'res.company', required=True, readonly=True, copy=False, index=True,
        default=lambda self: self.env.company,
    )

    purpose = fields.Char()
    destination = fields.Char()
    start_date = fields.Date()
    end_date = fields.Date()
    state = fields.Selection(
        [
            ('preparing', 'Preparing'),
            ('awaiting_business_review', 'Awaiting Business Review'),
            ('approved', 'Approved'),
            ('refused', 'Refused'),
        ],
        required=True,
        readonly=True,
        copy=False,
        default='preparing',
        index=True,
    )
    preparing_revision = fields.Integer(
        required=True, readonly=True, copy=False, default=1,
    )
    edit_revision_token = fields.Char(readonly=True, store=False, copy=False)
    approver_id = fields.Many2one('res.users', readonly=True, copy=False, index=True)
    decision_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    decision_at = fields.Datetime(readonly=True, copy=False)
    decision_reason = fields.Text(readonly=True, copy=False)
    event_ids = fields.One2many('ps.te.trip.event', 'request_id', readonly=True)
    advance_id = fields.Many2one('ps.te.trip.advance', readonly=True, copy=False)
    expense_report_id = fields.Many2one('ps.te.expense.report', readonly=True, copy=False)
    settlement_id = fields.Many2one('ps.te.settlement', readonly=True, copy=False)
    funding_lock_settlement_id = fields.Many2one('ps.te.settlement', readonly=True, copy=False)
    case_status = fields.Selection([('open', 'Open'), ('workflow_closed', 'Workflow Closed — Accounting Separate')], default='open', required=True, readonly=True)
    case_closed_at = fields.Datetime(readonly=True)
    case_closed_by_id = fields.Many2one('res.users', readonly=True)
    correction_case_id = fields.Many2one('ps.te.correction', readonly=True, copy=False)
    correction_hold = fields.Boolean(compute='_compute_correction_hold')
    cancellation_status = fields.Selection([
        ('none', 'No Pending Cancellation'), ('requested', 'Cancellation Awaiting Manager'),
        ('approved', 'Travel Cancelled — Obligations Separate'),
    ], default='none', required=True, readonly=True, copy=False)
    cancellation_revision = fields.Integer(default=0, readonly=True, copy=False)
    cancellation_reason = fields.Text(readonly=True, copy=False)
    cancellation_requested_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    cancellation_requested_at = fields.Datetime(readonly=True, copy=False)
    cancellation_decision_reason = fields.Text(readonly=True, copy=False)
    cancellation_decided_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    cancellation_decided_at = fields.Datetime(readonly=True, copy=False)
    cancellation_next_step = fields.Char(compute='_compute_cancellation_next_step')
    advance_choice = fields.Selection([
        ('undecided', 'Not Decided'), ('requested', 'Advance Requested'),
        ('not_requested', 'No Advance Requested'),
    ], default='undecided', required=True, readonly=True, copy=False)
    employee_mapping_valid = fields.Boolean(
        compute='_compute_employee_mapping_valid', store=True,
    )
    manager_mapping_valid = fields.Boolean(
        compute='_compute_employee_mapping_valid', store=True,
    )

    @api.depends(
        'owner_id', 'company_id', 'approver_id', 'employee_id.user_id',
        'employee_id.company_id', 'employee_id.parent_id.user_id',
        'employee_id.parent_id.company_id',
    )
    def _compute_employee_mapping_valid(self):
        for request in self:
            employee = request.employee_id
            request.employee_mapping_valid = bool(
                employee and employee.user_id == request.owner_id
                and employee.company_id == request.company_id
            )
            manager = employee.parent_id
            request.manager_mapping_valid = bool(
                request.approver_id and manager.user_id == request.approver_id
                and manager.company_id == request.company_id
            )

    submitted_revision = fields.Integer(readonly=True, copy=False)
    submission_intent = fields.Char(readonly=True, copy=False, index=True)
    submission_receipt = fields.Char(readonly=True, copy=False, index=True)
    submitted_by_id = fields.Many2one(
        'res.users', readonly=True, copy=False,
    )
    submitted_at = fields.Datetime(readonly=True, copy=False)
    submitted_purpose = fields.Char(readonly=True, copy=False)
    submitted_destination = fields.Char(readonly=True, copy=False)
    submitted_start_date = fields.Date(readonly=True, copy=False)
    submitted_end_date = fields.Date(readonly=True, copy=False)
    submitted_owner_id = fields.Many2one(
        'res.users', readonly=True, copy=False,
    )
    submitted_company_id = fields.Many2one(
        'res.company', readonly=True, copy=False,
    )

    _editable_fields = frozenset({'purpose', 'destination', 'start_date', 'end_date'})
    _server_fields = frozenset({
        'reference', 'owner_id', 'employee_id', 'company_id', 'state',
        'preparing_revision', 'submitted_revision', 'submission_intent',
        'submission_receipt', 'submitted_by_id', 'submitted_at',
        'submitted_purpose', 'submitted_destination', 'submitted_start_date',
        'submitted_end_date', 'submitted_owner_id', 'submitted_company_id',
        'approver_id', 'decision_by_id', 'decision_at', 'decision_reason',
        'event_ids',
        'edit_revision_token',
        'advance_id', 'advance_choice',
        'expense_report_id',
        'settlement_id', 'funding_lock_settlement_id', 'case_status', 'case_closed_at', 'case_closed_by_id',
    })

    @api.model
    def _new_reference(self):
        return f'PTR-{uuid.uuid4().hex.upper()}'

    @api.onchange('purpose', 'destination', 'start_date', 'end_date')
    def _onchange_edit_revision(self):
        # Native forms omit an unchanged readonly revision on save, even with
        # force_save. A changed transport token carries the revision the client
        # actually edited. The nonce only makes the field dirty; it grants no
        # authority and is never persisted as business data.
        revision = self.env.context.get('expected_preparing_revision')
        if revision is None:
            if self._origin:
                raise ValidationError(_('Reload the request before editing its preparing revision.'))
            revision = self.preparing_revision
        if type(revision) is not int or revision < 1:
            raise ValidationError(_('A valid preparing revision is required.'))
        self.edit_revision_token = f'{revision}:{uuid.uuid4().hex}'

    @api.model
    def _revision_from_edit_token(self, token):
        if not isinstance(token, str):
            raise ValidationError(_('A valid edit revision token is required.'))
        revision, separator, nonce = token.partition(':')
        if (
            not separator or not revision.isascii() or not revision.isdecimal()
            or int(revision) < 1 or len(nonce) != 32
            or any(character not in '0123456789abcdef' for character in nonce)
        ):
            raise ValidationError(_('A valid edit revision token is required.'))
        return int(revision)

    @api.model
    def _current_employee(self, company):
        user = self.env.user
        if company not in user.company_ids or company not in self.env.companies:
            raise AccessError(_('Trip request access is not permitted.'))
        employee = self.env['hr.employee'].sudo().search([
            ('user_id', '=', user.id),
            ('company_id', '=', company.id),
            ('active', '=', True),
        ], limit=2)
        if len(employee) != 1:
            raise AccessError(_('Trip request access is not permitted.'))
        return employee

    def _current_approver(self):
        self.ensure_one()
        manager = self.employee_id.sudo().parent_id
        user = manager.user_id
        if (
            not manager or not manager.active or manager.company_id != self.company_id
            or not user or not user.active or user == self.owner_id
            or self.company_id not in user.company_ids
            or not user.has_group('ps_expenses.group_ps_te_trip_manager')
        ):
            raise ValidationError(_(
                'Configure an active, authorized manager in the employee company before submission.'
            ))
        return user

    def _assert_manager(self):
        self.ensure_one()
        user = self.env.user
        employee = self.employee_id.sudo()
        if (
            not user.active
            or not user.has_group('ps_expenses.group_ps_te_trip_manager')
            or self.owner_id == user or self.approver_id != user
            or self.company_id not in user.company_ids
            or self.company_id not in self.env.companies
            or not employee.active or employee.user_id != self.owner_id
            or employee.company_id != self.company_id
            or self._current_approver() != user
        ):
            raise AccessError(_('Only the currently assigned manager may decide this request.'))

    def _record_event(self, event_type, reason=None):
        self.ensure_one()
        return self.env['ps.te.trip.event'].sudo()._append({
            'request_id': self.id,
            'owner_id': self.owner_id.id,
            'company_id': self.company_id.id,
            'actor_id': self.env.user.id,
            'occurred_at': fields.Datetime.now(),
            'event_type': event_type,
            'revision': self.submitted_revision,
            'reason': reason,
            'receipt': self.submission_receipt,
            'purpose': self.submitted_purpose,
            'destination': self.submitted_destination,
            'start_date': self.submitted_start_date,
            'end_date': self.submitted_end_date,
        })

    def _assert_current_membership(self):
        user = self.env.user
        allowed_companies = self.env.companies
        for request in self:
            employee = request.employee_id.sudo()
            permitted = (
                request.owner_id == user
                and request.company_id in user.company_ids
                and request.company_id in allowed_companies
                and employee.active
                and employee.user_id == user
                and employee.company_id == request.company_id
            )
            if not permitted:
                raise AccessError(_('Trip request access is not permitted.'))

    @api.constrains('start_date', 'end_date')
    def _check_date_range(self):
        for request in self:
            if (
                request.start_date
                and request.end_date
                and request.end_date < request.start_date
            ):
                raise ValidationError(
                    _('End date cannot be before start date.')
                )

    @api.model_create_multi
    def create(self, vals_list):
        self.browse().check_access('create')
        company = self.env.company
        employee = self._current_employee(company)
        protected = self._server_fields - {'reference'}
        prepared = []
        for source_vals in vals_list:
            vals = dict(source_vals)
            if 'edit_revision_token' in vals:
                if self._revision_from_edit_token(vals.pop('edit_revision_token')) != 1:
                    raise AccessError(_('The initial preparing revision must be 1.'))
            # The form force-saves its readonly optimistic-lock field on both
            # create and edit. Accept only the server's initial revision on
            # create, discard it, and still assign the value ourselves below.
            if 'preparing_revision' in vals:
                if type(vals['preparing_revision']) is not int or vals['preparing_revision'] != 1:
                    raise AccessError(_('The initial preparing revision must be 1.'))
                vals.pop('preparing_revision')
            if protected.intersection(vals) or 'reference' in vals:
                raise AccessError(
                    _('Owner, company, state, revision, and submission data are server assigned.')
                )
            unknown = set(vals) - self._editable_fields
            if unknown:
                raise AccessError(_('Unsupported trip request fields.'))
            vals.update({
                'reference': self._new_reference(),
                'owner_id': self.env.user.id,
                'employee_id': employee.id,
                'company_id': company.id,
                'state': 'preparing',
                'preparing_revision': 1,
            })
            prepared.append(vals)
        safe = self.with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
        return super(PsTeTripRequest, safe).create(prepared)

    def write(self, vals):
        self.check_access('write')
        if not vals:
            return True
        self.lock_for_update()
        self.invalidate_recordset()
        self._assert_current_membership()

        unexpected = set(vals) - self._editable_fields - {'preparing_revision', 'edit_revision_token'}
        if unexpected:
            raise AccessError(
                _('Owner, company, state, revision, and submission data are server controlled.')
            )
        editable_vals = {
            key: value for key, value in vals.items() if key in self._editable_fields
        }
        expected_revision = vals.get('preparing_revision')
        if 'edit_revision_token' in vals:
            token_revision = self._revision_from_edit_token(vals['edit_revision_token'])
            if expected_revision is not None and expected_revision != token_revision:
                raise ValidationError(_('Conflicting edit revision values.'))
            expected_revision = token_revision
        if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 1):
            raise ValidationError(_('A valid preparing revision is required.'))
        if not editable_vals:
            if expected_revision is not None:
                for request in self:
                    if request.preparing_revision != expected_revision:
                        raise ValidationError(_('Stale or conflicting preparing revision.'))
            return True
        if expected_revision is None:
            raise ValidationError(_('Preparing revision is required for an edit.'))
        for request in self:
            request._assert_travel_open()
            if request.state != 'preparing':
                raise AccessError(_('Submitted trip request facts are immutable.'))
            if request.preparing_revision != expected_revision:
                raise ValidationError(_('Stale or conflicting preparing revision.'))
        update_vals = dict(editable_vals)
        update_vals['preparing_revision'] = expected_revision + 1
        return super().write(update_vals)

    def copy(self, default=None):
        if not self.env.su:
            raise AccessError(_('Trip requests cannot be copied.'))
        return super().copy(default)

    def unlink(self):
        if not self.env.su:
            raise AccessError(_('Trip requests cannot be deleted.'))
        return super().unlink()

    def _intent_for_revision(self, revision):
        self.ensure_one()
        value = (
            f'{self.reference}|{revision}|{self.owner_id.id}|{self.company_id.id}'
        )
        return hashlib.sha256(value.encode('utf-8')).hexdigest()

    def _result_action(self, status, *, message, receipt=None, intent=None, revision=None):
        self.ensure_one()
        payload = {
            'status': status,
            'reference': self.reference,
            'phase': self.state,
            'expected_revision': revision if revision is not None else (self.submitted_revision or self.preparing_revision),
        }
        if receipt:
            payload['receipt'] = receipt
        if intent:
            payload['intent'] = intent
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Trip request submission'),
                'message': message,
                'type': 'success' if status == 'confirmed' else 'warning',
                'sticky': status != 'confirmed',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
            'ps_te_trip_request_result': payload,
        }

    def action_submit(self, expected_revision=None, correlation_token=None):
        self.ensure_one()
        self.check_access('write')
        if expected_revision is None:
            expected_revision = self.env.context.get('expected_preparing_revision')
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValidationError(_('A valid preparing revision is required.'))
        self._assert_current_membership()
        try:
            self.lock_for_update()
        except LockError:
            self.invalidate_recordset()
            self._assert_current_membership()
            return self._result_action(
                'unconfirmed',
                message=_(
                    'Submission result is unconfirmed. Reconcile this same intent before retrying.'
                ),
                intent=self._intent_for_revision(expected_revision),
            )
        self.invalidate_recordset()
        self._assert_current_membership()
        self._assert_travel_open()
        intent = self._intent_for_revision(expected_revision)

        if self.state in ('awaiting_business_review', 'approved', 'refused'):
            if (
                self.submitted_revision == expected_revision
                and self.submission_intent == intent
            ):
                return self._result_action(
                    'confirmed',
                    message=_('Submission is confirmed.'),
                    receipt=self.submission_receipt,
                    intent=self.submission_intent,
                )
            raise ValidationError(_('Stale or conflicting preparing revision.'))
        if self.state != 'preparing' or self.preparing_revision != expected_revision:
            raise ValidationError(_('Stale or conflicting preparing revision.'))
        missing = [
            label
            for field_name, label in (
                ('purpose', _('Purpose')),
                ('destination', _('Destination')),
                ('start_date', _('Start date')),
                ('end_date', _('End date')),
            )
            if not self[field_name] or (isinstance(self[field_name], str) and not self[field_name].strip())
        ]
        if missing:
            raise ValidationError(
                _('Required for submission: %s') % ', '.join(missing)
            )
        if self.end_date < self.start_date:
            raise ValidationError(_('End date cannot be before start date.'))

        approver = self._current_approver()
        receipt = f'PTR-RCPT-{uuid.uuid4().hex.upper()}'
        super(PsTeTripRequest, self).write({
            'state': 'awaiting_business_review',
            'submitted_revision': expected_revision,
            'submission_intent': intent,
            'submission_receipt': receipt,
            'submitted_by_id': self.env.user.id,
            'submitted_at': fields.Datetime.now(),
            'submitted_purpose': self.purpose,
            'submitted_destination': self.destination,
            'submitted_start_date': self.start_date,
            'submitted_end_date': self.end_date,
            'submitted_owner_id': self.owner_id.id,
            'submitted_company_id': self.company_id.id,
            'approver_id': approver.id,
            'decision_by_id': False,
            'decision_at': False,
            'decision_reason': False,
        })
        self._record_event('submitted')
        return self._result_action(
            'confirmed',
            message=_('Submission is confirmed.'),
            receipt=receipt,
            intent=intent,
        )

    def action_reconcile(self, expected_revision=None):
        self.ensure_one()
        self.check_access('read')
        self.invalidate_recordset()
        self._assert_current_membership()
        if expected_revision is None:
            expected_revision = self.env.context.get('expected_preparing_revision')
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValidationError(_('A valid preparing revision is required.'))
        intent = self._intent_for_revision(expected_revision)
        if (
            self.state in ('awaiting_business_review', 'approved', 'refused')
            and self.submitted_revision == expected_revision
            and self.submission_intent == intent
        ):
            return self._result_action(
                'confirmed',
                message=_('Persisted submission is confirmed.'),
                receipt=self.submission_receipt,
                intent=self.submission_intent,
            )
        historical_submission = self.env['ps.te.trip.event'].sudo().search([
            ('request_id', '=', self.id), ('revision', '=', expected_revision),
            ('event_type', '=', 'submitted'),
        ], limit=1)
        if historical_submission:
            return self._result_action(
                'confirmed',
                message=_('This version was submitted. Check the current phase and decision history.'),
                receipt=historical_submission.receipt,
                intent=intent,
                revision=expected_revision,
            )
        return self._result_action(
            'unconfirmed',
            message=_(
                'No confirmed submission exists for this exact intent. Review the current preparing revision before retrying.'
            ),
            intent=intent,
        )

    @api.depends_context('lang')
    @api.depends('cancellation_status', 'state', 'case_status')
    def _compute_cancellation_next_step(self):
        for trip in self:
            if trip.cancellation_status == 'requested':
                trip.cancellation_next_step = _('Assigned manager: decide cancellation; retain all obligations.')
            elif trip.cancellation_status == 'approved':
                trip.cancellation_next_step = (_('Workflow closed; external accounting remains separate.')
                    if trip.case_status == 'workflow_closed' else
                    _('Travel stopped. Finance/cash must reconcile retained costs and funding; no automatic zero.'))
            else:
                trip.cancellation_next_step = False

    def _assert_travel_open(self):
        self.ensure_one()
        self._assert_no_active_correction()
        if self.case_status == 'workflow_closed':
            raise ValidationError(_('The financial workflow is closed; use a new adjustment instead of reopening old travel or funding.'))
        if self.cancellation_status != 'none':
            raise ValidationError(_('Travel cancellation is pending or approved; no new travel or advance action is allowed.'))

    def _assert_no_pending_cancellation(self):
        self.ensure_one()
        self._assert_no_active_correction()
        if self.cancellation_status == 'requested':
            raise ValidationError(_('Decide the pending trip cancellation before new settlement approval, cash preparation or closure.'))

    def _cancellation_lock(self):
        self.ensure_one()
        self.check_access('write')
        self.lock_for_update()
        self.invalidate_recordset()
        record = self.sudo()
        for source in (record.advance_id, record.expense_report_id, record.settlement_id):
            if source:
                source.lock_for_update()
                source.invalidate_recordset()

    def _cancellation_revision_check(self, revision):
        if type(revision) is not int or revision != self.cancellation_revision:
            raise ValidationError(_('Stale cancellation revision. Reload the trip.'))

    def _cancellation_event(self, kind, reason):
        record = self.sudo()
        return self.env['ps.te.trip.event'].sudo()._append({
            'request_id': self.id, 'owner_id': self.owner_id.id, 'company_id': self.company_id.id,
            'actor_id': self.env.uid, 'occurred_at': fields.Datetime.now(), 'event_type': kind,
            'revision': self.preparing_revision, 'reason': reason, 'receipt': self.submission_receipt,
            'purpose': self.purpose, 'destination': self.destination,
            'start_date': self.start_date, 'end_date': self.end_date,
            'cancellation_revision': self.cancellation_revision,
            'cancellation_snapshot': json.dumps({
                'cancellation_status': self.cancellation_status, 'business_state': self.state,
                'case_status': self.case_status, 'advance_id': record.advance_id.id,
                'advance_state': record.advance_id.state, 'advance_outcome': record.advance_id.payment_outcome,
                'expense_id': record.expense_report_id.id, 'expense_revision': record.expense_report_id.revision,
                'settlement_id': record.settlement_id.id, 'settlement_state': record.settlement_id.state,
                'settlement_outcome': record.settlement_id.cash_outcome,
            }, sort_keys=True),
        })

    def action_request_cancellation(self, reason, expected_revision, expected_cancellation_revision):
        self._cancellation_lock()
        self._assert_current_membership()
        self._assert_no_active_correction()
        reason = self.env['ps.te.trip.advance']._text(reason, _('Cancellation reason'))
        if type(expected_revision) is not int or expected_revision != self.preparing_revision:
            raise ValidationError(_('Stale or conflicting preparing revision.'))
        if (self.cancellation_status == 'requested' and self.cancellation_reason == reason
                and type(expected_cancellation_revision) is int
                and expected_cancellation_revision in (self.cancellation_revision - 1, self.cancellation_revision)):
            return True
        self._cancellation_revision_check(expected_cancellation_revision)
        if self.case_status != 'open' or self.cancellation_status != 'none':
            raise ValidationError(_('Only an open case without a pending or approved cancellation may request cancellation.'))
        manager = self._current_approver()
        if self.approver_id and self.approver_id != manager:
            raise ValidationError(_('The manager assignment changed; resolve authority before cancellation.'))
        super().write({'cancellation_status': 'requested', 'cancellation_revision': self.cancellation_revision + 1,
                       'cancellation_reason': reason, 'cancellation_requested_by_id': self.env.uid,
                       'cancellation_requested_at': fields.Datetime.now(), 'approver_id': manager.id,
                       'cancellation_decision_reason': False, 'cancellation_decided_by_id': False,
                       'cancellation_decided_at': False})
        self._cancellation_event('cancellation_requested', reason)
        return True

    def action_decide_cancellation(self, decision, reason, expected_cancellation_revision):
        self._cancellation_lock()
        self._assert_manager()
        self._assert_no_active_correction()
        self._cancellation_revision_check(expected_cancellation_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Decision reason'))
        if decision not in ('approved', 'refused'):
            raise ValidationError(_('Unsupported cancellation decision.'))
        if self.cancellation_status != 'requested':
            event = self.env['ps.te.trip.event'].sudo().search_count([
                ('request_id', '=', self.id), ('cancellation_revision', '=', self.cancellation_revision),
                ('event_type', '=', 'cancellation_' + decision), ('actor_id', '=', self.env.uid), ('reason', '=', reason),
            ])
            if event and self.cancellation_status == ('approved' if decision == 'approved' else 'none'):
                return True
            raise ValidationError(_('This cancellation request has already been resolved.'))
        super().write({'cancellation_status': 'approved' if decision == 'approved' else 'none',
                       'cancellation_decision_reason': reason, 'cancellation_decided_by_id': self.env.uid,
                       'cancellation_decided_at': fields.Datetime.now()})
        self._cancellation_event('cancellation_' + decision, reason)
        return True

    def action_withdraw_cancellation(self, reason, expected_cancellation_revision):
        self._cancellation_lock()
        self._assert_current_membership()
        self._cancellation_revision_check(expected_cancellation_revision)
        reason = self.env['ps.te.trip.advance']._text(reason, _('Revision reason'))
        if self.cancellation_status != 'requested':
            if self.cancellation_status == 'none' and self.env['ps.te.trip.event'].sudo().search_count([
                ('request_id', '=', self.id), ('cancellation_revision', '=', self.cancellation_revision),
                ('event_type', '=', 'cancellation_withdrawn'), ('actor_id', '=', self.env.uid), ('reason', '=', reason),
            ]):
                return True
            raise ValidationError(_('Only a pending cancellation may be withdrawn.'))
        super().write({'cancellation_status': 'none'})
        self._cancellation_event('cancellation_withdrawn', reason)
        return True

    def action_open_cancellation(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Trip Cancellation'),
                'res_model': 'ps.te.trip.cancellation.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_trip_id': self.id, 'default_expected_revision': self.preparing_revision,
                            'default_expected_cancellation_revision': self.cancellation_revision}}

    @api.depends('correction_case_id.active_trip_id')
    def _compute_correction_hold(self):
        for record in self:
            record.correction_hold = record._has_active_correction()

    def _has_active_correction(self):
        self.ensure_one()
        return bool(self.sudo().correction_case_id.active_trip_id)

    def _assert_no_active_correction(self):
        if self._has_active_correction():
            raise ValidationError(_('An active correction case holds new decisions and execution. Resolve or route it first.'))

    def _bind_correction(self, correction):
        self.ensure_one()
        if correction.trip_id != self:
            raise ValidationError(_('Correction source mismatch.'))
        return super().write({'correction_case_id': correction.id})

    def action_open_correction(self):
        self.ensure_one()
        self.check_access('read')
        self._assert_current_membership()
        record = self.correction_case_id
        if record and record.active_trip_id:
            return {'type': 'ir.actions.act_window', 'res_model': record._name, 'res_id': record.id, 'view_mode': 'form'}
        return {'type': 'ir.actions.act_window', 'name': _('Correction Case'),
                'res_model': 'ps.te.correction.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_trip_id': self.id, 'default_expected_revision': self.preparing_revision}}

    def action_open_review_wizard(self):
        self.ensure_one()
        self.check_access('write')
        self._assert_manager()
        if self.state != 'awaiting_business_review':
            raise ValidationError(_('Only a request awaiting business review may be decided.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Review trip request'),
            'res_model': 'ps.te.trip.review.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.id,
                'default_expected_revision': self.submitted_revision,
            },
        }

    def _set_advance_choice(self, choice, advance=None):
        self.ensure_one()
        vals = {'advance_choice': choice}
        if advance:
            vals['advance_id'] = advance.id
        super().write(vals)

    def _bind_expense_report(self, report):
        self.ensure_one()
        return super().write({'expense_report_id': report.id})

    def _bind_settlement(self, settlement):
        self.ensure_one()
        return super().write({'settlement_id': settlement.id})

    def _set_funding_lock(self, settlement):
        self.ensure_one()
        return super().write({'funding_lock_settlement_id': settlement.id if settlement else False})

    def _close_workflow_case(self, settlement):
        self.ensure_one()
        if self.settlement_id != settlement or settlement.state != 'closed':
            raise ValidationError(_('Only the linked closed settlement can close this workflow case.'))
        return super().write({'case_status': 'workflow_closed', 'case_closed_at': fields.Datetime.now(),
                              'case_closed_by_id': settlement.closed_by_id.id})

    def action_open_settlement(self):
        self.ensure_one()
        self.check_access('read')
        self._assert_current_membership()
        record = self.settlement_id
        if not record:
            record = self.env['ps.te.settlement'].create({'trip_id': self.id})
        return {'type': 'ir.actions.act_window', 'res_model': record._name, 'res_id': record.id, 'view_mode': 'form'}

    def action_open_expenses(self):
        self.ensure_one()
        self.check_access('read')
        self._assert_current_membership()
        report = self.expense_report_id
        if not report:
            report = self.env['ps.te.expense.report'].create({'trip_id': self.id})
        return report._entry_action()

    def action_no_advance(self):
        self.ensure_one()
        self.check_access('write')
        self.lock_for_update()
        self.invalidate_recordset()
        self._assert_current_membership()
        self._assert_no_active_correction()
        if self.funding_lock_settlement_id and self.advance_choice != 'not_requested':
            raise ValidationError(_('Advance intent is locked by settlement.'))
        if self.state != 'approved' and self.cancellation_status != 'approved':
            raise ValidationError(_('Business approval is required before declaring advance intent.'))
        if self.advance_id and self.advance_id.state != 'cancelled':
            raise ValidationError(_('Cancel the unexecuted advance before choosing no advance.'))
        if self.advance_choice != 'not_requested':
            self._set_advance_choice('not_requested')
            self._record_event('advance_not_requested', _('Employee explicitly requested no advance'))
        return True

    def action_open_advance(self):
        self.ensure_one()
        self.check_access('read')
        self._assert_current_membership()
        if self.advance_id:
            return {'type': 'ir.actions.act_window', 'res_model': 'ps.te.trip.advance',
                    'res_id': self.advance_id.id, 'view_mode': 'form'}
        if self.state != 'approved':
            raise ValidationError(_('Business approval is required before requesting an advance.'))
        return {'type': 'ir.actions.act_window', 'name': _('Request Advance'),
                'res_model': 'ps.te.advance.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_trip_id': self.id, 'default_operation': 'create'}}

    def action_review(self, decision, reason, expected_revision):
        self.ensure_one()
        self.check_access('write')
        if decision not in ('approved', 'refused', 'returned'):
            raise ValidationError(_('Unsupported business decision.'))
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError(_('A decision reason is required.'))
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValidationError(_('A valid submitted revision is required.'))
        reason = reason.strip()
        self.lock_for_update()
        self.invalidate_recordset()
        self._assert_manager()
        self._assert_travel_open()
        if self.submitted_revision != expected_revision:
            raise ValidationError(_('Stale or conflicting submitted revision.'))
        if self.state != 'awaiting_business_review':
            previous = self.env['ps.te.trip.event'].sudo().search([
                ('request_id', '=', self.id), ('revision', '=', expected_revision),
                ('event_type', '=', decision), ('actor_id', '=', self.env.uid),
                ('reason', '=', reason),
            ], limit=1)
            expected_state = 'preparing' if decision == 'returned' else decision
            if previous and self.state == expected_state:
                return True
            raise ValidationError(_('This submitted version has already been decided.'))
        update_vals = {
            'state': 'preparing' if decision == 'returned' else decision,
            'decision_by_id': self.env.uid,
            'decision_at': fields.Datetime.now(),
            'decision_reason': reason,
        }
        if decision == 'returned':
            update_vals['preparing_revision'] = self.preparing_revision + 1
        super().write(update_vals)
        self._record_event(decision, reason)
        return True
