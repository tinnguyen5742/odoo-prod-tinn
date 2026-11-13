import uuid

from odoo import Command, SUPERUSER_ID, api
from odoo.exceptions import AccessError, LockError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPsTeTripRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.race_company_id, cls.race_user_id = cls._prepare_committed_actor()
        suffix = uuid.uuid4().hex[:10]
        cls.company_a = cls.env['res.company'].create({
            'name': f'Synthetic Company A {suffix}',
        })
        cls.company_b = cls.env['res.company'].create({
            'name': f'Synthetic Company B {suffix}',
        })
        cls.trip_group = cls.env.ref(
            'ps_expenses.group_ps_te_trip_employee'
        )
        cls.internal_group = cls.env.ref('base.group_user')
        cls.manager_group = cls.env.ref('ps_expenses.group_ps_te_trip_manager')
        cls.manager = cls._make_user('manager', cls.company_a, suffix)
        cls.manager.write({'group_ids': [Command.link(cls.manager_group.id)]})
        cls.manager_employee = cls._make_employee(cls.manager, cls.company_a)
        cls.user_a = cls._make_user('employee_a', cls.company_a, suffix)
        cls.user_other = cls._make_user('employee_other', cls.company_a, suffix)
        cls.user_foreign = cls._make_user('employee_foreign', cls.company_b, suffix)
        cls.employee_a = cls._make_employee(cls.user_a, cls.company_a)
        cls.employee_other = cls._make_employee(cls.user_other, cls.company_a)
        cls.employee_foreign = cls._make_employee(cls.user_foreign, cls.company_b)

    @classmethod
    def _make_user(cls, stem, company, suffix):
        group_field = (
            'group_ids'
            if 'group_ids' in cls.env['res.users']._fields
            else 'groups_id'
        )
        return cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': f'Synthetic {stem} {suffix}',
            'login': f'{stem}.{suffix}@example.invalid',
            'company_id': company.id,
            'company_ids': [Command.set([company.id])],
            group_field: [Command.set([
                cls.internal_group.id,
                cls.trip_group.id,
            ])],
        })

    @classmethod
    def _make_employee(cls, user, company):
        vals = {
            'name': user.name,
            'user_id': user.id,
            'company_id': company.id,
        }
        manager = getattr(cls, 'manager_employee', None)
        if manager and manager.company_id == company:
            vals['parent_id'] = manager.id
        return cls.env['hr.employee'].create(vals)

    def _model_as(self, user, company):
        return self.env['ps.te.trip.request'].with_user(user).with_context(
            allowed_company_ids=[company.id]
        )

    def _complete_vals(self, purpose='Synthetic test trip'):
        return {
            'purpose': purpose,
            'destination': 'Synthetic Destination',
            'start_date': '2026-11-01',
            'end_date': '2026-11-03',
        }

    @staticmethod
    def _status(action):
        return action['ps_te_trip_request_result']['status']

    @classmethod
    def _prepare_committed_actor(cls):
        # Seed before the outer class creates users/companies and locks native
        # global group/digest records. Race tests then write only their requests.
        with cls.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            suffix = uuid.uuid4().hex
            company = env.ref('base.main_company')
            employee_group = env.ref('ps_expenses.group_ps_te_trip_employee')
            manager_group = env.ref('ps_expenses.group_ps_te_trip_manager')
            manager = env['res.users'].with_context(no_reset_password=True).create({
                'name': f'Synthetic manager {suffix}',
                'login': f'race.manager.{suffix}@example.invalid',
                'company_id': company.id, 'company_ids': [Command.set([company.id])],
                'group_ids': [Command.set([env.ref('base.group_user').id, manager_group.id])],
            })
            manager_employee = env['hr.employee'].create({
                'name': manager.name, 'user_id': manager.id, 'company_id': company.id,
            })
            user = env['res.users'].with_context(no_reset_password=True).create({
                'name': f'Synthetic employee {suffix}',
                'login': f'race.employee.{suffix}@example.invalid',
                'company_id': company.id, 'company_ids': [Command.set([company.id])],
                'group_ids': [Command.set([env.ref('base.group_user').id, employee_group.id])],
            })
            env['hr.employee'].create({
                'name': user.name, 'user_id': user.id, 'company_id': company.id,
                'parent_id': manager_employee.id,
            })
            result = (company.id, user.id)
            cr.commit()
            return result

    def _committed_fixture(self, label, request_count=1):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, self.race_user_id, {
                'allowed_company_ids': [self.race_company_id],
            })
            model = env['ps.te.trip.request'].with_context(
                allowed_company_ids=[self.race_company_id]
            )
            requests = model.create([
                self._complete_vals(f'{label} {index + 1}')
                for index in range(request_count)
            ])
            result = (self.race_company_id, self.race_user_id, requests.ids)
            cr.commit()
            return result

    def test_01_own_preparing_create_read_edit_and_validation(self):
        request = self._model_as(self.user_a, self.company_a).create({
            'purpose': 'Incomplete synthetic draft',
        })
        self.assertEqual(request.owner_id, self.user_a)
        self.assertEqual(request.company_id, self.company_a)
        self.assertEqual(request.employee_id, self.employee_a)
        self.assertEqual(request.state, 'preparing')
        self.assertEqual(request.preparing_revision, 1)
        with self.assertRaises(ValidationError):
            request.action_submit(1, 'synthetic-correlation-a')
        request.write({
            'destination': 'Synthetic Destination',
            'preparing_revision': 1,
        })
        self.assertEqual(request.preparing_revision, 2)
        with self.assertRaises(ValidationError):
            request.write({
                'purpose': 'Stale overwrite',
                'preparing_revision': 1,
            })
        with self.assertRaises(ValidationError):
            self._model_as(self.user_a, self.company_a).create({
                'start_date': '2026-11-04',
                'end_date': '2026-11-03',
            })

    def test_02_finance_fields_absent_and_server_fields_not_forgeable(self):
        model = self._model_as(self.user_a, self.company_a)
        for field_name in (
            'amount', 'estimate', 'currency_id', 'advance', 'payment',
            'tax', 'receipt', 'account_id',
        ):
            self.assertNotIn(field_name, model._fields)
        with self.assertRaises(AccessError):
            model.create({
                **self._complete_vals(),
                'owner_id': self.user_other.id,
            })
        with self.assertRaises(AccessError):
            model.create({**self._complete_vals(), 'preparing_revision': 99})
        with self.assertRaises(AccessError):
            model.create({
                **self._complete_vals(),
                'company_id': self.company_b.id,
            })
        context_forged = model.with_context(
            default_owner_id=self.user_other.id,
            default_company_id=self.company_b.id,
        ).create(self._complete_vals('Context-forgery test'))
        self.assertEqual(context_forged.owner_id, self.user_a)
        self.assertEqual(context_forged.company_id, self.company_a)
        imported = model.load(
            ['purpose'], [['Synthetic imported incomplete draft']]
        )
        self.assertFalse(imported['messages'])
        imported_request = model.browse(imported['ids'][0])
        self.assertEqual(imported_request.owner_id, self.user_a)
        self.assertEqual(imported_request.company_id, self.company_a)

    def test_03_other_owner_foreign_company_and_direct_reference_denied(self):
        request = self._model_as(self.user_a, self.company_a).create(
            self._complete_vals()
        )
        other_model = self._model_as(self.user_other, self.company_a)
        self.assertEqual(other_model.search_count([('id', '=', request.id)]), 0)
        self.assertFalse(other_model.search_read([('id', '=', request.id)]))
        self.assertFalse(other_model.name_search(request.reference))
        self.assertFalse(other_model._read_group(
            [('id', '=', request.id)], ['company_id'], ['__count']
        ))
        with self.assertRaises(AccessError):
            other_model.browse(request.id).read(['reference'])
        try:
            other_model.browse(request.id).export_data(['reference'])
        except (AccessError, UserError):
            pass
        else:
            self.fail('Export of another owner request was not refused')
        foreign_model = self._model_as(self.user_foreign, self.company_b)
        self.assertEqual(foreign_model.search_count([('id', '=', request.id)]), 0)
        with self.assertRaises(AccessError):
            foreign_model.browse(request.id).action_reconcile(1)
        with self.assertRaises(AccessError):
            self.env['ps.te.trip.request'].with_user(
                self.user_foreign
            ).with_context(
                allowed_company_ids=[self.company_a.id]
            ).browse(request.id).read(['reference'])

    def test_04_submit_retry_reconcile_and_immutability(self):
        request = self._model_as(self.user_a, self.company_a).create(
            self._complete_vals()
        )
        first = request.action_submit(1, 'synthetic-token-a')
        self.assertEqual(self._status(first), 'confirmed')
        receipt = first['ps_te_trip_request_result']['receipt']
        second = request.action_submit(1, 'synthetic-token-b')
        self.assertEqual(self._status(second), 'confirmed')
        self.assertEqual(
            second['ps_te_trip_request_result']['receipt'], receipt
        )
        reconciled = request.action_reconcile(1)
        self.assertEqual(self._status(reconciled), 'confirmed')
        self.assertEqual(request.state, 'awaiting_business_review')
        self.assertEqual(request.submitted_revision, 1)
        self.assertEqual(request.submitted_purpose, request.purpose)
        self.assertEqual(request.submitted_owner_id, self.user_a)
        self.assertEqual(request.submitted_company_id, self.company_a)
        with self.assertRaises(AccessError):
            request.write({
                'purpose': 'Forbidden submitted edit',
                'preparing_revision': 1,
            })
        with self.assertRaises(AccessError):
            request.write({'state': 'preparing'})
        with self.assertRaises(AccessError):
            request.copy()
        with self.assertRaises(AccessError):
            request.unlink()

    def test_05_preparing_reconcile_is_honestly_unconfirmed(self):
        request = self._model_as(self.user_a, self.company_a).create(
            self._complete_vals()
        )
        result = request.action_reconcile(1)
        self.assertEqual(self._status(result), 'unconfirmed')
        self.assertNotIn('receipt', result['ps_te_trip_request_result'])

    def test_06_mixed_forbidden_batch_is_atomic(self):
        own = self._model_as(self.user_a, self.company_a).create(
            self._complete_vals('Own original')
        )
        other = self._model_as(self.user_other, self.company_a).create(
            self._complete_vals('Other original')
        )
        mixed = self._model_as(self.user_a, self.company_a).browse([
            own.id, other.id,
        ])
        with self.assertRaises(AccessError):
            mixed.write({
                'purpose': 'Must not be written',
                'preparing_revision': 1,
            })
        self.assertEqual(own.sudo().purpose, 'Own original')
        self.assertEqual(other.sudo().purpose, 'Other original')

    def test_07_revoked_membership_is_refused_at_action_time(self):
        suffix = uuid.uuid4().hex[:10]
        user = self._make_user('revoked_employee', self.company_a, suffix)
        self._make_employee(user, self.company_a)
        request = self._model_as(user, self.company_a).create(
            self._complete_vals()
        )
        user.write({
            'company_ids': [Command.set([self.company_b.id])],
            'company_id': self.company_b.id,
        })
        with self.assertRaises(AccessError):
            request.with_user(user).with_context(
                allowed_company_ids=[self.company_a.id]
            ).action_submit(1, 'revoked-membership-token')

    def test_08_synchronized_same_intent_submission(self):
        company_id, user_id, request_ids = self._committed_fixture(
            'Concurrent same intent'
        )
        request_id = request_ids[0]
        context = {'allowed_company_ids': [company_id]}
        with self.registry.cursor() as first_cr, self.registry.cursor() as second_cr:
            first_env = api.Environment(first_cr, user_id, context)
            second_env = api.Environment(second_cr, user_id, context)
            first_record = first_env['ps.te.trip.request'].browse(request_id)
            second_record = second_env['ps.te.trip.request'].browse(request_id)
            first_record.check_access('write')
            first_record.lock_for_update()
            second_result = second_record.action_submit(
                1, 'concurrent-token-b'
            )
            self.assertEqual(self._status(second_result), 'unconfirmed')
            second_cr.commit()
            first_result = first_record.action_submit(
                1, 'concurrent-token-a'
            )
            self.assertEqual(self._status(first_result), 'confirmed')
            first_cr.commit()
        with self.registry.cursor() as cr:
            env = api.Environment(cr, user_id, context)
            persisted = env['ps.te.trip.request'].browse(request_id)
            self.assertEqual(persisted.state, 'awaiting_business_review')
            self.assertTrue(persisted.submission_receipt)
            self.assertEqual(persisted.submitted_revision, 1)

    def test_09_edit_submit_ordering(self):
        company_id, user_id, request_ids = self._committed_fixture(
            'Edit submit ordering', request_count=2
        )
        edit_first_id, submit_first_id = request_ids
        context = {'allowed_company_ids': [company_id]}

        with self.registry.cursor() as edit_cr:
            edit_env = api.Environment(edit_cr, user_id, context)
            edit_env['ps.te.trip.request'].browse(edit_first_id).write({
                'purpose': 'Edited before submit',
                'preparing_revision': 1,
            })
            edit_cr.commit()
        with self.registry.cursor() as submit_cr:
            submit_env = api.Environment(submit_cr, user_id, context)
            with self.assertRaises(ValidationError):
                submit_env['ps.te.trip.request'].browse(
                    edit_first_id
                ).action_submit(1, 'stale-after-edit')

        with self.registry.cursor() as submit_cr:
            submit_env = api.Environment(submit_cr, user_id, context)
            result = submit_env['ps.te.trip.request'].browse(
                submit_first_id
            ).action_submit(1, 'submit-before-edit')
            self.assertEqual(self._status(result), 'confirmed')
            submit_cr.commit()
        with self.registry.cursor() as edit_cr:
            edit_env = api.Environment(edit_cr, user_id, context)
            with self.assertRaises(AccessError):
                edit_env['ps.te.trip.request'].browse(submit_first_id).write({
                    'purpose': 'Forbidden after submit',
                    'preparing_revision': 1,
                })

    def test_10_competing_manager_decisions_do_not_duplicate_history(self):
        company_id, owner_id, request_ids = self._committed_fixture('Competing decisions')
        request_id = request_ids[0]
        context = {'allowed_company_ids': [company_id]}
        with self.registry.cursor() as cr:
            env = api.Environment(cr, owner_id, context)
            request = env['ps.te.trip.request'].browse(request_id)
            request.action_submit(1)
            manager_id = request.approver_id.id
            cr.commit()
        with self.registry.cursor() as first_cr, self.registry.cursor() as second_cr:
            first = api.Environment(first_cr, manager_id, context)['ps.te.trip.request'].browse(request_id)
            second = api.Environment(second_cr, manager_id, context)['ps.te.trip.request'].browse(request_id)
            first.lock_for_update()
            with self.assertRaises(LockError):
                second.action_review('refused', 'Competing decision', 1)
            second_cr.rollback()
            first.action_review('approved', 'Approved once', 1)
            first_cr.commit()
        with self.registry.cursor() as cr:
            request = api.Environment(cr, manager_id, context)['ps.te.trip.request'].browse(request_id)
            request.action_review('approved', 'Approved once', 1)
            self.assertEqual(request.state, 'approved')
            self.assertEqual(len(request.event_ids), 2)
