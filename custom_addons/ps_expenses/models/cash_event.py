from decimal import Decimal, InvalidOperation

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class PsTeCashEvent(models.Model):
    _name = 'ps.te.cash.event'
    _description = 'PS T&E Recorded External Cash Movement'
    _rec_name = 'external_reference'

    _reference_unique = models.Constraint('UNIQUE(company_id, external_reference)', 'This cash reference is already recorded in the company.')
    _advance_unique = models.Constraint('UNIQUE(advance_id, kind)', 'This advance movement is already recorded.')
    _settlement_unique = models.Constraint('UNIQUE(settlement_id, kind)', 'This settlement movement is already recorded.')
    _adjustment_unique = models.Constraint('UNIQUE(adjustment_id)', 'This adjustment movement is already recorded.')
    _one_source = models.Constraint('CHECK (num_nonnulls(advance_id, settlement_id, adjustment_id) = 1)', 'A cash event must have exactly one workflow source.')

    trip_id = fields.Many2one('ps.te.trip.request', required=True, readonly=True, ondelete='restrict')
    advance_id = fields.Many2one('ps.te.trip.advance', readonly=True, ondelete='restrict')
    settlement_id = fields.Many2one('ps.te.settlement', readonly=True, ondelete='restrict')
    adjustment_id = fields.Many2one('ps.te.adjustment', readonly=True, ondelete='restrict')
    owner_id = fields.Many2one('res.users', required=True, readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    finance_reviewer_id = fields.Many2one('res.users', required=True, readonly=True)
    cash_operator_id = fields.Many2one('res.users', required=True, readonly=True)
    currency_id = fields.Many2one('res.currency', required=True, readonly=True)
    kind = fields.Selection([('advance', 'Advance Disbursement'), ('topup', 'Employee Top-up'), ('return', 'Employee Return')], required=True, readonly=True)
    amount = fields.Monetary(required=True, readonly=True)
    external_reference = fields.Char(required=True, readonly=True, index=True)
    execution_date = fields.Date(required=True, readonly=True)
    actor_id = fields.Many2one('res.users', required=True, readonly=True)
    recorded_at = fields.Datetime(required=True, readonly=True)
    finance_assignment_valid = fields.Boolean(compute='_compute_assignments', store=True)
    cash_assignment_valid = fields.Boolean(compute='_compute_assignments', store=True)

    @api.depends('company_id.ps_te_finance_reviewer_id', 'company_id.ps_te_cash_operator_id', 'finance_reviewer_id', 'cash_operator_id')
    def _compute_assignments(self):
        for event in self:
            event.finance_assignment_valid = event.finance_reviewer_id == event.company_id.ps_te_finance_reviewer_id
            event.cash_assignment_valid = event.cash_operator_id == event.company_id.ps_te_cash_operator_id

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Cash records are created only by authorized workflow actions.'))

    @api.model
    def _amount(self, value):
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError(_('Enter a positive whole-VND cash amount.'))
        if not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value() or amount > Decimal('99999999999900'):
            raise ValidationError(_('Cash amount is outside the supported whole-VND range.'))
        return float(amount)

    @api.model
    def _record_movement(self, source, kind, amount, reference, date, actor_id=None, recorded_at=None):
        source.ensure_one()
        reference = self.env['ps.te.trip.advance']._text(reference, _('External cash reference'))
        amount = self._amount(amount)
        sources = {'ps.te.trip.advance': 'advance_id', 'ps.te.settlement': 'settlement_id', 'ps.te.adjustment': 'adjustment_id'}
        if source._name not in sources:
            raise ValidationError(_('Unsupported cash source.'))
        field = sources[source._name]
        existing = self.sudo().search([('company_id', '=', source.company_id.id), ('external_reference', '=', reference)], limit=1)
        if existing:
            if existing[field].id == source.id and (existing.kind, existing.amount, existing.execution_date) == (kind, amount, date):
                return existing
            raise ValidationError(_('This external cash reference is already used by another recorded movement.'))
        # Include positive legacy advance facts that predate the registry.
        legacy = self.env['ps.te.trip.advance'].sudo().search([
            ('company_id', '=', source.company_id.id), ('cash_reference', '=', reference),
        ])
        if legacy and not (field == 'advance_id' and legacy.ids == [source.id]):
            raise ValidationError(_('This external cash reference is already recorded on an advance.'))
        safe = self.sudo().with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
        return super(PsTeCashEvent, safe).create({
            field: source.id, 'trip_id': source.trip_id.id, 'owner_id': source.owner_id.id,
            'company_id': source.company_id.id, 'currency_id': source.currency_id.id,
            'finance_reviewer_id': source.finance_reviewer_id.id, 'cash_operator_id': source.cash_operator_id.id,
            'kind': kind, 'amount': amount, 'external_reference': reference, 'execution_date': date,
            'actor_id': actor_id or self.env.uid, 'recorded_at': recorded_at or fields.Datetime.now(),
        })

    def write(self, vals):
        raise AccessError(_('Recorded cash movements cannot be changed.'))

    def unlink(self):
        raise AccessError(_('Recorded cash movements must be retained.'))
