import json

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from .test_advance import TestTripAdvance
from .test_settlement import TestSettlement


@tagged('post_install', '-at_install')
class TestTripAmendment(TransactionCase):
    def test_r6_compiled_manager_review_control_and_denied_role_counterparts(self):
        from lxml import etree
        from odoo.tools.safe_eval import safe_eval
        trip = self._trip()
        request = self._request(trip)
        view_id = self.env.ref('ps_expenses.view_amendment_form').id
        for role in ('owner', 'finance', 'cash', 'other', 'manager'):
            actor = request.with_user(self.users[role]).with_context(allowed_company_ids=[self.company])
            arch = etree.fromstring(actor.get_view(view_id, 'form')['arch'])
            controls = arch.xpath('//button[@name="action_open_review"]')
            self.assertEqual(len(controls), 1 if role == 'manager' else 0, role)
            if role == 'manager':
                self.assertFalse(safe_eval(controls[0].get('invisible'),
                    {'state': request.state, 'manager_id': request.manager_id.id, 'uid': self.users[role].id}))
                action = actor.action_open_review()
                self.assertEqual(action['context']['default_expected_revision'], request.revision)
                self.assertEqual(action['context']['default_amendment_id'], request.id)
            else:
                with self.assertRaises(AccessError):
                    actor.action_open_review()
        other = self.users['other']
        other.group_ids += self.env.ref('ps_expenses.group_ps_te_trip_manager')
        unassigned = request.with_user(other).with_context(allowed_company_ids=[self.company])
        arch = etree.fromstring(unassigned.get_view(view_id, 'form')['arch'])
        controls = arch.xpath('//button[@name="action_open_review"]')
        self.assertEqual(len(controls), 1)
        self.assertTrue(safe_eval(controls[0].get('invisible'),
            {'state': request.state, 'manager_id': request.manager_id.id, 'uid': other.id}))
        with self.assertRaises(AccessError):
            unassigned.action_open_review()

    def test_r6_manager_wizard_review_keeps_existing_finance_sources_held(self):
        from odoo.tests import Form
        settlement, report, advance = TestSettlement._case(self.env, self.users)
        trip = settlement.trip_id
        original = (trip.purpose, trip.destination, advance.cash_event_id, report.revision)
        request = self._request(trip, destination='R6 new synthetic destination')
        manager = request.with_user(self.users['manager'])
        action = manager.action_open_review()
        with Form(self.env['ps.te.amendment.wizard'].with_user(self.users['manager']).with_context(
                **action['context'], allowed_company_ids=[self.company]),
                view='ps_expenses.view_amendment_wizard') as wizard:
            wizard.decision = 'approved'
            wizard.reason = 'R6 independent manager reapproval, finance still separate'
        wizard.record.action_apply()
        self.assertEqual(request.state, 'finance')
        self.assertTrue(trip.correction_hold)
        self.assertEqual((trip.purpose, trip.destination, advance.cash_event_id, report.revision), original)
        self.assertEqual(request.decided_by_id, self.users['manager'])
        self.assertEqual(trip.case_status, 'open')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company, actors = TestSettlement._fixture(cls.env)
        cls.users = {role: cls.env['res.users'].browse(uid) for role, uid in actors.items()}

    def _trip(self):
        return TestTripAdvance._new_trip(self.env, self.users)

    def _request(self, trip, **changes):
        values = {'trip_id': trip.id, 'purpose': trip.purpose + ' amended',
                  'destination': trip.destination, 'start_date': str(trip.start_date),
                  'end_date': str(trip.end_date), 'reason': 'Synthetic amendment',
                  'expected_revision': trip.preparing_revision}
        values.update(changes)
        return self.env['ps.te.trip.amendment'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company]).create(values)

    def test_01_owner_proposal_freezes_original_and_holds_downstream(self):
        trip = self._trip()
        old = (trip.purpose, trip.submission_receipt, trip.preparing_revision)
        request = self._request(trip)
        self.assertEqual((trip.purpose, trip.submission_receipt, trip.preparing_revision), old)
        self.assertTrue(trip.correction_hold)
        self.assertTrue(trip.amendment_hold)
        with self.assertRaises(ValidationError):
            trip.action_no_advance()
        with self.assertRaises(ValidationError):
            self._request(trip)
        self.assertEqual(json.loads(request.original_facts)['purpose'], old[0])

    def test_02_fresh_manager_approval_applies_unfunded_trip_only(self):
        trip = self._trip()
        old_receipt = trip.submission_receipt
        old_events = trip.event_ids.ids
        amendment = self._request(trip, destination='Synthetic amended place')
        manager = amendment.with_user(self.users['manager'])
        manager.action_decide('approved', 'Synthetic fresh manager approval', 1)
        self.assertEqual(amendment.state, 'applied')
        self.assertEqual(trip.destination, 'Synthetic amended place')
        self.assertNotEqual(trip.submission_receipt, old_receipt)
        self.assertEqual(trip.state, 'approved')
        self.assertFalse(trip.correction_hold)
        self.assertTrue(set(old_events).issubset(trip.event_ids.ids))
        before = trip.event_ids.ids
        manager.action_decide('approved', 'Synthetic fresh manager approval', 1)
        self.assertEqual(trip.event_ids.ids, before)
        self.assertEqual(amendment.decided_by_id, self.users['manager'])

    def test_03_manager_refusal_keeps_original_authority_and_history(self):
        trip = self._trip()
        before = (trip.purpose, trip.submission_receipt, trip.preparing_revision)
        request = self._request(trip)
        request.with_user(self.users['manager']).action_decide('refused', 'Synthetic refusal', 1)
        self.assertEqual(request.state, 'refused')
        self.assertEqual((trip.purpose, trip.submission_receipt, trip.preparing_revision), before)
        self.assertFalse(trip.correction_hold)
        self.assertTrue(request.original_facts)

    def test_04_existing_financial_sources_require_separate_revalidation(self):
        settlement, _, _ = TestSettlement._case(self.env, self.users)
        trip = settlement.trip_id
        old = trip.purpose
        request = self._request(trip)
        request.with_user(self.users['manager']).action_decide('approved', 'Synthetic manager only', 1)
        self.assertEqual(request.state, 'finance')
        self.assertEqual(trip.purpose, old)
        self.assertTrue(trip.correction_hold)
        with self.assertRaises(ValidationError):
            settlement.action_submit(settlement.revision)
        self.assertFalse(request.applied_at)

    def test_05_wrong_actor_forgery_and_audit_mutation_are_denied(self):
        trip = self._trip()
        request = self._request(trip)
        with self.assertRaises(AccessError):
            request.action_decide('approved', 'Owner cannot approve', 1)
        with self.assertRaises(AccessError):
            request.with_user(self.users['other']).read(['purpose'])
        with self.assertRaises(AccessError):
            request.with_user(self.users['finance']).read(['original_facts'])
        with self.assertRaises(AccessError):
            request.write({'state': 'applied'})
        with self.assertRaises(AccessError):
            request.unlink()
        with self.assertRaises(AccessError):
            trip.write({'amendment_id': False})

    def test_06_no_change_bad_dates_stale_revision_and_revocation_fail(self):
        trip = self._trip()
        with self.assertRaises(ValidationError):
            self._request(trip, purpose=trip.purpose)
        with self.assertRaises(ValidationError):
            self._request(trip, end_date='2020-01-01')
        with self.assertRaises(ValidationError):
            self._request(trip, expected_revision=999)
        request = self._request(trip)
        with self.assertRaises(ValidationError):
            request.with_user(self.users['manager']).action_decide('approved', 'Stale', 2)
        trip.sudo().employee_id.parent_id.active = False
        with self.assertRaises(AccessError):
            request.with_user(self.users['manager']).action_decide('approved', 'Revoked', 1)

    def test_07_default_context_cannot_forge_approval_or_other_owner(self):
        trip = self._trip()
        model = self.env['ps.te.trip.amendment'].with_user(self.users['owner']).with_context(
            allowed_company_ids=[self.company], default_state='applied', default_owner_id=self.users['other'].id)
        vals = {'trip_id': trip.id, 'purpose': 'Synthetic new purpose', 'destination': trip.destination,
                'start_date': str(trip.start_date), 'end_date': str(trip.end_date),
                'reason': 'Synthetic default forgery', 'expected_revision': trip.preparing_revision}
        request = model.create(vals)
        self.assertEqual(request.state, 'manager')
        self.assertEqual(request.owner_id, self.users['owner'])
        action = request.with_user(self.users['manager']).action_open_review()
        self.assertEqual(action['context']['default_amendment_id'], request.id)
