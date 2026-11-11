# -*- coding: utf-8 -*-
"""Gán TK trả hàng khách (Nợ 521 / Có 131) từ cấu hình công ty."""

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    cost_center_id = fields.Many2one(
        "ps.vn.accounting.cost.center",
        string="Cost Center",
        check_company=True,
        ondelete="restrict",
        domain="[('company_id', '=', company_id), ('enabled', '=', True)]",
    )

    @api.onchange("cost_center_id")
    def _onchange_cost_center_id(self):
        if not self.cost_center_id:
            return
        skip_types = ("line_section", "line_subsection", "line_note")
        lines = (self.invoice_line_ids | self.line_ids).filtered(
            lambda line: line.display_type not in skip_types and not line.cost_center_id
        )
        lines.cost_center_id = self.cost_center_id

    def _fill_missing_cost_centers(self):
        """Gán cost center của chứng từ cho line còn trống (kể cả line tự tạo lúc post)."""
        skip_types = ("line_section", "line_subsection", "line_note")
        for move in self:
            if not move.cost_center_id:
                continue
            lines = (move.line_ids | move.invoice_line_ids).filtered(
                lambda line: line.display_type not in skip_types and not line.cost_center_id
            )
            if lines:
                lines.cost_center_id = move.cost_center_id

    def _get_sales_return_accounts(self):
        """Return (debit 521, credit 131), mapped by fiscal position."""
        self.ensure_one()
        company = self.company_id
        debit_account = company._get_sales_return_debit_account()
        credit_account = company._get_sales_return_credit_account()
        fiscal_pos = self.fiscal_position_id
        if fiscal_pos:
            if debit_account:
                debit_account = fiscal_pos.map_account(debit_account)
            if credit_account:
                credit_account = fiscal_pos.map_account(credit_account)
        return debit_account, credit_account

    def _apply_sales_return_accounts(self):
        """Replace product/receivable accounts on draft customer credit notes."""
        refunds = self.filtered(lambda move: move.move_type == "out_refund" and move.state == "draft")
        for move in refunds:
            debit_account, credit_account = move._get_sales_return_accounts()
            for line in move.line_ids:
                if line.display_type == "product" and debit_account and line.account_id != debit_account:
                    line.account_id = debit_account
                elif line.display_type == "payment_term" and credit_account and line.account_id != credit_account:
                    line.account_id = credit_account

    def _reverse_moves(self, default_values_list=None, cancel=False):
        if cancel:
            lines = self.mapped("line_ids")
            if lines:
                lines.remove_move_reconcile()
        reverse_moves = super()._reverse_moves(default_values_list=default_values_list, cancel=False)
        reverse_moves._apply_sales_return_accounts()
        if cancel:
            reverse_moves.with_context(move_reverse_cancel=True)._post(soft=False)
        return reverse_moves

    def action_switch_move_type(self):
        res = super().action_switch_move_type()
        self._apply_sales_return_accounts()
        return res

    def _post(self, soft=True):
        self.filtered(lambda move: move.move_type == "out_refund" and move.state == "draft")._apply_sales_return_accounts()
        self._fill_missing_cost_centers()
        return super()._post(soft=soft)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    cost_center_id = fields.Many2one(
        "ps.vn.accounting.cost.center",
        string="Cost Center",
        check_company=True,
        ondelete="restrict",
        domain="[('company_id', '=', company_id), ('enabled', '=', True)]",
        index=True,
    )

    def _compute_account_id(self):
        super()._compute_account_id()
        for line in self:
            move = line.move_id
            if (
                not move
                or not move.company_id
                or move.move_type != "out_refund"
                or line.display_type not in ("product", "payment_term")
            ):
                continue
            debit_account, credit_account = move._get_sales_return_accounts()
            if line.display_type == "product" and debit_account:
                line.account_id = debit_account
            elif line.display_type == "payment_term" and credit_account:
                line.account_id = credit_account
