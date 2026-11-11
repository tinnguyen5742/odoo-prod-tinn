# -*- coding: utf-8 -*-
"""Wizard in báo cáo tài chính."""

from odoo import api, fields, models

from ..models.financial_report_engine import FinancialReportEngine


class PsFinancialReportWizard(models.TransientModel):
    _name = "ps.financial.report.wizard"
    _description = "Financial Report Wizard"

    x_template_id = fields.Many2one(
        "ps.financial.report.template",
        string="Mẫu báo cáo",
        required=True,
        default=lambda self: self._default_template(),
    )
    x_company_id = fields.Many2one(
        "res.company",
        string="Công ty",
        required=True,
        default=lambda self: self.env.company,
    )
    x_date_from = fields.Date(
        string="Từ ngày",
        required=True,
        default=lambda self: self._default_date_from(),
    )
    x_date_to = fields.Date(
        string="Đến ngày",
        required=True,
        default=lambda self: fields.Date.today(),
    )

    @api.model
    def _default_template(self):
        return self.env["ps.financial.report.template"].search(
            [("x_code", "=", "TT99-BCDKT")], limit=1
        )

    @api.model
    def _default_date_from(self):
        from datetime import date
        today = fields.Date.today()
        return date(today.year, 1, 1)

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref(
            "ps_vn_accounting.action_report_financial_tt99_bcdkt"
        ).report_action(self)

    def _get_report_lines(self):
        """Trả về danh sách dòng báo cáo đã tính toán."""
        self.ensure_one()
        engine = FinancialReportEngine(
            self.env,
            self.x_company_id.id,
            self.x_date_from,
            self.x_date_to,
        )
        return engine.evaluate_template(self.x_template_id)
