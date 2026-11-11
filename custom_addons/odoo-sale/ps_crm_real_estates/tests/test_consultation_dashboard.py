from datetime import datetime

from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestConsultationDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env['res.partner'].create({'name': 'Consultation Owner'})
        cls.property = cls.env['property.property'].create({
            'name': 'Consultation Property',
            'owner_partner_id': cls.owner.id,
        })
        cls.salesperson = new_test_user(
            cls.env, login='consultation_salesperson',
            groups='sales_team.group_sale_salesman',
        )
        cls.lead = cls.env['crm.lead'].create([{
            'name': 'Property Consultation',
            'property_id': cls.property.id,
            'user_id': cls.salesperson.id,
        }])
        cls.result = cls.env['crm.lead.consultation.result'].create({
            'name': 'Consultation Test Result',
        })

    def _create_call(self, start_date=False):
        return self.env['crm.lead.consultation.call'].create({
            'lead_id': self.lead.id,
            'start_date': start_date,
            'result_id': self.result.id,
        })

    def test_latest_call_uses_start_time(self):
        latest_call = self._create_call('2026-11-06 10:30:00')
        self._create_call('2026-11-06 09:30:00')
        self._create_call()
        self.assertEqual(self.lead.latest_consultation_call_id, latest_call)
        self.assertEqual(
            self.lead.latest_consultation_start_date, datetime(2026, 11, 6, 10, 30),
        )
        self.assertEqual(self.lead.latest_consultation_result_id, self.result)
        self.assertEqual(self.lead.consultation_status, 'done')

    def test_equal_start_times_use_latest_created_call(self):
        self._create_call('2026-11-06 10:30:00')
        latest_call = self._create_call('2026-11-06 10:30:00')
        self.assertEqual(self.lead.latest_consultation_call_id, latest_call)

    def test_undated_calls_are_excluded(self):
        self._create_call()
        self.assertFalse(self.lead.latest_consultation_call_id)
        self.assertFalse(self.lead.latest_consultation_start_date)
        dated_call = self._create_call('2026-11-06 10:30:00')
        self.assertEqual(self.lead.latest_consultation_call_id, dated_call)
        dated_call.start_date = False
        self.assertFalse(self.lead.latest_consultation_call_id)
        self.assertFalse(self.lead.latest_consultation_start_date)

    def test_date_changes_and_deletion_refresh_latest_call(self):
        first_call = self._create_call('2026-11-06 09:30:00')
        second_call = self._create_call('2026-11-06 10:30:00')
        self.assertEqual(self.lead.latest_consultation_call_id, second_call)
        first_call.start_date = '2026-11-06 11:30:00'
        self.assertEqual(self.lead.latest_consultation_call_id, first_call)
        first_call.unlink()
        self.assertEqual(self.lead.latest_consultation_call_id, second_call)
        self.assertEqual(
            self.lead.latest_consultation_start_date, datetime(2026, 11, 6, 10, 30),
        )
        second_call.unlink()
        self.assertFalse(self.lead.latest_consultation_call_id)

    def test_dashboard_follows_owner_and_result_changes(self):
        latest_call = self._create_call('2026-11-06 10:30:00')
        self.assertEqual(self.lead.consultation_owner_id, self.owner)
        self.assertEqual(self.lead.latest_consultation_result_id, self.result)
        new_owner = self.env['res.partner'].create({'name': 'New Consultation Owner'})
        self.property.owner_partner_id = new_owner
        latest_call.result_id = False
        self.assertEqual(self.lead.consultation_owner_id, new_owner)
        self.assertFalse(self.lead.latest_consultation_result_id)

    def test_dashboard_respects_crm_access(self):
        self._create_call('2026-11-06 10:30:00')
        dashboard_domain = [
            ('id', '=', self.lead.id),
            ('latest_consultation_call_id', '!=', False),
        ]
        leads = self.env['crm.lead'].with_user(self.salesperson)
        self.assertEqual(leads.search(dashboard_domain).ids, self.lead.ids)
        self.lead.user_id = self.env.user
        self.assertFalse(leads.search(dashboard_domain))
