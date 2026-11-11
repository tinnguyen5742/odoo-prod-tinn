from odoo import api, fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    @api.depends_context('company', 'formatted_display_name', 'show_account_code')
    @api.depends('code', 'name')
    def _compute_display_name(self):
        if self.env.context.get('show_account_code'):
            for account in self:
                account.display_name = (
                    f"{account.code} {account.name}" if account.code else account.name
                )
            return
        return super()._compute_display_name()


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    is_operating = fields.Boolean(
        string='Operating',
        default=True,
        help='Tick if this workshop/department is currently operating.',
    )
    is_workshop = fields.Boolean(
        string='Workshop',
        default=False,
        help='Tick if this department is a workshop/factory.',
    )
    workshop_code = fields.Char(
        string='Workshop Code',
        size=10,
        help='Short workshop code, e.g. A. Prefixes become LSXA, YCA, DNA.',
    )
    lsx_prefix = fields.Char(
        string='LSX Prefix',
        size=16,
        help='Prefix for manufacturing orders (Lệnh sản xuất), e.g. LSXA.',
    )
    yc_prefix = fields.Char(
        string='YC Prefix',
        size=16,
        help='Prefix for requests (Yêu cầu), e.g. YCA.',
    )
    dn_prefix = fields.Char(
        string='DN Prefix',
        size=16,
        help='Prefix for proposals (Đề nghị), e.g. DNA.',
    )
    material_cost_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Raw Material Cost Account',
        check_company=True,
        context={'show_account_code': True},
        default=lambda self: self._ps_default_material_cost_account(),
        help='Account used for raw material costs (Chi phí NVL). Defaults to account 621.',
    )
    wip_account_id = fields.Many2one(
        comodel_name='account.account',
        string='WIP Account',
        check_company=True,
        context={'show_account_code': True},
        default=lambda self: self._ps_default_wip_account(),
        help='Account used for work in progress (Tài khoản dở dang). Defaults to account 154.',
    )
    material_warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Default Materials Warehouse',
        check_company=True,
        default=lambda self: self._ps_default_warehouse(),
        help='Default warehouse for raw materials. Defaults to the company warehouse in Inventory.',
    )
    finished_warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Default Finished Goods Warehouse',
        check_company=True,
        default=lambda self: self._ps_default_warehouse(),
        help='Default warehouse for finished goods. Defaults to the company warehouse in Inventory.',
    )

    @api.model
    def _ps_get_account_by_code_prefix(self, code_prefix):
        return self.env['account.account'].with_company(self.env.company).search(
            [
                ('code', '=like', f'{code_prefix}%'),
                ('company_ids', 'in', self.env.company.ids),
            ],
            limit=1,
            order='code',
        )

    @api.model
    def _ps_default_material_cost_account(self):
        account = self._ps_get_account_by_code_prefix('621')
        if not account:
            account = self.env['account.account'].with_company(self.env.company).search(
                [('account_type', '=', 'expense_direct_cost')],
                limit=1,
                order='code',
            )
        return account or self.env.company.expense_account_id

    @api.model
    def _ps_default_wip_account(self):
        company = self.env.company
        if 'account_production_wip_account_id' in company._fields and company.account_production_wip_account_id:
            return company.account_production_wip_account_id
        return self._ps_get_account_by_code_prefix('154')

    @api.model
    def _ps_default_warehouse(self):
        return self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)],
            limit=1,
            order='sequence,id',
        )

    @api.model
    def _ps_normalize_prefix(self, value):
        return (value or '').strip().upper() or False

    @api.model
    def _ps_apply_workshop_code_prefixes(self, vals):
        if 'workshop_code' in vals:
            vals['workshop_code'] = self._ps_normalize_prefix(vals.get('workshop_code'))
        code = vals.get('workshop_code')
        if not code:
            return
        vals.setdefault('lsx_prefix', f'LSX{code}')
        vals.setdefault('yc_prefix', f'YC{code}')
        vals.setdefault('dn_prefix', f'DN{code}')

    @api.model
    def _ps_apply_account_warehouse_defaults(self, vals):
        if not vals.get('material_cost_account_id'):
            account = self._ps_default_material_cost_account()
            if account:
                vals['material_cost_account_id'] = account.id
        if not vals.get('wip_account_id'):
            account = self._ps_default_wip_account()
            if account:
                vals['wip_account_id'] = account.id
        if not vals.get('material_warehouse_id'):
            warehouse = self._ps_default_warehouse()
            if warehouse:
                vals['material_warehouse_id'] = warehouse.id
        if not vals.get('finished_warehouse_id'):
            warehouse = self._ps_default_warehouse()
            if warehouse:
                vals['finished_warehouse_id'] = warehouse.id

    @api.onchange('workshop_code')
    def _onchange_workshop_code(self):
        code = self._ps_normalize_prefix(self.workshop_code)
        self.workshop_code = code
        if code:
            self.lsx_prefix = f'LSX{code}'
            self.yc_prefix = f'YC{code}'
            self.dn_prefix = f'DN{code}'

    @api.onchange('lsx_prefix', 'yc_prefix', 'dn_prefix')
    def _onchange_workshop_prefixes(self):
        self.lsx_prefix = self._ps_normalize_prefix(self.lsx_prefix)
        self.yc_prefix = self._ps_normalize_prefix(self.yc_prefix)
        self.dn_prefix = self._ps_normalize_prefix(self.dn_prefix)

    @api.onchange('is_workshop')
    def _onchange_is_workshop(self):
        if not self.is_workshop:
            return
        if not self.material_cost_account_id:
            self.material_cost_account_id = self._ps_default_material_cost_account()
        if not self.wip_account_id:
            self.wip_account_id = self._ps_default_wip_account()
        if not self.material_warehouse_id:
            self.material_warehouse_id = self._ps_default_warehouse()
        if not self.finished_warehouse_id:
            self.finished_warehouse_id = self._ps_default_warehouse()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._ps_apply_workshop_code_prefixes(vals)
            self._ps_apply_account_warehouse_defaults(vals)
            for fname in ('lsx_prefix', 'yc_prefix', 'dn_prefix'):
                if fname in vals:
                    vals[fname] = self._ps_normalize_prefix(vals.get(fname))
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        self._ps_apply_workshop_code_prefixes(vals)
        for fname in ('lsx_prefix', 'yc_prefix', 'dn_prefix'):
            if fname in vals:
                vals[fname] = self._ps_normalize_prefix(vals.get(fname))
        return super().write(vals)
