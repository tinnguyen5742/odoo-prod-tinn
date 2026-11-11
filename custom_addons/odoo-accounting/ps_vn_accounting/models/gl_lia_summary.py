# -*- coding: utf-8 -*-
"""Model rỗng lưu chi tiết công nợ (AR/AP) và materialized view tổng hợp theo năm."""

from odoo import models, tools


class GlLiaSummary(models.Model):
    _name = "gl.lia.summary"
    _description = "GL Liability Summary"

    def init(self):
        tools.drop_view_if_exists(self.env.cr, "gl_lia_summary_byyear")
        self.env.cr.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS gl_lia_summary_byyear AS
            SELECT
                ROW_NUMBER() OVER () AS id,
                NULL::BIGINT AS client_id,
                NULL::BIGINT AS company_site_id,
                NULL::BIGINT AS account_id,
                NULL::INT AS fiscal_year,
                0.0::NUMERIC AS total_debit_amount,
                0.0::NUMERIC AS total_credit_amount,
                0.0::NUMERIC AS total_debit_base_amount,
                0.0::NUMERIC AS total_credit_base_amount,
                0::BIGINT AS line_count
            WHERE FALSE
        """)
