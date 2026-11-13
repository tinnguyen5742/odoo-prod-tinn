from odoo import api, models, _
from odoo.exceptions import AccessError, ValidationError


def checked_records(env, model, docids):
    # Never render a partial authorized subset of a forbidden mixed request.
    if (not isinstance(docids, (list, tuple)) or not docids or len(docids) > 100
            or any(type(value) is not int or value < 1 for value in docids)):
        raise ValidationError(env._('Select between one and 100 report records.'))
    records = env[model].browse(list(dict.fromkeys(docids)))
    records.check_access('read')
    if len(records.exists()) != len(records):
        raise AccessError(env._('A requested report record is unavailable.'))
    return records


class ExpenseSummary(models.AbstractModel):
    _name = 'report.ps_expenses.expense_summary'
    _description = 'Authorized Employee Expense Summary'

    @api.model
    def _get_report_values(self, docids, data=None):
        records = checked_records(self.env, 'ps.te.expense.report', docids)
        for record in records:
            record._assert_viewer()
        return {'doc_ids': records.ids, 'doc_model': records._name, 'docs': records}


class SettlementSummary(models.AbstractModel):
    _name = 'report.ps_expenses.settlement_summary'
    _description = 'Authorized Recorded Settlement Summary'

    @api.model
    def _get_report_values(self, docids, data=None):
        records = checked_records(self.env, 'ps.te.settlement', docids)
        current = {}
        for record in records:
            try:
                record.sudo().trip_id._assert_no_active_correction()
                record._verify_sources()
            except ValidationError:
                current[record.id] = False
            else:
                current[record.id] = not bool(record.sudo().trip_id.latest_completed_adjustment_id)
        # data from the caller cannot replace docs or source-validity flags.
        return {'doc_ids': records.ids, 'doc_model': records._name,
                'docs': records, 'basis_current': current}


class AdjustmentSummary(models.AbstractModel):
    _name = 'report.ps_expenses.adjustment_summary'
    _description = 'Authorized Recorded Financial Adjustment Summary'

    @api.model
    def _get_report_values(self, docids, data=None):
        records = checked_records(self.env, 'ps.te.adjustment', docids)
        return {'doc_ids': records.ids, 'doc_model': records._name, 'docs': records}
