import uuid

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTripBusinessReview(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        suffix = uuid.uuid4().hex
        cls.company = cls.env['res.company'].create({'name': f'Review A {suffix}'})
        cls.foreign_company = cls.env['res.company'].create({'name': f'Review B {suffix}'})
        employee_group = cls.env.ref('ps_expenses.group_ps_te_trip_employee')
        manager_group = cls.env.ref('ps_expenses.group_ps_te_trip_manager')

        def user(stem, company, manager=False):
            return cls.env['res.users'].with_context(no_reset_password=True).create({
                'name': f'Synthetic {stem}', 'login': f'{stem}.{suffix}@example.invalid',
                'company_id': company.id, 'company_ids': [Command.set([company.id])],
                'group_ids': [Command.set([
                    cls.env.ref('base.group_user').id,
                    manager_group.id if manager else employee_group.id,
                ])],
            })

        cls.owner = user('owner', cls.company)
        cls.manager = user('manager', cls.company, True)
        cls.other_manager = user('other_manager', cls.company, True)
        cls.foreign_manager = user('foreign_manager', cls.foreign_company, True)
        cls.manager_employee = cls.env['hr.employee'].create({
            'name': cls.manager.name, 'user_id': cls.manager.id, 'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': cls.owner.name, 'user_id': cls.owner.id, 'company_id': cls.company.id,
            'parent_id': cls.manager_employee.id,
        })

    def _as(self, record, user):
        return record.with_user(user).with_context(allowed_company_ids=[user.company_id.id])

    def _request(self, submit=True):
        request = self._as(self.env['ps.te.trip.request'], self.owner).create({
            'purpose': 'Synthetic review trip', 'destination': 'Synthetic location',
            'start_date': '2026-11-01', 'end_date': '2026-11-03',
        })
        if submit:
            request.action_submit(1)
        return request

    def test_manager_approval_preserves_snapshot_and_is_idempotent(self):
        request = self._request()
        managed = self._as(request, self.manager)
        self.assertEqual(managed.approver_id, self.manager)
        self.assertEqual(len(managed.event_ids), 1)
        self.assertTrue(managed.action_review('approved', 'Business purpose accepted', 1))
        self.assertEqual(request.state, 'approved')
        self.assertEqual(request.submitted_purpose, 'Synthetic review trip')
        self.assertEqual(request.decision_by_id, self.manager)
        self.assertTrue(request.decision_at)
        managed.action_review('approved', 'Business purpose accepted', 1)
        self.assertEqual(len(request.event_ids), 2)
        with self.assertRaises(ValidationError):
            managed.action_review('refused', 'Conflicting decision', 1)
        with self.assertRaises(AccessError):
            managed.write({'purpose': 'Manager cannot replace employee facts', 'preparing_revision': 1})

    def test_return_correction_resubmit_and_stale_decision(self):
        request = self._request()
        managed = self._as(request, self.manager)
        managed.action_review('returned', 'Clarify destination', 1)
        managed.action_review('returned', 'Clarify destination', 1)
        self.assertEqual(request.state, 'preparing')
        self.assertEqual(request.preparing_revision, 2)
        request.write({'destination': 'Corrected synthetic location', 'preparing_revision': 2})
        request.action_submit(3)
        self.assertEqual(request.submitted_revision, 3)
        self.assertEqual(len(request.event_ids), 3)
        reconciled = request.action_reconcile(1)['ps_te_trip_request_result']
        self.assertEqual(reconciled['status'], 'confirmed')
        self.assertEqual(reconciled['expected_revision'], 1)
        original = request.event_ids.filtered(lambda event: event.event_type == 'submitted' and event.revision == 1)
        self.assertEqual(original.destination, 'Synthetic location')
        with self.assertRaises(ValidationError):
            managed.action_review('approved', 'Stale version', 1)
        managed.action_review('approved', 'Corrected version accepted', 3)
        self.assertEqual(request.state, 'approved')
        self.assertEqual(len(request.event_ids), 4)

    def test_refusal_and_required_reason_and_revision(self):
        request = self._request()
        managed = self._as(request, self.manager)
        with self.assertRaises(ValidationError):
            managed.action_review('refused', '  ', 1)
        with self.assertRaises(ValidationError):
            managed.action_review('approved', 'Reason', True)
        managed.action_review('refused', 'Business purpose not accepted', 1)
        self.assertEqual(request.state, 'refused')
        with self.assertRaises(AccessError):
            request.write({'purpose': 'Changed after refusal', 'preparing_revision': 1})

    def test_unassigned_foreign_and_owner_decisions_denied(self):
        request = self._request()
        for user in (self.owner, self.other_manager, self.foreign_manager):
            with self.assertRaises(AccessError):
                self._as(request, user).action_review('approved', 'Unauthorized', 1)
        for user in (self.other_manager, self.foreign_manager):
            model = self._as(self.env['ps.te.trip.request'], user)
            self.assertFalse(model.search([('id', '=', request.id)]))
            history = self._as(self.env['ps.te.trip.event'], user)
            self.assertFalse(history.search([('request_id', '=', request.id)]))
        for vals in ({'approver_id': self.owner.id}, {'decision_reason': 'Forged'}, {'state': 'approved'}):
            with self.assertRaises(AccessError):
                request.write(vals)

    def test_manager_assignment_or_group_revocation_denies_access(self):
        request = self._request()
        self.employee.parent_id = False
        with self.assertRaises(AccessError):
            self._as(request, self.manager).action_review('approved', 'Revoked hierarchy', 1)
        self.assertFalse(self._as(self.env['ps.te.trip.event'], self.manager).search([
            ('request_id', '=', request.id),
        ]))
        self.employee.parent_id = self.manager_employee
        self.manager.write({'group_ids': [Command.unlink(self.env.ref('ps_expenses.group_ps_te_trip_manager').id)]})
        with self.assertRaises(AccessError):
            self._as(request, self.manager).action_review('approved', 'Revoked role', 1)

    def test_missing_or_self_manager_cannot_submit(self):
        request = self._request(submit=False)
        self.employee.parent_id = False
        with self.assertRaises(ValidationError):
            request.action_submit(1)
        self.assertEqual(request.state, 'preparing')
        self.assertFalse(request.event_ids)
        self.employee.parent_id = self.manager_employee
        self.owner.write({'group_ids': [Command.link(self.env.ref('ps_expenses.group_ps_te_trip_manager').id)]})
        request.action_submit(1)
        with self.assertRaises(AccessError):
            request.action_review('approved', 'Owner with manager role cannot self-approve', 1)

    def test_history_cannot_be_forged_changed_or_deleted(self):
        request = self._request()
        event = request.event_ids
        with self.assertRaises(AccessError):
            self._as(self.env['ps.te.trip.event'], self.owner).create({'request_id': request.id})
        with self.assertRaises(AccessError):
            event.write({'reason': 'Forged'})
        with self.assertRaises(AccessError):
            event.unlink()
        self.employee.user_id = self.other_manager
        self.assertFalse(self._as(self.env['ps.te.trip.request'], self.owner).search([('id', '=', request.id)]))
        self.assertFalse(self._as(self.env['ps.te.trip.event'], self.owner).search([('id', '=', event.id)]))
        self.assertFalse(self._as(self.env['ps.te.trip.request'], self.manager).search([('id', '=', request.id)]))
        self.assertFalse(self._as(self.env['ps.te.trip.event'], self.manager).search([('id', '=', event.id)]))

    def test_review_wizard_uses_actual_request_authorization(self):
        request = self._request()
        wizard_model = self._as(self.env['ps.te.trip.review.wizard'], self.manager)
        wizard = wizard_model.create({
            'request_id': request.id, 'expected_revision': 1,
            'decision': 'approved', 'reason': 'Reviewed in wizard',
        })
        self.assertEqual(wizard.action_apply()['type'], 'ir.actions.act_window_close')
        self.assertEqual(request.state, 'approved')

    def test_employee_form_can_create_edit_and_submit(self):
        model = self._as(self.env['ps.te.trip.request'], self.owner)
        with Form(model) as form:
            form.purpose = 'Created through form'
            form.destination = 'Synthetic destination'
            form.start_date = '2026-11-01'
            form.end_date = '2026-11-03'
        request = form.record
        with Form(request) as editing:
            editing.purpose = 'Edited through form'
        self.assertEqual(request.preparing_revision, 2)
        request.action_submit(2)
        self.assertEqual(request.state, 'awaiting_business_review')

    def test_stale_form_cannot_overwrite_newer_edit(self):
        request = self._request(submit=False)
        first = Form(request)
        stale = Form(request)
        first.purpose = 'First form edit'
        first.save()
        stale.purpose = 'Stale form edit'
        with self.assertRaises(ValidationError):
            stale.save()
        self.assertEqual(request.purpose, 'First form edit')
