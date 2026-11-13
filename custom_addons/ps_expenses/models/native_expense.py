"""Native Expenses is the claim/decision source; PS adds versioned T&E policy.

The object capability is private Python state, not a serializable RPC bypass.
PS report/line records are aggregate identities and readonly projections only.
"""
from odoo import api, fields, models, Command, _
from odoo.exceptions import AccessError, ValidationError


_PS_NATIVE = object()
_CLAIM_MAP = {'description': 'name', 'claimed_amount': 'total_amount_currency', 'expense_date': 'date'}
_DECISION_MAP = {key: 'ps_' + key for key in (
    'decision', 'accepted_amount', 'decision_reason', 'reviewed_revision', 'reviewed_by_id', 'reviewed_at')}


class PsNativeExpense(models.Model):
    _inherit = 'hr.expense'

    @api.model
    def _ps_safe_input_context(self):
        # Report is a route input, never authority. All other PS defaults are
        # generated from the authorized report or declared field defaults.
        return self.with_context({key: value for key, value in self.env.context.items()
            if not key.startswith('default_ps_') or key == 'default_ps_report_id'})

    @api.model
    def _ps_check_input_report(self, report_id):
        if not report_id:
            return
        if type(report_id) is not int or report_id < 1:
            raise AccessError(_('Dữ kiện PS do máy chủ kiểm soát.'))
        report = self.with_user(self.env.uid).sudo(False).env['ps.te.expense.report'].browse(report_id)
        report.check_access('read')
        if not report.exists():
            raise AccessError(_('Dữ kiện PS do máy chủ kiểm soát.'))
        report._assert_viewer()

    @api.model
    def default_get(self, fields_list):
        safe = self._ps_safe_input_context()
        safe._ps_check_input_report(safe.env.context.get('default_ps_report_id'))
        return super(PsNativeExpense, safe).default_get(fields_list)

    def onchange(self, values, field_names, fields_spec):
        safe = self._ps_safe_input_context()
        if self:
            actual = self.with_user(self.env.uid).sudo(False)
            actual.check_access('read')
            for report in actual.ps_report_id:
                safe._ps_check_input_report(report.id)
        # Check both sources, including before the web layer constructs any
        # pseudo-record whose related fields could compute with elevated access.
        safe._ps_check_input_report(safe.env.context.get('default_ps_report_id'))
        safe._ps_check_input_report(values.get('ps_report_id'))
        clean = {key: value for key, value in values.items()
            if not key.startswith('ps_') or key in ('ps_report_id', 'ps_expected_revision')}
        return super(PsNativeExpense, safe).onchange(clean, field_names, fields_spec)

    @api.depends_context('uid', 'allowed_company_ids')
    @api.depends('employee_id', 'product_id', 'date', 'total_amount_currency', 'company_id', 'currency_id')
    def _compute_duplicate_expense_ids(self):
        # Native SQL groups include hidden historical rows, then fail when the
        # many2many checks those rows. Search first as the actual user instead;
        # neither disclose hidden IDs nor open their rules to make the form work.
        visible = self.with_user(self.env.uid).sudo(False)
        for expense in self:
            candidates = visible.browse()
            if (type(expense.id) is int and expense.employee_id and expense.product_id
                    and expense.total_amount_currency):
                candidates = visible.search([
                    ('employee_id', '=', expense.employee_id.id), ('product_id', '=', expense.product_id.id),
                    ('date', '=', expense.date), ('total_amount_currency', '=', expense.total_amount_currency),
                    ('company_id', '=', expense.company_id.id), ('currency_id', '=', expense.currency_id.id)])
            expense.duplicate_expense_ids = candidates if len(candidates) > 1 else False

    @api.depends_context('uid', 'allowed_company_ids')
    @api.depends('attachment_ids', 'attachment_ids.checksum', 'split_expense_origin_id')
    def _compute_same_receipt_expense_ids(self):
        actual = self.with_user(self.env.uid).sudo(False)
        for expense in self:
            candidates = actual.browse()
            if expense.attachment_ids and not expense.split_expense_origin_id:
                files = actual.env['ir.attachment'].search([
                    ('res_model', '=', 'hr.expense'),
                    ('checksum', 'in', expense.attachment_ids.mapped('checksum'))])
                candidates = actual.search([('id', 'in', files.mapped('res_id')), ('id', '!=', expense.id)])
            expense.same_receipt_expense_ids = candidates

    ps_report_id = fields.Many2one('ps.te.expense.report', readonly=True, copy=False, ondelete='restrict', index=True, string='Cơ sở chi phí PS')
    ps_line_id = fields.Many2one('ps.te.expense.line', readonly=True, copy=False, ondelete='restrict', index=True, string='Tham chiếu phiên PS')
    ps_trip_id = fields.Many2one(related='ps_report_id.trip_id', store=True)
    ps_owner_id = fields.Many2one(related='ps_report_id.owner_id', store=True)
    ps_finance_id = fields.Many2one(related='ps_report_id.finance_reviewer_id', store=True)
    ps_finance_valid = fields.Boolean(related='ps_report_id.finance_assignment_valid', store=True)
    ps_revision = fields.Integer(related='ps_report_id.revision', string='Phiên cơ sở PS')
    ps_expected_revision = fields.Integer(default=lambda self: self._ps_default_revision(), readonly=True,
        copy=False, string='Phiên đã thấy khi tạo khoản chi')
    ps_decision = fields.Selection([(key, key.title()) for key in ('pending', 'accepted', 'refused', 'returned')],
        default='pending', readonly=True, copy=False, string='Quyết định PS')
    ps_accepted_amount = fields.Monetary(readonly=True, copy=False, string='Tài chính chấp nhận')
    ps_refused_amount = fields.Monetary(compute='_ps_refused', string='Không chấp nhận')
    ps_decision_reason = fields.Text(readonly=True, copy=False, string='Lý do quyết định PS')
    ps_reviewed_revision = fields.Integer(readonly=True, copy=False, string='Phiên đã quyết định PS')
    ps_reviewed_by_id = fields.Many2one('res.users', readonly=True, copy=False, string='Người quyết định PS')
    ps_reviewed_at = fields.Datetime(readonly=True, copy=False, string='Thời điểm quyết định PS')
    ps_claimed_amount = fields.Monetary(related='total_amount_currency', string='Nhân viên kê khai')
    ps_basis_ready = fields.Boolean(related='ps_report_id.accepted_basis_ready', string='Cơ sở PS đủ điều kiện')
    ps_basis_status = fields.Selection([
        ('native', 'Chi phí Odoo độc lập'), ('current', 'Cơ sở PS hiện hành'),
        ('proposal', 'Phiên điều chỉnh chưa có hiệu lực'), ('historical', 'Phiên PS lịch sử — không cộng lại'),
    ], compute='_ps_basis_status', store=True, string='Hiệu lực phiên PS')
    _ps_line_unique = models.Constraint('UNIQUE(ps_line_id)', 'One native expense is allowed per PS line identity.')

    @api.model
    def _ps_default_revision(self):
        report_id = self.env.context.get('default_ps_report_id')
        if not report_id:
            return 0
        report = self.env['ps.te.expense.report'].browse(report_id)
        report.check_access('read')
        return report.revision

    @api.depends('ps_report_id', 'ps_report_id.trip_id.effective_expense_report_id',
        'ps_report_id.trip_id.expense_report_id', 'ps_report_id.adjustment_id.state')
    def _ps_basis_status(self):
        for expense in self:
            report = expense.ps_report_id
            effective = report.trip_id.effective_expense_report_id or report.trip_id.expense_report_id
            if not report:
                expense.ps_basis_status = 'native'
            elif report.adjustment_id and report.adjustment_id.state not in ('closed', 'withdrawn'):
                expense.ps_basis_status = 'proposal'
            else:
                expense.ps_basis_status = 'current' if report == effective else 'historical'

    @api.depends('total_amount_currency', 'ps_decision', 'ps_reviewed_revision', 'ps_revision', 'ps_accepted_amount')
    def _ps_refused(self):
        for expense in self:
            expense.ps_refused_amount = (expense.total_amount_currency - expense.ps_accepted_amount
                if expense.ps_decision in ('accepted', 'refused') and expense.ps_reviewed_revision == expense.ps_revision else 0)

    @api.model
    def _ps_create_claim(self, report, values):
        safe = self.with_context({key: value for key, value in self.env.context.items() if not key.startswith('default_')})
        category = self.env.ref('ps_expenses.product_ps_native_expense')
        if category.with_company(report.company_id).standard_price or category.supplier_taxes_id:
            raise ValidationError(_('Loại chi phí PS phải không định mức giá và không thuế trong phạm vi demo.'))
        return super(PsNativeExpense, safe.with_context(_ps_native=_PS_NATIVE)).create({
            'name': values['description'], 'date': values['expense_date'], 'total_amount_currency': values['claimed_amount'],
            'product_id': category.id, 'quantity': 1, 'payment_mode': 'own_account', 'tax_ids': [Command.clear()],
            'company_id': report.company_id.id, 'employee_id': report.trip_id.employee_id.id,
            'currency_id': report.currency_id.id, 'manager_id': report.finance_reviewer_id.id,
            'ps_report_id': report.id,
            'ps_expected_revision': report.revision,
        })

    def _ps_update(self, values):
        native = self.sudo().with_context(_ps_native=_PS_NATIVE)
        mapped = {(_CLAIM_MAP | _DECISION_MAP)[key]: value for key, value in values.items()}
        result = super(PsNativeExpense, native).write(mapped)
        decision = values.get('decision')
        if decision == 'pending':
            if native.account_move_id:
                raise ValidationError(_('Không reset hồ sơ đã có bút toán; không thuộc phạm vi demo PS.'))
            native._do_reset_approval()
        elif decision == 'accepted':
            native._do_approve()
        elif decision in ('refused', 'returned'):
            native._do_refuse(values.get('decision_reason') or '')
        return result

    def _ps_submit(self):
        for expense in self:
            native = expense.with_context(_ps_native=_PS_NATIVE)
            super(PsNativeExpense, native).write({'manager_id': expense.ps_report_id.finance_reviewer_id.id})
            super(PsNativeExpense, native).action_submit()

    def _ps_bind_line(self, line):
        self.ensure_one()
        if self.ps_line_id or line.report_id != self.ps_report_id:
            raise ValidationError(_('Liên kết khoản chi native không khớp cơ sở PS.'))
        return super().write({'ps_line_id': line.id})

    def _ps_main_proof(self, attachment):
        self.with_context(_ps_native=_PS_NATIVE)._message_set_main_attachment_id(attachment, force=True)

    @api.model_create_multi
    def create(self, vals_list):
        safe = self._ps_safe_input_context()
        safe._ps_check_input_report(safe.env.context.get('default_ps_report_id'))
        linked = [bool(vals.get('ps_report_id', self.env.context.get('default_ps_report_id'))) for vals in vals_list]
        if not any(linked):
            if any(key.startswith('ps_') and not (key in ('ps_report_id', 'ps_expected_revision') and not value)
                   for vals in vals_list for key, value in vals.items()):
                raise AccessError(_('Dữ kiện PS do máy chủ kiểm soát.'))
            return super(PsNativeExpense, safe).create(vals_list)
        if len(vals_list) != 1:
            raise ValidationError(_('Tạo từng khoản chi PS để kiểm soát đúng phiên cơ sở.'))
        vals = vals_list[0]
        if any(key.startswith('ps_') and key not in ('ps_report_id', 'ps_expected_revision') for key in vals):
            raise AccessError(_('Không tạo sẵn quyết định hoặc liên kết khoản chi PS.'))
        report = self.env['ps.te.expense.report'].browse(vals.get('ps_report_id', self.env.context.get('default_ps_report_id'))).exists()
        report.check_access('write')
        report._assert_actor('owner')
        expected = {'employee_id': report.trip_id.employee_id.id, 'company_id': report.company_id.id,
            'currency_id': report.currency_id.id, 'manager_id': report.finance_reviewer_id.id,
            'product_id': self.env.ref('ps_expenses.product_ps_native_expense').id,
            'payment_mode': 'own_account', 'quantity': 1,
            # Read a fixed own-trip department as server metadata; do not grant
            # the requester access to private Odoo19 employee-version fields.
            'department_id': report.trip_id.employee_id.sudo().department_id.id or False,
            'vendor_id': False, 'payment_method_line_id': False}
        allowed = set(expected) | {'ps_report_id', 'ps_expected_revision', 'name', 'date', 'total_amount_currency', 'total_amount', 'tax_ids'}
        if (set(vals) - allowed or any(key in vals and vals[key] != value for key, value in expected.items())
                or vals.get('tax_ids') and vals['tax_ids'] not in ([[5]], [(5, 0, 0)], [[6, 0, []]], [(6, 0, [])])):
            raise AccessError(_('Không giả phân công, danh mục, tiền tệ hoặc dữ kiện kế toán của khoản chi PS.'))
        amount = vals.get('total_amount_currency')
        if 'total_amount' in vals and vals['total_amount'] != amount:
            raise ValidationError(_('Số kê khai VND không thống nhất.'))
        line_id = report.action_add_line(vals.get('name'), amount, vals.get('date'), vals.get('ps_expected_revision'))
        return self.env['ps.te.expense.line'].browse(line_id).native_expense_id

    def write(self, vals):
        if self.env.context.get('_ps_native') is _PS_NATIVE:
            return super().write(vals)
        if not self.filtered('ps_report_id'):
            vals = {key: value for key, value in vals.items()
                if not (key in ('ps_report_id', 'ps_expected_revision') and not value)}
        if self.filtered('ps_report_id') or any(key.startswith('ps_') for key in vals):
            # Even ordinary claim edits require an explicit versioned PS wizard.
            raise AccessError(_('Dùng thao tác PS có phiên kiểm soát để sửa khoản chi, chứng từ hoặc quyết định.'))
        return super().write(vals)

    def _can_be_autovalidated(self):
        return False if self.ps_report_id else super()._can_be_autovalidated()

    def _get_default_responsible_for_approval(self):
        self.ensure_one()
        if self.ps_report_id:
            return self.ps_report_id.finance_reviewer_id
        return super()._get_default_responsible_for_approval()

    def action_submit(self):
        linked = self.filtered('ps_report_id')
        if linked:
            raise ValidationError(_('Gửi cơ sở qua thao tác PS có phiên đã thấy; không tự lấy phiên mới nhất để gửi.'))
        if self - linked:
            return super(PsNativeExpense, self - linked).action_submit()
        return True

    def _do_approve(self, check=True):
        if self.filtered('ps_report_id') and self.env.context.get('_ps_native') is not _PS_NATIVE:
            raise AccessError(_('Thiếu quyết định PS đúng phiên.'))
        return super()._do_approve(check=check)

    def _check_can_create_move(self):
        if self.filtered('ps_report_id'):
            raise ValidationError(_('PS demo không ghi sổ hoặc tạo thanh toán native; dùng nguồn thu chi PS duy nhất.'))
        return super()._check_can_create_move()

    def action_approve(self):
        if self.filtered('ps_report_id'):
            raise ValidationError(_('Duyệt số chấp nhận qua thao tác PS, không thay số kê khai gốc.'))
        return super().action_approve()

    def action_pay(self):
        if self.filtered('ps_report_id'):
            raise ValidationError(_('PS demo không dùng thanh toán native hoặc giả trạng thái Paid.'))
        return super().action_pay()

    def action_reset(self):
        if self.filtered('ps_report_id'):
            raise ValidationError(_('Rút phiên cơ sở PS có lịch sử; không reset native trực tiếp.'))
        return super().action_reset()

    def action_refuse(self):
        if self.filtered('ps_report_id'):
            raise ValidationError(_('Dùng quyết định từ chối hoặc trả lại PS có lý do và phiên.'))
        return super().action_refuse()

    def action_split_wizard(self):
        if self.filtered('ps_report_id'):
            raise ValidationError(_('Không tách khoản chi PS qua đường native không có phiên kiểm soát.'))
        return super().action_split_wizard()

    def attach_document(self, **kwargs):
        if self.filtered('ps_report_id'):
            raise AccessError(_('Tải chứng từ qua thao tác PS để giữ hash, lịch sử và đúng phiên.'))
        return super().attach_document(**kwargs)

    def copy(self, default=None):
        if self.filtered('ps_report_id'):
            raise AccessError(_('Không nhân bản khoản chi PS.'))
        return super().copy(default)

    def unlink(self):
        if self.filtered('ps_report_id'):
            raise AccessError(_('Giữ nguyên khoản chi PS và lịch sử.'))
        return super().unlink()

    def action_ps_operation(self):
        self.ensure_one()
        self.check_access('read')
        self.ps_report_id._assert_viewer()
        action = self.ps_report_id.action_open_operation()
        action['context'].update(default_line_id=self.ps_line_id.id,
            default_description=self.name, default_amount=self.total_amount_currency, default_expense_date=self.date)
        return action

    def action_ps_basis(self):
        self.ensure_one()
        self.check_access('read')
        self.ps_report_id._assert_viewer()
        return {'type': 'ir.actions.act_window', 'res_model': 'ps.te.expense.report',
            'res_id': self.ps_report_id.id, 'view_mode': 'form'}
