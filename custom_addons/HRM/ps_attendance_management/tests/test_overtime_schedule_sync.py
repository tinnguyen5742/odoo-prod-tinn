from odoo.tests.common import TransactionCase


class TestOvertimeScheduleSync(TransactionCase):
    """Kiểm tra đồng bộ thông tin tăng ca giữa phiếu đăng ký và lịch phân ca."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref('base.main_company')
        cls.department = cls.env['hr.department'].create({
            'name': 'Test Department',
            'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Employee',
            'company_id': cls.company.id,
            'department_id': cls.department.id,
        })
        # Ca làm 08:00-17:00, tă ca ngoài khung giờ này để qua kiểm tra overlap
        cls.shift = cls.env['ps.work.shift'].create({
            'x_shift_code': 'TEST',
            'x_shift_name': 'Test Shift',
            'x_start_time': 8.0,
            'x_end_time': 17.0,
            'x_has_lunch_break': False,
            'company_id': cls.company.id,
        })
        cls.date = '2026-08-21'
        cls.slot = cls.env['ps.work.shift.slot'].create({
            'x_employee_id': cls.employee.id,
            'x_date': cls.date,
            'x_shift_id': cls.shift.id,
            'x_company_id': cls.company.id,
        })

    def _create_overtime_registration(self, time_from, time_to):
        """Tạo phiếu tăng ca nháp với 1 dòng chi tiết."""
        reg = self.env['ps.overtime.registration'].create({
            'x_date_from': self.date,
            'x_date_to': self.date,
            'x_time_from': time_from,
            'x_time_to': time_to,
            'x_company_id': self.company.id,
            'x_state': 'draft',
        })
        reg.x_line_ids = [(0, 0, {
            'x_employee_id': self.employee.id,
            'x_date_from': self.date,
            'x_date_to': self.date,
            'x_shift_id': self.shift.id,
            'x_time_from': time_from,
            'x_time_to': time_to,
        })]
        return reg

    def test_confirm_updates_slot(self):
        """Xác nhận phiếu tăng ca phải cập nhật lịch phân ca."""
        reg = self._create_overtime_registration(18.0, 20.0)
        self.assertEqual(self.slot.x_overtime_hours, 0.0)

        reg.action_confirm()

        self.assertEqual(reg.x_state, 'confirmed')
        self.assertEqual(self.slot.x_overtime_from, 18.0)
        self.assertEqual(self.slot.x_overtime_to, 20.0)
        self.assertEqual(self.slot.x_overtime_hours, 2.0)

    def test_draft_clears_slot(self):
        """Đưa phiếu đã xác nhận về nháp phải xóa thông tin tăng ca trên lịch phân ca."""
        reg = self._create_overtime_registration(18.0, 20.0)
        reg.action_confirm()
        self.assertEqual(self.slot.x_overtime_hours, 2.0)

        reg.action_draft()

        self.assertEqual(reg.x_state, 'draft')
        self.assertEqual(self.slot.x_overtime_from, 0.0)
        self.assertEqual(self.slot.x_overtime_to, 0.0)
        self.assertEqual(self.slot.x_overtime_hours, 0.0)

    def test_redraft_edit_reconfirm_updates_slot(self):
        """Xác nhận -> nháp -> sửa giờ -> xác nhận lại phải cập nhật lịch phân ca theo giờ mới."""
        reg = self._create_overtime_registration(18.0, 20.0)
        reg.action_confirm()
        self.assertEqual(self.slot.x_overtime_to, 20.0)

        reg.action_draft()
        reg.x_line_ids.write({'x_time_to': 21.5})
        reg.x_time_to = 21.5
        reg.action_confirm()

        self.assertEqual(self.slot.x_overtime_from, 18.0)
        self.assertEqual(self.slot.x_overtime_to, 21.5)
        self.assertEqual(self.slot.x_overtime_hours, 3.5)

    def test_multiple_confirmed_aggregate(self):
        """Nhiều phiếu tăng ca đã xác nhận cùng ngày được tổng hợp trên lịch phân ca."""
        reg1 = self._create_overtime_registration(18.0, 19.0)
        reg1.action_confirm()

        reg2 = self._create_overtime_registration(20.0, 21.0)
        reg2.action_confirm()

        self.assertEqual(self.slot.x_overtime_from, 18.0)
        self.assertEqual(self.slot.x_overtime_to, 21.0)
        self.assertEqual(self.slot.x_overtime_hours, 2.0)

    def test_unlink_confirmed_line_updates_slot(self):
        """Xóa dòng tăng ca của phiếu đã xác nhận phải cập nhật lại lịch phân ca."""
        reg = self._create_overtime_registration(18.0, 20.0)
        reg.action_confirm()
        self.assertEqual(self.slot.x_overtime_hours, 2.0)

        reg.x_line_ids.unlink()

        self.assertEqual(self.slot.x_overtime_from, 0.0)
        self.assertEqual(self.slot.x_overtime_to, 0.0)
        self.assertEqual(self.slot.x_overtime_hours, 0.0)
