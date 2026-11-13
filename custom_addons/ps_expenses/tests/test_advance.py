from datetime import timedelta
import uuid

from odoo import Command, SUPERUSER_ID, api, fields
from odoo.exceptions import AccessError, LockError, ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTripAdvance(TransactionCase):

    @staticmethod
    def _build_fixture(env):
        suffix = uuid.uuid4().hex
        currency = env.ref('base.VND')
        currency.active = True
        company = env['res.company'].create({'name': 'Synthetic Advance ' + suffix, 'currency_id': currency.id})
        users = {}
        for role, group in (
            ('owner', 'group_ps_te_trip_employee'), ('manager', 'group_ps_te_trip_manager'),
            ('finance', 'group_ps_te_finance'), ('cash', 'group_ps_te_cash'),
            ('other', 'group_ps_te_trip_employee'),
        ):
            users[role] = env['res.users'].with_context(no_reset_password=True).create({
                'name': 'Synthetic ' + role, 'login': role + '.' + suffix + '@example.invalid',
                'company_id': company.id, 'company_ids': [Command.set([company.id])],
                'group_ids': [Command.set([env.ref('base.group_user').id, env.ref('ps_expenses.' + group).id])],
            })
        manager_employee = env['hr.employee'].create({
            'name': users['manager'].name, 'user_id': users['manager'].id, 'company_id': company.id,
        })
        env['hr.employee'].create({
            'name': users['owner'].name, 'user_id': users['owner'].id, 'company_id': company.id,
            'parent_id': manager_employee.id,
        })
        company.write({
            'ps_te_advance_policy_reference': 'SYNTHETIC-ADVANCE-V1-' + suffix,
            'ps_te_finance_reviewer_id': users['finance'].id,
            'ps_te_cash_operator_id': users['cash'].id,
        })
        return company.id, {key: value.id for key, value in users.items()}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Committed race actors precede outer fixture locks (native company/group/digest writes).
        with cls.registry.cursor() as cr:
            cls.race_company, cls.race_users = cls._build_fixture(api.Environment(cr, SUPERUSER_ID, {}))
            cr.commit()
        company_id, user_ids = cls._build_fixture(cls.env)
        cls.company = cls.env['res.company'].browse(company_id)
        for role, user_id in user_ids.items():
            setattr(cls, role, cls.env['res.users'].browse(user_id))

    def _as(self, record, user):
        return record.with_user(user).with_context(allowed_company_ids=[user.company_id.id])

    @staticmethod
    def _new_trip(env, users):
        trip = env['ps.te.trip.request'].with_user(users['owner']).with_context(
            allowed_company_ids=[users['owner'].company_id.id],
        ).create({'purpose': 'Synthetic advance trip', 'destination': 'Synthetic location',
                  'start_date': '2026-11-01', 'end_date': '2026-11-03'})
        trip.action_submit(1)
        trip.with_user(users['manager']).action_review('approved', 'Synthetic business approval', 1)
        return trip

    def _trip(self):
        return self._new_trip(self.env, {'owner': self.owner, 'manager': self.manager})

    def _advance(self, trip=None, amount=1000000):
        trip = trip or self._trip()
        return self._as(self.env['ps.te.trip.advance'], self.owner).create({
            'trip_id': trip.id, 'requested_amount': amount, 'purpose': 'Synthetic travel advance',
        })

    def _approved(self, advance=None):
        advance = advance or self._advance()
        advance.action_submit(advance.revision)
        self._as(advance, self.finance).action_review('approved', 'Synthetic policy decision', advance.revision, 900000)
        return advance

    def test_01_request_review_and_external_disbursement_are_separate(self):
        advance = self._advance()
        self.assertFalse(advance.has_approval)
        self.assertFalse(advance.has_disbursement)
        self.assertEqual(advance.trip_id.advance_choice, 'requested')
        advance.action_submit(1)
        advance.action_submit(1)
        self.assertEqual(advance.state, 'submitted')
        self.assertEqual(len(advance.event_ids), 2)
        reviewed = self._as(advance, self.finance)
        reviewed.action_review('approved', 'Synthetic policy decision', 1, 900000)
        reviewed.action_review('approved', 'Synthetic policy decision', 1, 900000)
        self.assertTrue(advance.has_approval)
        self.assertFalse(advance.has_disbursement)
        self.assertEqual(advance.requested_amount, 1000000)
        self.assertEqual(advance.approved_amount, 900000)
        paid = self._as(advance, self.cash)
        today = fields.Date.context_today(paid)
        paid.action_start_disbursement('SYNTHETIC-ATTEMPT-001', 'Prepare external payment', 1)
        paid.action_record_disbursement(900000, 'SYNTHETIC-CASH-001', today, 1)
        paid.action_record_disbursement(900000, 'SYNTHETIC-CASH-001', today, 1)
        self.assertEqual(advance.state, 'disbursed')
        self.assertTrue(advance.has_disbursement)
        self.assertEqual(advance.disbursed_by_id, self.cash)
        self.assertEqual(len(advance.event_ids), 5)
        with self.assertRaises(ValidationError):
            paid.action_record_disbursement(900000, 'SYNTHETIC-CASH-OTHER', today, 1)

    def test_02_no_advance_is_explicit_and_one_record_per_trip(self):
        trip = self._trip()
        self.assertEqual(trip.advance_choice, 'undecided')
        trip.action_no_advance()
        trip.action_no_advance()
        self.assertEqual(trip.advance_choice, 'not_requested')
        self.assertFalse(trip.advance_id)
        self.assertEqual(len(trip.event_ids.filtered(lambda event: event.event_type == 'advance_not_requested')), 1)
        advance = self._advance(trip)
        with self.assertRaises(ValidationError):
            self._advance(trip)
        with self.assertRaises(ValidationError):
            trip.action_no_advance()
        advance.action_cancel('No advance needed', 1)
        trip.action_no_advance()
        self.assertEqual(trip.advance_choice, 'not_requested')
        self.assertEqual(trip.advance_id, advance)

    def test_03_unapproved_foreign_and_unconfigured_requests_denied(self):
        trip = self._as(self.env['ps.te.trip.request'], self.owner).create({'purpose': 'Draft trip'})
        with self.assertRaises(ValidationError):
            self._advance(trip)
        trip = self._trip()
        with self.assertRaises(AccessError):
            self._as(self.env['ps.te.trip.advance'], self.other).create({
                'trip_id': trip.id, 'requested_amount': 1000, 'purpose': 'Unauthorized',
            })
        self.company.ps_te_advance_policy_reference = False
        with self.assertRaises(ValidationError):
            self._advance(trip)

    def test_04_amounts_validation_and_no_automatic_approval(self):
        trip = self._trip()
        for invalid in (0, -1, 1.5, float('nan'), float('inf'), True, 1000000000000):
            with self.assertRaises(ValidationError):
                self._advance(trip, invalid)
        advance = self._advance(trip)
        advance.action_submit(1)
        reviewed = self._as(advance, self.finance)
        for invalid in (0, -1, 1000001, 1.5):
            with self.assertRaises(ValidationError):
                reviewed.action_review('approved', 'Reason', 1, invalid)
        with self.assertRaises(ValidationError):
            reviewed.action_review('approved', ' ', 1, 900000)
        self.assertEqual(advance.state, 'submitted')
        self.assertFalse(advance.has_approval)

    def test_05_return_edit_resubmit_and_historical_snapshots(self):
        advance = self._advance()
        advance.action_submit(1)
        self._as(advance, self.finance).action_review('returned', 'Clarify amount', 1)
        self.assertEqual(advance.state, 'draft')
        self.assertEqual(advance.revision, 2)
        advance.action_edit(800000, 'Corrected purpose', 2)
        with self.assertRaises(ValidationError):
            advance.action_edit(700000, 'Stale edit', 2)
        advance.action_submit(3)
        self._as(advance, self.finance).action_review('approved', 'Revised basis accepted', 3, 750000)
        old = advance.event_ids.filtered(lambda event: event.event_type == 'submitted' and event.revision == 1)
        self.assertEqual(old.requested_amount, 1000000)
        self.assertEqual(old.purpose, 'Synthetic travel advance')
        self.assertEqual(advance.approved_amount, 750000)
        with self.assertRaises(ValidationError):
            self._as(advance, self.finance).action_review('approved', 'Stale', 1, 750000)

    def test_06_cannot_edit_cancel_or_reopen_after_cash_recorded(self):
        advance = self._approved()
        self._as(advance, self.cash).action_start_disbursement('LOCKED-ATTEMPT', 'Prepare', 1)
        self._as(advance, self.cash).action_record_disbursement(900000, 'SYNTHETIC-LOCKED', fields.Date.today(), 1)
        for action in (
            lambda: advance.action_cancel('Cancel after cash', 1),
            lambda: advance.action_revise('Reset after cash', 1),
            lambda: advance.action_edit(800000, 'Change after cash', 1),
        ):
            with self.assertRaises(ValidationError):
                action()
        with self.assertRaises(AccessError):
            advance.write({'state': 'draft', 'disbursed_amount': 0})
        with self.assertRaises(AccessError):
            advance.unlink()

    def test_07_role_separation_direct_forgery_and_history(self):
        advance = self._advance()
        advance.action_submit(1)
        for user in (self.owner, self.cash, self.manager, self.other):
            with self.assertRaises(AccessError):
                self._as(advance, user).action_review('approved', 'Wrong role', 1, 900000)
        self._as(advance, self.finance).action_review('approved', 'Finance decision', 1, 900000)
        for user in (self.owner, self.finance, self.manager, self.other):
            with self.assertRaises(AccessError):
                self._as(advance, user).action_record_disbursement(900000, 'FORGED', fields.Date.today(), 1)
        with self.assertRaises(AccessError):
            self._as(self.env['ps.te.trip.advance'], self.owner).create({
                'trip_id': self._trip().id, 'requested_amount': 100, 'purpose': 'Forged', 'state': 'disbursed',
            })
        event = advance.event_ids[:1]
        for action in (lambda: event.write({'reason': 'Forged'}), lambda: event.unlink(),
                       lambda: self._as(self.env['ps.te.advance.event'], self.owner).create({'advance_id': advance.id})):
            with self.assertRaises(AccessError):
                action()

    def test_08_payment_reference_amount_and_date_validation(self):
        advance = self._approved()
        paid = self._as(advance, self.cash)
        for amount, reference, date in (
            (800000, 'BAD-AMOUNT', fields.Date.today()), (900000, ' ', fields.Date.today()),
            (900000, 'FUTURE', fields.Date.today() + timedelta(days=1)),
            (900000, 'PAST', fields.Date.today() - timedelta(days=1)),
            (900000, 'BAD-DATE', 'not-a-date'),
        ):
            with self.assertRaises(ValidationError):
                paid.action_record_disbursement(amount, reference, date, 1)
        self.assertFalse(advance.has_disbursement)

    def test_09_revoked_assignment_role_and_policy_change(self):
        advance = self._approved()
        self.company.ps_te_advance_policy_reference = 'SYNTHETIC-ADVANCE-V2'
        with self.assertRaises(ValidationError):
            self._as(advance, self.cash).action_record_disbursement(900000, 'OLD-POLICY', fields.Date.today(), 1)
        advance.action_revise('Policy changed', 1)
        self.assertFalse(advance.has_approval)
        advance.action_submit(2)
        self.assertEqual(advance.policy_reference, 'SYNTHETIC-ADVANCE-V2')
        self.finance.write({'group_ids': [Command.unlink(self.env.ref('ps_expenses.group_ps_te_finance').id)]})
        with self.assertRaises(AccessError):
            self._as(advance, self.finance).action_review('approved', 'Revoked role', 2, 900000)

    def test_10_read_search_company_and_assignment_boundaries(self):
        advance = self._advance()
        self.assertFalse(self._as(self.env['ps.te.trip.advance'], self.other).search([('id', '=', advance.id)]))
        self.assertFalse(self._as(self.env['ps.te.advance.event'], self.other).search([('advance_id', '=', advance.id)]))
        self.assertEqual(self._as(advance, self.finance).read(['reference'])[0]['reference'], advance.reference)
        self.assertEqual(self._as(advance, self.cash).trip_id.reference, advance.trip_id.reference)
        self.company.ps_te_finance_reviewer_id = False
        self.assertFalse(self._as(self.env['ps.te.trip.advance'], self.finance).search([('id', '=', advance.id)]))
        self.assertFalse(self._as(self.env['ps.te.advance.event'], self.finance).search([('advance_id', '=', advance.id)]))
        foreign_company = self.env['res.company'].create({'name': 'Synthetic other company'})
        with self.assertRaises(AccessError):
            advance.with_user(self.owner).with_context(allowed_company_ids=[foreign_company.id]).read(['reference'])

    def test_11_cancel_reopen_requires_new_approval(self):
        advance = self._approved()
        advance.action_cancel('Trip postponed', 1)
        advance.action_cancel('Trip postponed', 1)
        with self.assertRaises(ValidationError):
            self._as(advance, self.cash).action_record_disbursement(900000, 'CANCELLED', fields.Date.today(), 1)
        advance.action_revise('Trip resumed', 1)
        self.assertEqual(advance.state, 'draft')
        self.assertFalse(advance.has_approval)
        self.assertEqual(advance.revision, 2)
        advance.action_submit(2)
        self.assertEqual(advance.state, 'submitted')

    def test_12_native_wizard_and_readonly_form(self):
        trip = self._trip()
        model = self._as(self.env['ps.te.advance.wizard'], self.owner).with_context(
            **trip.action_open_advance()['context'],
        )
        with Form(model) as wizard_form:
            wizard_form.amount = 1000000
            wizard_form.purpose = 'Synthetic wizard request'
        action = wizard_form.record.action_apply()
        advance = self._as(self.env['ps.te.trip.advance'].browse(action['res_id']), self.owner)
        self.assertEqual(advance.trip_id, trip)
        Form(advance)  # Load complete native view/spec without granting inline edit.
        with self.assertRaises(AccessError):
            advance.copy()

    def _committed_advance(self):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            users = {role: env['res.users'].browse(user_id) for role, user_id in self.race_users.items()}
            trip = self._new_trip(env, users)
            advance = env['ps.te.trip.advance'].with_user(users['owner']).with_context(
                allowed_company_ids=[self.race_company],
            ).create({'trip_id': trip.id, 'requested_amount': 1000000, 'purpose': 'Synthetic race'})
            advance.action_submit(1)
            advance.with_user(users['finance']).action_review('approved', 'Synthetic race approval', 1, 900000)
            result = advance.id
            cr.commit()
            return result

    def test_13_competing_cash_and_cancel_do_not_execute_twice(self):
        advance_id = self._committed_advance()
        context = {'allowed_company_ids': [self.race_company]}
        with self.registry.cursor() as cash_cr, self.registry.cursor() as owner_cr:
            cash = api.Environment(cash_cr, self.race_users['cash'], context)['ps.te.trip.advance'].browse(advance_id)
            owner = api.Environment(owner_cr, self.race_users['owner'], context)['ps.te.trip.advance'].browse(advance_id)
            cash._lock()
            with self.assertRaises(LockError):
                owner.action_cancel('Concurrent cancel', 1)
            owner_cr.rollback()
            cash.action_start_disbursement('RACE-ATTEMPT', 'Prepare', 1)
            cash.action_record_disbursement(900000, 'SYNTHETIC-RACE-' + uuid.uuid4().hex, fields.Date.today(), 1)
            cash_cr.commit()
        with self.registry.cursor() as cr:
            owner = api.Environment(cr, self.race_users['owner'], context)['ps.te.trip.advance'].browse(advance_id)
            with self.assertRaises(ValidationError):
                owner.action_cancel('Too late', 1)
            self.assertEqual(len(owner.event_ids.filtered(lambda event: event.event_type == 'disbursed')), 1)

    def test_14_external_reference_cannot_pay_two_advances(self):
        first = self._approved()
        second = self._approved()
        first_cash = self._as(first, self.cash)
        second_cash = self._as(second, self.cash)
        first_cash.action_start_disbursement('UNIQUE-ATTEMPT-1', 'Prepare', 1)
        second_cash.action_start_disbursement('UNIQUE-ATTEMPT-2', 'Prepare', 1)
        first_cash.action_record_disbursement(900000, 'SYNTHETIC-UNIQUE-REFERENCE', fields.Date.today(), 1)
        with self.assertRaises(ValidationError):
            second_cash.action_record_disbursement(900000, 'SYNTHETIC-UNIQUE-REFERENCE', fields.Date.today(), 1)
        self.assertEqual(second.state, 'approved')
        self.assertFalse(second.has_disbursement)

    def test_15_mixed_forbidden_create_batch_is_atomic(self):
        own_trip = self._trip()
        manager_employee = self.env['hr.employee'].search([('user_id', '=', self.manager.id)])
        self.env['hr.employee'].create({
            'name': self.other.name, 'user_id': self.other.id, 'company_id': self.company.id,
            'parent_id': manager_employee.id,
        })
        other_trip = self._new_trip(self.env, {'owner': self.other, 'manager': self.manager})
        model = self._as(self.env['ps.te.trip.advance'], self.owner)
        with self.assertRaises(AccessError):
            model.create([
                {'trip_id': own_trip.id, 'requested_amount': 1000, 'purpose': 'Allowed'},
                {'trip_id': other_trip.id, 'requested_amount': 1000, 'purpose': 'Forbidden'},
            ])
        self.assertFalse(own_trip.advance_id)
        self.assertFalse(model.search([('trip_id', '=', own_trip.id)]))

    def test_16_company_cannot_configure_same_maker_and_checker(self):
        with self.assertRaises(ValidationError):
            self.company.ps_te_cash_operator_id = self.finance

    def test_17_competing_creation_keeps_one_advance_per_trip(self):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            users = {role: env['res.users'].browse(user_id) for role, user_id in self.race_users.items()}
            trip_id = self._new_trip(env, users).id
            cr.commit()
        context = {'allowed_company_ids': [self.race_company]}
        vals = {'trip_id': trip_id, 'requested_amount': 1000, 'purpose': 'Synthetic competing draft'}
        with self.registry.cursor() as first_cr, self.registry.cursor() as second_cr:
            first_env = api.Environment(first_cr, self.race_users['owner'], context)
            second_env = api.Environment(second_cr, self.race_users['owner'], context)
            first_env['ps.te.trip.request'].browse(trip_id).lock_for_update()
            with self.assertRaises(LockError):
                second_env['ps.te.trip.advance'].create(vals)
            second_cr.rollback()
            first_env['ps.te.trip.advance'].create(vals)
            first_cr.commit()
        with self.registry.cursor() as cr:
            env = api.Environment(cr, self.race_users['owner'], context)
            with self.assertRaises(ValidationError):
                env['ps.te.trip.advance'].create(vals)
            self.assertEqual(env['ps.te.trip.advance'].search_count([('trip_id', '=', trip_id)]), 1)

    def test_18_cash_recording_refuses_revoked_finance_authority(self):
        advance = self._approved()
        self.finance.write({'group_ids': [Command.unlink(self.env.ref('ps_expenses.group_ps_te_finance').id)]})
        with self.assertRaises(ValidationError):
            self._as(advance, self.cash).action_record_disbursement(900000, 'REVOKED-FINANCE', fields.Date.today(), 1)
        self.assertFalse(advance.has_disbursement)
