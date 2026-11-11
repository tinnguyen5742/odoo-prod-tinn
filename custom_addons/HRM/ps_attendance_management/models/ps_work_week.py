from datetime import timedelta
from odoo import api, fields, models


class PsWorkWeek(models.Model):
    _name = 'ps.work.week'
    _description = 'Work Week'
    _rec_name = 'x_name'
    _order = 'x_year desc, x_week_no desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    x_name = fields.Char(
        string='Name',
        compute='_compute_x_name',
        store=True,
        index=True,
    )
    x_year = fields.Integer(
        string='Year',
        required=True,
        index=True,
    )
    x_week_no = fields.Integer(
        string='Week Number',
        required=True,
    )
    x_date_from = fields.Date(
        string='Date From',
        required=True,
    )
    x_date_to = fields.Date(
        string='Date To',
        required=True,
    )
    x_company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)

    _week_year_unique = models.Constraint(
        "UNIQUE(x_year, x_week_no, x_company_id)",
        "A week already exists for this year.",
    )

    @api.depends('x_year', 'x_week_no')
    def _compute_x_name(self):
        for rec in self:
            # Format: Tuần 1 (02/09 - 08/09/2026)
            date_from_str = fields.Date.to_string(rec.x_date_from) if rec.x_date_from else ''
            date_to_str = fields.Date.to_string(rec.x_date_to) if rec.x_date_to else ''
            # Convert yyyy-mm-dd -> dd/mm/yyyy
            def _fmt(date_str):
                if not date_str:
                    return ''
                parts = date_str.split('-')
                if len(parts) == 3:
                    return f'{parts[2]}/{parts[1]}/{parts[0]}'
                return date_str
            rec.x_name = 'Tuần %(week)s (%(date_from)s - %(date_to)s)' % {
                'week': rec.x_week_no,
                'date_from': _fmt(date_from_str),
                'date_to': _fmt(date_to_str),
            }

    @api.model
    def _generate_weeks_for_year(self, year, company_id=None):
        """Sinh các bản ghi tuần theo chuẩn ISO cho năm được chỉ định, giữ nguyên các tuần đã có"""
        if company_id is None:
            company_id = self.env.company.id
        jan_4 = fields.Date.from_string(f'{year}-01-04')
        week1_monday = jan_4 - timedelta(days=jan_4.weekday())
        existing_week_nos = set(
            self.search([('x_year', '=', year), ('x_company_id', '=', company_id)]).mapped('x_week_no')
        )
        week_no = 1
        while True:
            monday = week1_monday + timedelta(weeks=week_no - 1)
            sunday = monday + timedelta(days=6)
            # Stop when we clearly passed the year, but ensure last year week is included
            if monday.year > year and week_no > 1:
                break
            # Only create weeks that belong to the target year
            if monday.year == year or (sunday.year == year and monday.year < year):
                if week_no not in existing_week_nos:
                    self.create({
                        'x_year': year,
                        'x_week_no': week_no,
                        'x_date_from': monday,
                        'x_date_to': sunday,
                        'x_company_id': company_id,
                    })
                week_no += 1
            else:
                break
        return True

    @api.model
    def _get_or_generate_week(self, year, week_no, company_id=None):
        """Return a week record for the given year/week, generating weeks if needed."""
        if company_id is None:
            company_id = self.env.company.id
        week = self.search([
            ('x_year', '=', year),
            ('x_week_no', '=', week_no),
            ('x_company_id', '=', company_id),
        ], limit=1)
        if not week:
            self._generate_weeks_for_year(year, company_id)
            week = self.search([
                ('x_year', '=', year),
                ('x_week_no', '=', week_no),
                ('x_company_id', '=', company_id),
            ], limit=1)
        return week

    @api.model
    def _get_current_week(self, company_id=None):
        """Return the ISO week record for today."""
        today = fields.Date.today()
        iso = today.isocalendar()
        return self._get_or_generate_week(iso.year, iso.week, company_id)
