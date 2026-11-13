from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    ps_te_settlement_policy_reference = fields.Char(
        string='Settlement Policy Reference', groups='base.group_system',
        help='Reference/version for recorded funding, expense basis and settlement closure controls.',
    )

    ps_te_expense_policy_reference = fields.Char(
        string='Expense Policy Reference', groups='base.group_system',
        help='Reference/version of the internal expense review policy. This does not establish tax eligibility.',
    )

    ps_te_advance_policy_reference = fields.Char(
        string='Advance Policy Reference', groups='base.group_system',
        help='Reference/version of the approved internal policy. Configure before requesting advances.',
    )
    ps_te_finance_reviewer_id = fields.Many2one(
        'res.users', string='Advance Finance Reviewer', groups='base.group_system',
    )
    ps_te_cash_operator_id = fields.Many2one(
        'res.users', string='Advance Cash Operator', groups='base.group_system',
    )

    @api.constrains('ps_te_finance_reviewer_id', 'ps_te_cash_operator_id')
    def _check_te_advance_roles(self):
        for company in self:
            finance = company.ps_te_finance_reviewer_id
            cash = company.ps_te_cash_operator_id
            if finance and cash and finance == cash:
                raise ValidationError(_('The finance reviewer and cash operator must be different users.'))
            for user, group in (
                (finance, 'ps_expenses.group_ps_te_finance'),
                (cash, 'ps_expenses.group_ps_te_cash'),
            ):
                if user and (not user.active or company not in user.company_ids or not user.has_group(group)):
                    raise ValidationError(_('Advance officers must be active company members with the matching role.'))
