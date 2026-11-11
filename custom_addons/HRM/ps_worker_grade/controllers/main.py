# CSV export for salary matrix
import csv
import io

from odoo import http
from odoo.http import request


class PsWorkerSalaryController(http.Controller):

    @http.route('/ps_worker_grade/salary/export/<int:salary_id>', type='http', auth='user')
    def export_salary_matrix(self, salary_id, **kwargs):
        # Xuất thang lương ra CSV
        salary = request.env['ps.worker.salary'].browse(salary_id)
        if not salary.exists():
            return request.not_found()

        output = io.StringIO()
        writer = csv.writer(output)

        # Header info
        writer.writerow(['WORKER GRADE - SOCIAL INSURANCE SALARY MATRIX'])
        writer.writerow([
            'Name:', salary.x_name,
            'Year:', salary.x_year,
            'Profession:', salary.x_profession_id.x_name,
        ])
        writer.writerow([])

        lines = salary.x_line_ids.sorted(lambda l: l.x_sequence)
        if not lines:
            writer.writerow(['No data'])
            output.seek(0)
            return self._csv_response(output, salary)

        # Header rows
        header1 = ['Description / Grade']
        header2 = ['']
        for line in lines:
            header1.extend([line.x_grade_id.x_name, '', ''])
            header2.extend(['Basic', 'KPI', 'Income'])
        writer.writerow(header1)
        writer.writerow(header2)

        # Basic rows
        base_rows = [
            ('Basic Salary', lambda l: l.x_basic_salary),
            ('KPI Amount', lambda l: l.x_kpi_amount),
            ('Hourly Basic', lambda l: l.x_hourly_basic),
            ('Hourly KPI', lambda l: l.x_hourly_kpi),
            ('Hourly Total', lambda l: l.x_hourly_total),
        ]
        for label, getter in base_rows:
            row = [label]
            for line in lines:
                row.extend([getter(line), '', ''])
            writer.writerow(row)

        # Shift rows
        shift_types = request.env['ps.worker.shift.type'].search([])
        for shift_type in shift_types:
            for suffix, getter in [
                (' - Basic', lambda s: s.x_basic_amount),
                (' - KPI', lambda s: s.x_kpi_amount),
                (' - Total', lambda s: s.x_total),
            ]:
                row = [f'{shift_type.x_name}{suffix}']
                for line in lines:
                    shift = line.x_shift_line_ids.filtered(
                        lambda s: s.x_shift_type_id == shift_type)
                    vals = ['', '', '']
                    vals[0 if 'Basic' in suffix else 1 if 'KPI' in suffix else 2] = getter(shift) if shift else 0.0
                    row.extend(vals)
                writer.writerow(row)

        # Total rows
        total_rows = [
            ('26 Days - Basic', lambda l: l.x_total_26_basic),
            ('26 Days - KPI', lambda l: l.x_total_26_kpi),
            ('26 Days - Total', lambda l: l.x_total_26_total),
            ('28 Days - Basic', lambda l: l.x_total_28_basic),
            ('28 Days - KPI', lambda l: l.x_total_28_kpi),
            ('28 Days - Total', lambda l: l.x_total_28_total),
        ]
        for label, getter in total_rows:
            row = [label]
            for line in lines:
                row.extend(['', '', getter(line)])
            writer.writerow(row)

        # Allowance rows
        allowances = request.env['ps.worker.allowance'].search([])
        for allowance in allowances:
            row = [allowance.x_name]
            for line in lines:
                al = line.x_allowance_line_ids.filtered(
                    lambda a: a.x_allowance_id == allowance)
                row.extend(['', '', al.x_amount if al else 0.0])
            writer.writerow(row)

        # Final totals
        final_rows = [
            ('Total Allowance', lambda l: l.x_total_allowance),
            ('Total 26 Days Income', lambda l: l.x_total_26_income),
            ('Total 28 Days Income', lambda l: l.x_total_28_income),
        ]
        for label, getter in final_rows:
            row = [label]
            for line in lines:
                row.extend(['', '', getter(line)])
            writer.writerow(row)

        output.seek(0)
        return self._csv_response(output, salary)

    def _csv_response(self, output, salary):
        # Trả về response CSV
        filename = f'salary_matrix_{salary.x_year}_{salary.x_profession_id.x_code}.csv'
        return request.make_response(
            output.getvalue().encode('utf-8-sig'),
            headers=[
                ('Content-Type', 'text/csv; charset=utf-8'),
                ('Content-Disposition', f'attachment; filename="{filename}"'),
            ],
        )
