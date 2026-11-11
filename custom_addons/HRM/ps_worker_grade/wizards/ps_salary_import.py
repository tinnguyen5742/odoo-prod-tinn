# Import salary matrix from Excel
import base64
import io

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PsWorkerSalaryImport(models.TransientModel):
    # Wizard import thang lương từ Excel
    _name = 'ps.worker.salary.import'
    _description = 'Import Salary Matrix from Excel'

    x_salary_id = fields.Many2one(
        'ps.worker.salary',
        string='Salary Matrix',
        required=True,
        default=lambda self: self.env.context.get('active_id'),
    )
    x_file = fields.Binary(
        string='Excel File',
        required=True,
    )
    x_filename = fields.Char(
        string='Filename',
    )
    x_sheet_name = fields.Char(
        string='Sheet Name',
        default='TP.KP - BAC THO 2025',
    )

    # Excel column mapping: (grade_name, lcb_col, kpi_col)
    _GRADE_COLS = [
        ('Thử việc', 4, 5),   # E, F
        ('Bậc 0', 6, 7),      # G, H
        ('Bậc 1', 9, 10),     # J, K
        ('Bậc 1.5', 12, 13),  # M, N
        ('Bậc 2', 15, 16),    # P, Q
        ('Bậc 2.5', 18, 19),  # S, T
        ('Bậc 3', 21, 22),    # V, W
        ('Bậc 3.5', 24, 25),  # Y, Z
        ('Bậc 4', 27, 28),    # AB, AC
        ('Bậc 4.5', 30, 31),  # AE, AF
        ('Bậc 5', 33, 34),    # AH, AI
        ('Bậc 5.5', 36, 37),  # AK, AL
        ('Bậc 6', 39, 40),    # AN, AO
    ]

    def action_import(self):
        # Xử lý import Excel
        self.ensure_one()
        if not self.x_file:
            raise UserError(_('Please select an Excel file.'))

        try:
            import openpyxl
        except ImportError:
            raise UserError(_('Please install openpyxl to use this feature.'))

        data = base64.b64decode(self.x_file)
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        if self.x_sheet_name not in wb.sheetnames:
            raise UserError(_('Sheet "%s" not found in workbook.') % self.x_sheet_name)
        ws = wb[self.x_sheet_name]

        created = 0
        current_profession = None

        profession_env = self.env['ps.worker.profession']
        grade_env = self.env['ps.worker.grade']
        job_env = self.env['hr.job']
        line_env = self.env['ps.worker.salary.line']

        # Remove existing lines
        self.x_salary_id.x_line_ids.unlink()

        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True):
            col_a = row[0]
            col_b = row[1]
            col_d = row[3]

            # Update profession from column A
            if col_a and isinstance(col_a, str) and col_a.strip():
                prof_name = col_a.strip().split('\n')[0].strip()
                current_profession = profession_env.search([('x_name', '=', prof_name)], limit=1)
                if not current_profession:
                    current_profession = profession_env.create({
                        'x_code': self._make_code(prof_name),
                        'x_name': prof_name,
                    })

            # Only process LƯƠNG rows
            if not col_d or not isinstance(col_d, str) or 'LƯƠNG' not in col_d.upper():
                continue
            if not current_profession:
                continue

            # Get job from column B
            job = False
            if col_b and isinstance(col_b, str) and col_b.strip():
                job_name = col_b.strip().split('\n')[0].strip()
                job = job_env.search([('name', '=', job_name)], limit=1)
                if not job:
                    job = job_env.create({'name': job_name})

            # Get or create formula
            formula = self.env['ps.worker.salary.formula'].sudo()._get_formula(
                current_profession, job)
            if not formula:
                prof_code = current_profession.x_code or self._make_code(current_profession.x_name)
                job_code = self._make_code(job.name) if job else 'ALL'
                code = f'FML_{prof_code}_{job_code}'[:20]
                formula = self.env['ps.worker.salary.formula'].sudo().search([
                    ('x_code', '=', code),
                ], limit=1)
                if not formula:
                    formula = self.env['ps.worker.salary.formula'].sudo().create({
                        'x_code': code,
                        'x_name': f'Formula {current_profession.x_name} {job.name if job else ""}'.strip(),
                        'x_profession_id': current_profession.id,
                        'x_job_id': job.id if job else False,
                    })
                    self._ensure_formula_shifts(formula)
                    self._ensure_formula_allowances(formula)

            for grade_name, lcb_col, kpi_col in self._GRADE_COLS:
                lcb = row[lcb_col]
                kpi = row[kpi_col]
                if not lcb and not kpi:
                    continue
                try:
                    lcb_val = float(lcb) if lcb else 0.0
                    kpi_val = float(kpi) if kpi else 0.0
                except (ValueError, TypeError):
                    continue

                grade = self._get_or_create_grade(
                    grade_env, current_profession, job, grade_name)

                line_env.create({
                    'x_salary_id': self.x_salary_id.id,
                    'x_grade_id': grade.id,
                    'x_formula_id': formula.id,
                    'x_basic_salary': lcb_val,
                    'x_kpi_amount': kpi_val,
                })
                created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Import Completed'),
                'message': _('Created %s salary lines.') % created,
                'type': 'success',
            },
        }

    def _get_or_create_grade(self, grade_env, profession, job, grade_name):
        # Tìm hoặc tạo bậc thợ
        job_code = self._make_code(job.name) if job else 'ALL'
        grade_code = f'{profession.x_code}_{job_code}_{self._make_code(grade_name)}'[:50]
        grade = grade_env.search([
            ('x_profession_id', '=', profession.id),
            ('x_code', '=', grade_code),
        ], limit=1)
        if grade:
            return grade

        level = self._grade_level(grade_name)
        emp_type = 'probation' if 'Thử việc' in grade_name else 'official'
        probation_days = 6 if 'Thử việc' in grade_name else 0
        grade = grade_env.create({
            'x_code': grade_code,
            'x_name': grade_name,
            'x_profession_id': profession.id,
            'x_job_id': job.id if job else False,
            'x_level': level,
            'x_employment_type': emp_type,
            'x_probation_days': probation_days,
        })
        self._ensure_grade_shifts(grade)
        return grade

    def _ensure_formula_shifts(self, formula):
        # Tạo số ca mặc định cho công thức lương mới
        shift_type_env = self.env['ps.worker.shift.type'].sudo()
        mapping = {'DAY_8H': 13, 'NIGHT': 13, 'SUN_DAY': 1}
        shift_vals = []
        for code, count in mapping.items():
            shift_type = shift_type_env.search([('x_code', '=', code)], limit=1)
            if shift_type:
                shift_vals.append({
                    'x_formula_id': formula.id,
                    'x_shift_type_id': shift_type.id,
                    'x_count': count,
                })
        if shift_vals:
            self.env['ps.worker.salary.formula.shift'].sudo().create(shift_vals)

    def _ensure_formula_allowances(self, formula):
        # Liên kết phụ cấp mặc định cho công thức lương mới
        codes = ['PC_NHA_O', 'PC_DIEN_THOAI', 'PC_NOI_QUY']
        allowances = self.env['ps.worker.allowance'].sudo().search([('x_code', 'in', codes)])
        if allowances:
            formula.sudo().write({'x_allowance_ids': [(6, 0, allowances.ids)]})

    def _ensure_grade_shifts(self, grade):
        # Tạo cấu hình ca mặc định cho bậc thợ mới
        shift_type_env = self.env['ps.worker.shift.type'].sudo()
        grade_shift_env = self.env['ps.worker.grade.shift'].sudo()
        day_12h = shift_type_env.search([('x_code', '=', 'DAY_12H')], limit=1)
        night = shift_type_env.search([('x_code', '=', 'NIGHT')], limit=1)

        if grade.x_employment_type == 'probation':
            if day_12h:
                grade_shift_env.create({
                    'x_grade_id': grade.id,
                    'x_shift_type_id': day_12h.id,
                    'x_count': grade.x_probation_days or 6,
                })
        else:
            shift_vals = []
            if day_12h:
                shift_vals.append({
                    'x_grade_id': grade.id,
                    'x_shift_type_id': day_12h.id,
                    'x_count': 13,
                })
            if night:
                shift_vals.append({
                    'x_grade_id': grade.id,
                    'x_shift_type_id': night.id,
                    'x_count': 13,
                })
            if shift_vals:
                grade_shift_env.create(shift_vals)

    def _make_code(self, name):
        # Tạo mã từ tên có dấu tiếng Việt
        import unicodedata
        import re
        name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
        code = re.sub(r'[^a-zA-Z0-9]+', '_', name).strip('_').upper()[:20]
        return code or 'CODE'

    def _grade_level(self, name):
        # Chuyển tên bậc thành số level
        name = name.strip()
        if 'Thử việc' in name:
            return 0.0
        if name.startswith('Bậc '):
            try:
                return float(name.replace('Bậc ', '').replace(',', '.'))
            except ValueError:
                return 0.0
        return 0.0
