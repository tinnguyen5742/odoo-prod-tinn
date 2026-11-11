# -*- coding: utf-8 -*-
"""Sổ Transaction All (VN): cặp Nợ/Có từ account.move.line đã posted."""

import base64
import io
from datetime import datetime

from odoo import api, fields, models
from odoo.tools import float_is_zero, html2plaintext


class GlTransactionAll(models.Model):
    _name = "gl.transaction.all"
    _description = "GL Transaction ALL"
    _order = "date desc, move_name desc, id desc"
    _rec_name = "move_name"
    _check_company_auto = True

    _SKIP_DISPLAY_TYPES = ("line_section", "line_subsection", "line_note")

    # Liên kết kỹ thuật (debit line giữ move_line_id để cột NOT NULL cũ còn hợp lệ)
    move_line_id = fields.Many2one(
        "account.move.line",
        string="Journal Item",
        index=True,
        ondelete="cascade",
        check_company=True,
    )
    debit_move_line_id = fields.Many2one(
        "account.move.line",
        string="Debit Journal Item",
        index=True,
        ondelete="cascade",
        check_company=True,
    )
    credit_move_line_id = fields.Many2one(
        "account.move.line",
        string="Credit Journal Item",
        index=True,
        ondelete="cascade",
        check_company=True,
    )
    move_id = fields.Many2one(
        "account.move",
        string="Journal Entry",
        required=True,
        index=True,
        ondelete="cascade",
        check_company=True,
    )
    date = fields.Date(string="Date", required=True, index=True)
    journal_id = fields.Many2one(
        "account.journal",
        string="Journal",
        required=True,
        index=True,
        check_company=True,
    )
    move_name = fields.Char(string="Document Number", index=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer/Vendor",
        index=True,
    )
    cost_center_id = fields.Many2one(
        "ps.vn.accounting.cost.center",
        string="Cost Center",
        index=True,
        check_company=True,
        ondelete="restrict",
    )
    account_id = fields.Many2one(
        "account.account",
        string="Account",
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    debit_account_id = fields.Many2one(
        "account.account",
        string="Debit Account",
        required=True,
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    credit_account_id = fields.Many2one(
        "account.account",
        string="Credit Account",
        required=True,
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    amount = fields.Monetary(
        string="Amount",
        currency_field="company_currency_id",
    )
    description = fields.Char(string="Description")
    company_currency_id = fields.Many2one("res.currency", string="Company Currency")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    move_type = fields.Selection(related="move_id.move_type", store=True)

    _debit_credit_line_unique = models.Constraint(
        "UNIQUE (debit_move_line_id, credit_move_line_id)",
        "Each debit/credit pair can only appear once in Transaction All.",
    )

    def init(self):
        """Nâng cấp schema cũ rồi backfill bút toán posted chưa có trên sổ."""
        cr = self.env.cr
        cr.execute(
            "ALTER TABLE gl_transaction_all DROP CONSTRAINT IF EXISTS gl_transaction_all_move_line_unique"
        )
        cr.execute(
            """
            ALTER TABLE gl_transaction_all
                ALTER COLUMN move_line_id DROP NOT NULL,
                ALTER COLUMN account_id DROP NOT NULL
            """
        )
        cr.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'gl_transaction_all'
                  AND column_name = 'debit_account_id'
            )
            """
        )
        if cr.fetchone()[0]:
            cr.execute(
                """
                DELETE FROM gl_transaction_all
                WHERE debit_account_id IS NULL
                   OR credit_account_id IS NULL
                """
            )

        cr.execute(
            """
            SELECT DISTINCT am.id
            FROM account_move am
            WHERE am.state = 'posted'
              AND EXISTS (
                  SELECT 1 FROM account_move_line aml
                  WHERE aml.move_id = am.id
                    AND aml.account_id IS NOT NULL
                    AND COALESCE(aml.display_type, '') NOT IN (
                        'line_section', 'line_subsection', 'line_note'
                    )
              )
              AND NOT EXISTS (
                  SELECT 1 FROM gl_transaction_all gl
                  WHERE gl.move_id = am.id
              )
            """
        )
        move_ids = [row[0] for row in cr.fetchall()]
        Move = self.env["account.move"]
        batch_size = 200
        for index in range(0, len(move_ids), batch_size):
            self._sync_from_moves(Move.browse(move_ids[index:index + batch_size]))

    def _get_sync_lines(self, moves):
        return moves.line_ids.filtered(
            lambda line: line.display_type not in self._SKIP_DISPLAY_TYPES and line.account_id
        )

    def _iter_debit_credit_pairs(self, lines):
        """Ghép line Nợ với line Có theo số tiền còn lại (waterfall)."""
        if not lines:
            return
        rounding = lines[0].company_currency_id.rounding or 0.01
        debit_queue = [
            [line, line.debit]
            for line in lines
            if not float_is_zero(line.debit, precision_rounding=rounding)
        ]
        credit_queue = [
            [line, line.credit]
            for line in lines
            if not float_is_zero(line.credit, precision_rounding=rounding)
        ]
        debit_index = 0
        credit_index = 0
        while debit_index < len(debit_queue) and credit_index < len(credit_queue):
            debit_line, debit_remain = debit_queue[debit_index]
            credit_line, credit_remain = credit_queue[credit_index]
            amount = min(debit_remain, credit_remain)
            if not float_is_zero(amount, precision_rounding=rounding):
                yield debit_line, credit_line, amount
            debit_remain -= amount
            credit_remain -= amount
            if float_is_zero(debit_remain, precision_rounding=rounding):
                debit_index += 1
            else:
                debit_queue[debit_index][1] = debit_remain
            if float_is_zero(credit_remain, precision_rounding=rounding):
                credit_index += 1
            else:
                credit_queue[credit_index][1] = credit_remain

    def _pair_description(self, move, debit_line, credit_line):
        candidates = (
            debit_line.name,
            credit_line.name,
            move.ref,
            html2plaintext(move.narration or "") if move.narration else "",
            move.name,
        )
        for candidate in candidates:
            text = (candidate or "").strip()
            if text and text != "/":
                return text
        return ""

    def _prepare_vals_from_pair(self, move, debit_line, credit_line, amount):
        """Map 1 cặp Nợ/Có sang vals Transaction All (định dạng VN)."""
        partner = debit_line.partner_id or credit_line.partner_id or move.partner_id
        cost_center = (
            debit_line.cost_center_id
            or credit_line.cost_center_id
            or move.cost_center_id
        )
        return {
            "move_line_id": debit_line.id,
            "debit_move_line_id": debit_line.id,
            "credit_move_line_id": credit_line.id,
            "move_id": move.id,
            "date": move.date or debit_line.date,
            "journal_id": move.journal_id.id,
            "move_name": move.name or debit_line.move_name,
            "partner_id": partner.id,
            "cost_center_id": cost_center.id,
            "account_id": debit_line.account_id.id,
            "debit_account_id": debit_line.account_id.id,
            "credit_account_id": credit_line.account_id.id,
            "amount": amount,
            "description": self._pair_description(move, debit_line, credit_line),
            "company_currency_id": move.company_currency_id.id,
            "company_id": move.company_id.id,
        }

    def _prepare_vals_from_move(self, move):
        lines = self._get_sync_lines(move).sorted(lambda line: (line.sequence, line.id))
        return [
            self._prepare_vals_from_pair(move, debit_line, credit_line, amount)
            for debit_line, credit_line, amount in self._iter_debit_credit_pairs(lines)
        ]

    @api.model
    def _prepare_vals_from_aml(self, aml):
        """Giữ API cũ: map 1 AML thành cặp nếu tìm được đối ứng cùng số tiền."""
        move = aml.move_id
        lines = self._get_sync_lines(move).sorted(lambda line: (line.sequence, line.id))
        for debit_line, credit_line, amount in self._iter_debit_credit_pairs(lines):
            if aml in (debit_line, credit_line):
                return self._prepare_vals_from_pair(move, debit_line, credit_line, amount)
        return {}

    @api.model
    def _sync_from_moves(self, moves):
        """Tạo lại cặp Nợ/Có của các account.move đã posted."""
        self = self.sudo()
        posted_moves = moves.filtered(lambda move: move.state == "posted")
        if not posted_moves:
            return self.browse()

        existing = self.search([("move_id", "in", posted_moves.ids)])
        if existing:
            existing.unlink()

        vals_to_create = []
        for move in posted_moves:
            vals_to_create.extend(self._prepare_vals_from_move(move))
        if vals_to_create:
            return self.create(vals_to_create)
        return self.browse()

    @api.model
    def _unlink_from_moves(self, moves):
        """Xóa snapshot khi chứng từ ra khỏi sổ (draft / cancel)."""
        if moves:
            self.sudo().search([("move_id", "in", moves.ids)]).unlink()

    def _get_export_records(self):
        if self:
            records = self
        else:
            domain = list(self.env.context.get("active_domain") or [])
            records = self.search(domain)
        return records.sorted(lambda rec: (rec.date or fields.Date.today(), rec.move_name or "", rec.id))

    def _account_export_label(self, account):
        if not account:
            return ""
        if account.code:
            return f"{account.code} {account.name}"
        return account.name or ""

    def _generate_xlsx(self, records):
        import xlsxwriter  # noqa: PLC0415

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False})
        sheet = workbook.add_worksheet("Nhat ky chung")

        title_format = workbook.add_format({
            "bold": True,
            "font_size": 14,
            "font_color": "#1F4E79",
        })
        subtitle_format = workbook.add_format({"font_size": 10, "italic": True})
        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#1F4E79",
            "font_color": "#FFFFFF",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
        })
        date_format = workbook.add_format({"num_format": "dd/mm/yyyy", "border": 1, "valign": "vcenter"})
        text_format = workbook.add_format({"border": 1, "valign": "vcenter"})
        amount_format = workbook.add_format({
            "num_format": "#,##0.00",
            "border": 1,
            "valign": "vcenter",
            "align": "right",
        })
        total_label_format = workbook.add_format({
            "bold": True,
            "border": 1,
            "align": "right",
            "bg_color": "#D6EAF8",
        })
        total_amount_format = workbook.add_format({
            "bold": True,
            "num_format": "#,##0.00",
            "border": 1,
            "align": "right",
            "bg_color": "#D6EAF8",
        })

        company = records[:1].company_id or self.env.company
        dates = [rec.date for rec in records if rec.date]
        period = ""
        if dates:
            period = "%s → %s" % (
                min(dates).strftime("%d/%m/%Y"),
                max(dates).strftime("%d/%m/%Y"),
            )

        sheet.merge_range(0, 0, 0, 7, company.display_name or "", title_format)
        sheet.merge_range(1, 0, 1, 7, "TRANSACTION ALL - NHẬT KÝ CHUNG", title_format)
        sheet.merge_range(
            2,
            0,
            2,
            7,
            "Kỳ: %s    Ngày xuất: %s"
            % (period or "-", fields.Date.context_today(self).strftime("%d/%m/%Y")),
            subtitle_format,
        )

        headers = [
            "Ngày",
            "Số chứng từ",
            "Khách hàng/Nhà cung cấp",
            "Cost Center",
            "Tài khoản nợ",
            "Tài khoản có",
            "Số tiền",
            "Diễn giải",
        ]
        header_row = 4
        for col, header in enumerate(headers):
            sheet.write(header_row, col, header, header_format)

        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 1, 18)
        sheet.set_column(2, 2, 32)
        sheet.set_column(3, 3, 24)
        sheet.set_column(4, 5, 28)
        sheet.set_column(6, 6, 16)
        sheet.set_column(7, 7, 42)
        sheet.set_row(header_row, 22)
        sheet.freeze_panes(header_row + 1, 0)
        sheet.autofilter(header_row, 0, header_row + max(len(records), 1), 7)

        total_amount = 0.0
        for index, rec in enumerate(records):
            row = header_row + 1 + index
            if rec.date:
                sheet.write_datetime(
                    row, 0, datetime.combine(rec.date, datetime.min.time()), date_format
                )
            else:
                sheet.write_blank(row, 0, None, date_format)
            sheet.write(row, 1, rec.move_name or "", text_format)
            sheet.write(row, 2, rec.partner_id.display_name or "", text_format)
            sheet.write(row, 3, rec.cost_center_id.display_name or "", text_format)
            sheet.write(row, 4, self._account_export_label(rec.debit_account_id), text_format)
            sheet.write(row, 5, self._account_export_label(rec.credit_account_id), text_format)
            sheet.write_number(row, 6, rec.amount or 0.0, amount_format)
            sheet.write(row, 7, rec.description or "", text_format)
            total_amount += rec.amount or 0.0

        total_row = header_row + 1 + len(records)
        sheet.merge_range(total_row, 0, total_row, 5, "Tổng cộng", total_label_format)
        sheet.write_number(total_row, 6, total_amount, total_amount_format)
        sheet.write(total_row, 7, "", total_label_format)

        workbook.close()
        return output.getvalue()

    def action_export_xlsx(self):
        records = self._get_export_records()
        content = self._generate_xlsx(records)
        filename = "Transaction_All_%s.xlsx" % fields.Date.context_today(self).strftime("%Y%m%d")
        attachment = self.env["ir.attachment"].sudo().create({
            "name": filename,
            "datas": base64.b64encode(content),
            "res_model": self._name,
            "type": "binary",
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s/%s?download=true" % (attachment.id, filename),
            "target": "self",
        }


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        self.env["gl.transaction.all"]._sync_from_moves(posted)
        return posted

    def button_draft(self):
        res = super().button_draft()
        self.env["gl.transaction.all"]._unlink_from_moves(self)
        return res
