from odoo import models


def _as_html_preview(action):
    """Đổi action in PDF thành xem trước HTML trong client."""
    if isinstance(action, dict) and action.get("type") == "ir.actions.report":
        action = dict(action)
        action["report_type"] = "qweb-html"
        action["close_on_report_download"] = False
    return action


class AccountCommonReport(models.TransientModel):
    """Thêm Preview cho Trial Balance, GL, P&L, BCDKT, Tax, Aged Partner, ..."""

    _inherit = "account.common.report"

    def action_preview_report(self):
        """Mở xem trước HTML, dùng cùng dữ liệu với nút Print."""
        self.ensure_one()
        return _as_html_preview(self.check_report())


class AccountDaybookReport(models.TransientModel):
    _inherit = "account.daybook.report"

    def action_preview_report(self):
        self.ensure_one()
        return _as_html_preview(self.check_report())


class AccountCashbookReport(models.TransientModel):
    _inherit = "account.cashbook.report"

    def action_preview_report(self):
        self.ensure_one()
        return _as_html_preview(self.check_report())


class AccountBankbookReport(models.TransientModel):
    _inherit = "account.bankbook.report"

    def action_preview_report(self):
        self.ensure_one()
        return _as_html_preview(self.check_report())


class PsFinancialReportWizard(models.TransientModel):
    _inherit = "ps.financial.report.wizard"

    def action_preview_report(self):
        self.ensure_one()
        return _as_html_preview(self.action_print_pdf())
