# Worker salary matrix
from odoo import api, fields, models


class PsWorkerSalary(models.Model):
    # Thang lương bậc thợ
    _name = 'ps.worker.salary'
    _description = 'Worker Salary Matrix'
    _rec_name = 'x_name'
    _order = 'x_year desc, x_profession_id, id'

    x_name = fields.Char(
        string='Name',
        required=True,
    )
    x_year = fields.Integer(
        string='Year',
        required=True,
        default=lambda self: fields.Date.today().year,
    )
    x_profession_id = fields.Many2one(
        'ps.worker.profession',
        string='Profession',
        required=True,
        ondelete='cascade',
    )
    x_active = fields.Boolean(
        string='Active',
        default=True,
    )
    x_note = fields.Text(
        string='Notes',
    )
    x_line_ids = fields.One2many(
        'ps.worker.salary.line',
        'x_salary_id',
        string='Salary Lines',
    )

    def action_generate_lines(self):
        # Sinh dòng lương từ danh sách bậc thợ đang hoạt động
        for salary in self:
            grades = self.env['ps.worker.grade'].search([
                ('x_profession_id', '=', salary.x_profession_id.id),
                ('x_active', '=', True),
            ])
            existing = salary.x_line_ids.mapped('x_grade_id').ids
            vals = []
            for grade in grades:
                if grade.id not in existing:
                    formula = self.env['ps.worker.salary.formula'].sudo()._get_formula(
                        salary.x_profession_id, grade.x_job_id)
                    vals.append({
                        'x_salary_id': salary.id,
                        'x_grade_id': grade.id,
                        'x_formula_id': formula.id if formula else False,
                    })
            if vals:
                self.env['ps.worker.salary.line'].create(vals)

    def action_export_csv(self):
        # Xuất thang lương ra file CSV
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': f'/ps_worker_grade/salary/export/{self.id}',
        }


class PsWorkerSalaryLine(models.Model):
    # Dòng chi tiết thang lương
    _name = 'ps.worker.salary.line'
    _description = 'Worker Salary Line'
    _order = 'x_sequence, id'

    x_salary_id = fields.Many2one(
        'ps.worker.salary',
        string='Salary Matrix',
        required=True,
        ondelete='cascade',
    )
    x_grade_id = fields.Many2one(
        'ps.worker.grade',
        string='Grade',
        required=True,
    )
    x_formula_id = fields.Many2one(
        'ps.worker.salary.formula',
        string='Formula',
        help='Salary formula used for calculation',
    )
    x_sequence = fields.Integer(
        related='x_grade_id.x_sequence',
        string='Sequence',
        store=True,
    )

    x_basic_salary = fields.Float(
        string='Basic Salary (LCB)',
        required=True,
        default=0.0,
    )
    x_kpi_amount = fields.Float(
        string='KPI Amount',
        required=True,
        default=0.0,
    )

    x_hourly_basic = fields.Float(
        string='Hourly Basic',
        compute='_compute_all',
        store=True,
    )
    x_hourly_kpi = fields.Float(
        string='Hourly KPI',
        compute='_compute_all',
        store=True,
    )
    x_hourly_total = fields.Float(
        string='Hourly Total',
        compute='_compute_all',
        store=True,
    )

    x_shift_line_ids = fields.One2many(
        'ps.worker.salary.line.shift',
        'x_salary_line_id',
        string='Shift Lines',
    )

    x_allowance_line_ids = fields.One2many(
        'ps.worker.salary.line.allowance',
        'x_salary_line_id',
        string='Allowance Lines',
    )

    x_total_26_basic = fields.Float(
        string='26 Days Basic',
        compute='_compute_all',
        store=True,
    )
    x_total_26_kpi = fields.Float(
        string='26 Days KPI',
        compute='_compute_all',
        store=True,
    )
    x_total_26_total = fields.Float(
        string='26 Days Total',
        compute='_compute_all',
        store=True,
    )
    x_total_28_basic = fields.Float(
        string='28 Days Basic',
        compute='_compute_all',
        store=True,
    )
    x_total_28_kpi = fields.Float(
        string='28 Days KPI',
        compute='_compute_all',
        store=True,
    )
    x_total_28_total = fields.Float(
        string='28 Days Total',
        compute='_compute_all',
        store=True,
    )

    x_working_days = fields.Integer(
        string='Working Days',
        compute='_compute_all',
        store=True,
    )

    x_total_allowance = fields.Float(
        string='Total Allowance',
        compute='_compute_all',
        store=True,
    )

    x_total_26_income = fields.Float(
        string='Total 26 Days Income',
        compute='_compute_all',
        store=True,
    )
    x_total_28_income = fields.Float(
        string='Total 28 Days Income',
        compute='_compute_all',
        store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        # Tạo dòng lương và sinh ca/phụ cấp mặc định
        records = super().create(vals_list)
        for record in records:
            record._ensure_default_shifts()
            record._ensure_default_allowances()
        return records

    def _ensure_default_shifts(self):
        # Sinh ca làm việc mặc định từ bậc thợ hoặc công thức lương
        self.ensure_one()
        if not self.x_formula_id or self.x_shift_line_ids:
            return
        shift_env = self.env['ps.worker.salary.line.shift']

        grade_shifts = self.x_grade_id.x_shift_ids
        if grade_shifts:
            for gs in grade_shifts:
                if gs.x_count:
                    shift_env.create({
                        'x_salary_line_id': self.id,
                        'x_shift_type_id': gs.x_shift_type_id.id,
                        'x_count': gs.x_count,
                    })
            return

        grade = self.x_grade_id
        if grade and grade.x_employment_type == 'probation':
            probation_shift = self.x_formula_id.x_probation_shift_type_id
            if probation_shift:
                shift_env.create({
                    'x_salary_line_id': self.id,
                    'x_shift_type_id': probation_shift.id,
                    'x_count': grade.x_probation_days or 6,
                })
            return

        counts = self.x_formula_id.get_default_shift_counts()
        for shift_type, count in counts.items():
            if count:
                shift_env.create({
                    'x_salary_line_id': self.id,
                    'x_shift_type_id': shift_type,
                    'x_count': count,
                })

    def _ensure_default_allowances(self):
        # Sinh phụ cấp mặc định từ công thức lương
        self.ensure_one()
        if not self.x_formula_id or self.x_allowance_line_ids:
            return
        line_env = self.env['ps.worker.salary.line.allowance']
        for allowance in self.x_formula_id.x_allowance_ids:
            line_env.create({
                'x_salary_line_id': self.id,
                'x_allowance_id': allowance.id,
                'x_note': allowance.x_note or '',
            })

    @api.onchange('x_formula_id')
    def _onchange_formula(self):
        # Đồng bộ ca làm việc và phụ cấp khi đổi công thức lương
        for line in self:
            if not line.x_formula_id:
                continue

            grade = line.x_grade_id
            grade_shifts = grade.x_shift_ids if grade else False
            if grade_shifts:
                existing_shifts = line.x_shift_line_ids
                existing_types = existing_shifts.mapped('x_shift_type_id').ids
                for gs in grade_shifts:
                    if gs.x_shift_type_id.id in existing_types:
                        shift = existing_shifts.filtered(
                            lambda s: s.x_shift_type_id == gs.x_shift_type_id)
                        shift.x_count = gs.x_count
                    elif gs.x_count:
                        self.env['ps.worker.salary.line.shift'].new({
                            'x_salary_line_id': line.id,
                            'x_shift_type_id': gs.x_shift_type_id.id,
                            'x_count': gs.x_count,
                        })
                for shift in existing_shifts:
                    if shift.x_shift_type_id.id not in grade_shifts.mapped('x_shift_type_id').ids:
                        shift.x_count = 0
            elif grade and grade.x_employment_type == 'probation':
                probation_shift = line.x_formula_id.x_probation_shift_type_id
                if probation_shift:
                    existing = line.x_shift_line_ids.filtered(
                        lambda s: s.x_shift_type_id == probation_shift)
                    days = grade.x_probation_days or 6
                    if existing:
                        existing.x_count = days
                    else:
                        self.env['ps.worker.salary.line.shift'].new({
                            'x_salary_line_id': line.id,
                            'x_shift_type_id': probation_shift.id,
                            'x_count': days,
                        })
            else:
                counts = line.x_formula_id.get_default_shift_counts()
                existing_shifts = line.x_shift_line_ids
                for shift in existing_shifts:
                    if shift.x_shift_type_id.id in counts:
                        shift.x_count = counts[shift.x_shift_type_id.id]
                existing_types = existing_shifts.mapped('x_shift_type_id').ids
                for shift_type, count in counts.items():
                    if shift_type not in existing_types and count:
                        self.env['ps.worker.salary.line.shift'].new({
                            'x_salary_line_id': line.id,
                            'x_shift_type_id': shift_type,
                            'x_count': count,
                        })

            existing_allowance_ids = line.x_allowance_line_ids.mapped('x_allowance_id').ids
            for allowance in line.x_formula_id.x_allowance_ids:
                if allowance.id not in existing_allowance_ids:
                    self.env['ps.worker.salary.line.allowance'].new({
                        'x_salary_line_id': line.id,
                        'x_allowance_id': allowance.id,
                        'x_note': allowance.x_note or '',
                    })

    @api.depends(
        'x_basic_salary', 'x_kpi_amount', 'x_formula_id',
        'x_shift_line_ids.x_count', 'x_shift_line_ids.x_shift_type_id',
        'x_shift_line_ids.x_basic_amount', 'x_shift_line_ids.x_kpi_amount',
        'x_allowance_line_ids.x_amount',
    )
    def _compute_all(self):
        # Tính toán tất cả các chỉ tiêu lương
        for line in self:
            formula = line.x_formula_id
            divisor = formula.x_kpi_divisor if formula else 11.0

            line.x_hourly_basic = line.x_basic_salary / 26.0 / 8.0
            line.x_hourly_kpi = line.x_kpi_amount / 26.0 / divisor if divisor else 0.0
            line.x_hourly_total = line.x_hourly_basic + line.x_hourly_kpi

            shifts = line.x_shift_line_ids
            total_26_basic = 0.0
            total_26_kpi = 0.0
            sunday_basic = 0.0
            sunday_kpi = 0.0
            working_days = 0
            for shift in shifts:
                working_days += shift.x_count
                if shift.x_shift_type_id.x_is_sunday:
                    sunday_basic += shift.x_basic_amount
                    sunday_kpi += shift.x_kpi_amount
                else:
                    total_26_basic += shift.x_basic_amount
                    total_26_kpi += shift.x_kpi_amount

            line.x_working_days = working_days
            line.x_total_26_basic = total_26_basic
            line.x_total_26_kpi = total_26_kpi
            line.x_total_26_total = total_26_basic + total_26_kpi

            line.x_total_28_basic = total_26_basic + sunday_basic * 2
            line.x_total_28_kpi = total_26_kpi + sunday_kpi * 2
            line.x_total_28_total = line.x_total_28_basic + line.x_total_28_kpi

            line.x_total_allowance = sum(line.x_allowance_line_ids.mapped('x_amount'))

            line.x_total_26_income = line.x_total_26_total + line.x_total_allowance
            line.x_total_28_income = line.x_total_28_total + line.x_total_allowance
