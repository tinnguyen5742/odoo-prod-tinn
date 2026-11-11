# -*- coding: utf-8 -*-
"""Report renderer cho BCDKT TT99."""

from odoo import api, models


class ReportFinancialTT99BCDKT(models.AbstractModel):
    _name = "report.ps_vn_accounting.report_financial_tt99_bcdkt"
    _description = "BCDKT TT99 Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["ps.financial.report.wizard"].browse(docids)
        doc = docs[0] if docs else self.env["ps.financial.report.wizard"]
        lines = doc._get_report_lines() if doc else []
        return {
            "doc_ids": docids,
            "doc_model": "ps.financial.report.wizard",
            "docs": docs,
            "doc": doc,
            "lines": lines,
            "data": data,
        }
