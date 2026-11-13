import logging
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, Command, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_round

_logger = logging.getLogger(__name__)


class Company(models.Model):
    _inherit = "res.company"

    eam_journal_id = fields.Many2one("account.journal", "Nhật ký chi phí EAM", check_company=True,
                                     domain="[('type', '=', 'general')]", groups="account.group_account_manager")
    eam_overhead_account_id = fields.Many2one("account.account", "Chi phí chung bảo trì", check_company=True,
                                              groups="account.group_account_manager")
    eam_labor_clearing_id = fields.Many2one("account.account", "Tài khoản đối ứng giờ công", check_company=True,
                                           groups="account.group_account_manager")

    def _eam_post_entry(self, reference, entry_date, balances):
        self.ensure_one()
        currency = self.currency_id
        lines = [
            Command.create({
                "name": reference, "account_id": account_id,
                "balance": currency.round(balance),
            })
            for account_id, balance in balances.items() if not currency.is_zero(balance)
        ]
        if not lines:
            return self.env["account.move"]
        if not self.eam_journal_id or self.eam_journal_id.type != "general":
            raise UserError(_("Kế toán cần cấu hình nhật ký bút toán tổng hợp EAM cho công ty."))
        if len(lines) < 2:
            raise UserError(_("Kiểm tra lại tài khoản ghi nhận và tài khoản đối ứng chi phí EAM."))
        entry = self.env["account.move"].sudo().with_company(self).create({
            "company_id": self.id, "journal_id": self.eam_journal_id.id,
            "move_type": "entry", "date": entry_date, "ref": reference, "line_ids": lines,
        })
        entry.action_post()
        if entry.state != "posted":
            raise UserError(_("Bút toán EAM chưa được ghi sổ."))
        return entry


class Request(models.Model):
    _inherit = "maintenance.request"

    eam_accounting_mode = fields.Selection([
        ("none", "Theo dõi nội bộ"), ("overhead", "Chi phí chung nhà máy"),
        ("production", "Giá thành lệnh sản xuất"),
    ], string="Hạch toán bảo trì", default="none", required=True, copy=False)
    eam_production_id = fields.Many2one("mrp.production", "Lệnh sản xuất chịu chi phí", check_company=True,
                                         ondelete="restrict", copy=False, index=True)
    eam_posted_entry_id = fields.Many2one("account.move", "Bút toán EAM", check_company=True, ondelete="restrict",
                                           readonly=True, copy=False, groups="account.group_account_readonly,account.group_account_manager")
    eam_capitalized_amount = fields.Monetary("Chi phí chuyển vào giá thành", readonly=True, copy=False)

    @api.constrains("eam_accounting_mode", "eam_production_id", "eam_managed")
    def _check_eam_accounting_mode(self):
        for order in self:
            if order.eam_accounting_mode == "production" and (
                not order.eam_production_id or order.eam_production_id.company_id != order.company_id
            ):
                raise ValidationError(_("Chọn lệnh sản xuất cùng công ty để tính giá thành."))
            if not order.eam_managed and order.eam_accounting_mode != "none":
                raise ValidationError(_("Chỉ lệnh EAM mới được phân loại hạch toán bảo trì."))

    @api.model_create_multi
    def create(self, vals_list):
        protected = {"eam_posted_entry_id", "eam_capitalized_amount"}
        if any(protected.intersection(values) for values in vals_list) or any(
            self.env.context.get("default_" + key) for key in protected
        ):
            raise AccessError(_("Số liệu hạch toán được tạo khi nghiệm thu."))
        if not self.env.su and not self.env.user.has_group("ps_enterprise_asset.group_eam_manager"):
            defaults = self.default_get(["eam_accounting_mode", "eam_production_id"])
            if any(values.get("eam_accounting_mode", defaults.get("eam_accounting_mode", "none")) != "none"
                   or values.get("eam_production_id", defaults.get("eam_production_id")) for values in vals_list):
                raise AccessError(_("Chỉ quản lý EAM được chọn cách hạch toán lệnh."))
        return super().create(vals_list)

    def write(self, vals):
        if {"eam_posted_entry_id", "eam_capitalized_amount"} & vals.keys():
            raise AccessError(_("Số liệu hạch toán được tạo khi nghiệm thu."))
        if {"eam_accounting_mode", "eam_production_id"} & vals.keys():
            if not self.env.su and not self.env.user.has_group("ps_enterprise_asset.group_eam_manager"):
                raise AccessError(_("Chỉ quản lý EAM được chọn cách hạch toán lệnh."))
            if self.filtered(lambda order: order.eam_state in ("done", "cancelled") or order.picking_ids):
                raise UserError(_("Chọn cách hạch toán trước khi lập phiếu vật tư hoặc đóng lệnh."))
        result = super().write(vals)
        if vals.get("eam_state") == "done":
            for order in self.filtered(lambda order: order.eam_accounting_mode != "none"):
                entry, capitalized = order.sudo().with_context({})._eam_post_maintenance_cost()
                super(Request, order.sudo()).write({
                    "eam_posted_entry_id": entry.id, "eam_capitalized_amount": capitalized,
                })
        return result

    def _eam_post_maintenance_cost(self):
        self.ensure_one()
        company = self.company_id
        currency = company.currency_id
        with_company = self.with_company(company)
        balances = defaultdict(float)
        sources = defaultdict(float)
        costs = with_company.cost_ids.filtered(lambda line: not currency.is_zero(line.amount))
        bills = costs.bill_id
        if bills:
            self.env.cr.execute("SELECT id FROM account_move WHERE id IN %s ORDER BY id FOR UPDATE", [tuple(bills.ids)])
            bills.invalidate_recordset()
        for cost in costs:
            bill = cost.bill_id
            if not bill or bill.state != "posted" or bill.move_type != "in_invoice":
                raise UserError(_("Ghi sổ hóa đơn nhà cung cấp cho chi phí dịch vụ trước khi nghiệm thu."))
            if bill.invoice_origin != self.eam_number:
                raise UserError(_("Nguồn của hóa đơn dịch vụ phải là số lệnh EAM đang nghiệm thu."))
            if with_company.cost_ids.search_count([("bill_id", "=", bill.id)], limit=2) != 1:
                raise UserError(_("Một hóa đơn dịch vụ chỉ được dùng cho một dòng chi phí EAM."))
            lines = bill.invoice_line_ids.filtered(lambda line: line.display_type == "product")
            if currency.compare_amounts(sum(lines.mapped("balance")), cost.amount):
                raise UserError(_("Chi phí dịch vụ EAM phải bằng giá trị trước thuế của hóa đơn theo tiền công ty."))
            for line in lines:
                sources[line.account_id.id] += line.balance

        for move in with_company.eam_move_ids.filtered(lambda move: move.state == "done"):
            outgoing = move.location_id.usage == "internal" and move.location_dest_id.eam_consumption
            returning = move.location_dest_id.usage == "internal" and move.location_id.eam_consumption
            if not (outgoing or returning):
                continue
            expense = move.location_dest_id.valuation_account_id if outgoing else move.location_id.valuation_account_id
            if not expense or (not currency.is_zero(move.value) and move.account_move_id.state != "posted"):
                raise UserError(_("Cấu hình tài khoản vị trí tiêu hao và định giá tự động cho phụ tùng EAM."))
            sources[expense.id] += currency.round(move.value) * (1 if outgoing else -1)

        labor = currency.round(with_company.actual_hours * with_company.hourly_rate)
        if labor and not company.eam_labor_clearing_id:
            raise UserError(_("Kế toán cần cấu hình tài khoản đối ứng giờ công EAM."))
        capitalized = 0
        if self.eam_accounting_mode == "overhead":
            target = company.eam_overhead_account_id
            if not target:
                raise UserError(_("Kế toán cần cấu hình tài khoản chi phí chung bảo trì."))
        else:
            production = with_company.eam_production_id
            self.env.cr.execute("SELECT id FROM mrp_production WHERE id = %s FOR UPDATE", [production.id])
            production.invalidate_recordset()
            if production.state in ("done", "cancel") or production.eam_cost_applied or (
                production.move_finished_ids.filtered(lambda move: move.state == "done")
            ):
                raise UserError(_("Chỉ chuyển chi phí vào lệnh sản xuất chưa nhập thành phẩm."))
            product = production.product_id
            target = product.property_stock_production.valuation_account_id
            if not target or not product.is_storable or product.valuation != "real_time" or (
                product.cost_method not in ("fifo", "average")
            ):
                raise UserError(_("Giá thành EAM cần thành phẩm định giá tự động FIFO/AVCO và tài khoản dở dang."))
            capitalized = currency.round(labor + sum(sources.values()))
            if capitalized < 0:
                raise UserError(_("Chi phí chuyển vào giá thành không được âm."))

        if labor:
            if company.eam_labor_clearing_id == target:
                raise UserError(_("Tài khoản đối ứng giờ công phải khác tài khoản nhận chi phí."))
            balances[company.eam_labor_clearing_id.id] -= labor
            balances[target.id] += labor
        for account_id, amount in sources.items():
            if account_id != target.id:
                balances[account_id] -= amount
                balances[target.id] += amount
        entry = company._eam_post_entry(self.eam_number, fields.Date.context_today(self), balances)
        return entry, capitalized


class Production(models.Model):
    _inherit = "mrp.production"

    eam_cost_applied = fields.Boolean("Đã tính giá thành bảo trì", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        if any(values.get("eam_cost_applied", self.env.context.get("default_eam_cost_applied"))
               for values in vals_list):
            raise AccessError(_("Odoo ghi nhận chi phí bảo trì khi tính giá thành."))
        return super().create(vals_list)

    def write(self, vals):
        if "eam_cost_applied" in vals:
            raise AccessError(_("Odoo ghi nhận chi phí bảo trì khi tính giá thành."))
        return super().write(vals)

    def _eam_cost_orders(self):
        return self.env["maintenance.request"].sudo().search([
            ("eam_production_id", "in", self.ids), ("eam_state", "=", "done"),
            ("eam_capitalized_amount", "!=", 0),
        ])

    def action_cancel(self):
        if self._eam_cost_orders():
            raise UserError(_("Lệnh sản xuất có chi phí EAM đã ghi sổ. Kế toán cần xử lý bút toán trước khi hủy."))
        return super().action_cancel()

    def _cal_price(self, consumed_moves):
        self.ensure_one()
        self.env.cr.execute("SELECT id FROM mrp_production WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["eam_cost_applied"])
        result = super()._cal_price(consumed_moves)
        if self.eam_cost_applied:
            return result
        orders = self._eam_cost_orders()
        cost = sum(orders.mapped("eam_capitalized_amount"))
        if self.company_id.currency_id.is_zero(cost):
            return result
        finished = self.move_finished_ids.filtered(
            lambda move: move.product_id == self.product_id and move.state not in ("done", "cancel")
            and move.product_uom.compare(move.quantity, 0) > 0
        )
        if not finished:
            return result
        target = self.product_id.property_stock_production.valuation_account_id
        if self.product_id.cost_method not in ("fifo", "average") or self.product_id.valuation != "real_time" or (
            not target or finished.location_id.valuation_account_id != target
        ):
            raise UserError(_("Cấu hình định giá hoặc tài khoản dở dang đã thay đổi sau khi ghi sổ chi phí EAM."))
        byproducts = self.move_byproduct_ids.filtered(
            lambda move: move.state not in ("done", "cancel") and move.product_uom.compare(move.quantity, 0) > 0
        )
        if byproducts.filtered(lambda move: move.cost_share and (
            move.product_id.cost_method not in ("fifo", "average")
            or move.product_id.valuation != "real_time"
            or move.location_id.valuation_account_id != target
        )):
            raise UserError(_("Sản phẩm phụ nhận chi phí EAM cần cùng tài khoản dở dang và định giá FIFO/AVCO."))
        quantity = sum(move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id)
                       for move in finished)
        main_share = float_round(1 - sum(byproducts.mapped("cost_share")) / 100, precision_rounding=0.0001)
        for move in finished:
            move.price_unit += cost * main_share / quantity
        for move in byproducts.filtered("cost_share"):
            qty = move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id)
            move.price_unit += cost * move.cost_share / 100 / qty
        super(Production, self.sudo()).write({"eam_cost_applied": True})
        return result


class DepreciationSchedule(models.Model):
    _name = "ps.eam.depreciation"
    _description = "Lịch khấu hao thiết bị EAM"
    _check_company_auto = True

    name = fields.Char("Tên lịch", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    equipment_id = fields.Many2one("maintenance.equipment", "Thiết bị", required=True, check_company=True,
                                    ondelete="restrict")
    acquisition_value = fields.Monetary("Nguyên giá", required=True)
    salvage_value = fields.Monetary("Giá trị thu hồi")
    opening_depreciation = fields.Monetary("Khấu hao đã ghi trước lịch")
    months = fields.Integer("Số tháng khấu hao còn lại", required=True, default=12)
    first_date = fields.Date("Ngày khấu hao kỳ đầu", required=True)
    expense_account_id = fields.Many2one("account.account", "Chi phí khấu hao", required=True, check_company=True)
    accumulated_account_id = fields.Many2one("account.account", "Hao mòn lũy kế", required=True, check_company=True)
    state = fields.Selection(
        [("draft", "Nháp"), ("running", "Đang khấu hao"), ("done", "Đã hoàn tất")],
        required=True, default="draft", readonly=True, index=True,
    )
    entry_ids = fields.One2many("account.move", "eam_depreciation_id", string="Bút toán khấu hao")
    _one_schedule = models.Constraint("unique(equipment_id)", "Mỗi thiết bị chỉ có một lịch khấu hao EAM.")

    @api.constrains("acquisition_value", "salvage_value", "opening_depreciation", "months",
                    "expense_account_id", "accumulated_account_id")
    def _check_schedule_values(self):
        for schedule in self:
            if schedule.months < 1 or schedule.salvage_value < 0 or schedule.opening_depreciation < 0 or (
                schedule.acquisition_value <= schedule.salvage_value + schedule.opening_depreciation
            ) or schedule.expense_account_id == schedule.accumulated_account_id:
                raise ValidationError(_("Kiểm tra giá trị khấu hao, số kỳ và hai tài khoản khấu hao."))

    @api.model_create_multi
    def create(self, vals_list):
        if any(values.get("state", self.env.context.get("default_state", "draft")) != "draft"
               for values in vals_list):
            raise AccessError(_("Lịch khấu hao mới phải ở trạng thái nháp."))
        return super().create(vals_list)

    def write(self, vals):
        if "state" in vals or self.filtered(lambda schedule: schedule.state != "draft"):
            raise UserError(_("Chỉ sửa lịch khấu hao nháp."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _prevent_delete_active_schedule(self):
        if self.filtered(lambda schedule: schedule.state != "draft"):
            raise UserError(_("Phải giữ lại lịch khấu hao đã kích hoạt."))

    def action_activate(self):
        self.ensure_one()
        self.check_access("write")
        self.env.cr.execute("SELECT id FROM ps_eam_depreciation WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["state"])
        if self.state != "draft":
            raise UserError(_("Chỉ kích hoạt lịch khấu hao nháp."))
        if not self.company_id.eam_journal_id or self.equipment_id.company_id != self.company_id:
            raise UserError(_("Cấu hình nhật ký EAM và chọn thiết bị cùng công ty."))
        super().write({"state": "running"})

    @api.model
    def _cron_post_depreciation(self):
        for schedule in self.search([("state", "=", "running"), ("first_date", "<=", fields.Date.today())]):
            try:
                with self.env.cr.savepoint():
                    schedule._post_due()
            except (UserError, ValidationError):
                _logger.exception("EAM depreciation %s could not post", schedule.id)

    def _post_due(self):
        self.ensure_one()
        self.env.cr.execute("SELECT id FROM ps_eam_depreciation WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["state", "entry_ids"])
        if self.state != "running":
            return
        today = fields.Date.context_today(self)
        base = self.acquisition_value - self.salvage_value - self.opening_depreciation
        dates_posted = set(self.entry_ids.mapped("eam_depreciation_date"))
        for index in range(self.months):
            due = self.first_date + relativedelta(months=index)
            if due > today:
                return
            if due in dates_posted:
                continue
            amount = self.currency_id.round(base * (index + 1) / self.months) - self.currency_id.round(
                base * index / self.months
            )
            entry = self.company_id._eam_post_entry(self.name, due, {
                self.expense_account_id.id: amount, self.accumulated_account_id.id: -amount,
            })
            if entry:
                entry._eam_link_depreciation(self, due)
        super().write({"state": "done"})


class AccountMove(models.Model):
    _inherit = "account.move"

    eam_depreciation_id = fields.Many2one("ps.eam.depreciation", "Lịch khấu hao EAM",
                                           check_company=True, ondelete="restrict", readonly=True, copy=False)
    eam_depreciation_date = fields.Date("Kỳ khấu hao EAM", readonly=True, copy=False)
    _eam_depreciation_period = models.Constraint(
        "unique(eam_depreciation_id, eam_depreciation_date)", "Kỳ khấu hao EAM này đã được ghi sổ.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        fields_to_protect = ("eam_depreciation_id", "eam_depreciation_date")
        if any(values.get(key, self.env.context.get("default_" + key))
               for values in vals_list for key in fields_to_protect):
            raise AccessError(_("Liên kết kỳ khấu hao được tạo bởi lịch EAM."))
        return super().create(vals_list)

    def write(self, vals):
        if {"eam_depreciation_id", "eam_depreciation_date"} & vals.keys():
            raise AccessError(_("Liên kết kỳ khấu hao được tạo bởi lịch EAM."))
        return super().write(vals)

    def _eam_link_depreciation(self, schedule, due):
        return super().write({"eam_depreciation_id": schedule.id, "eam_depreciation_date": due})

    def button_draft(self):
        if self.filtered("eam_depreciation_id"):
            raise UserError(_("Giữ bút toán khấu hao EAM đã ghi sổ và dùng bút toán đảo khi cần điều chỉnh."))
        return super().button_draft()


class Equipment(models.Model):
    _inherit = "maintenance.equipment"

    eam_depreciation_ids = fields.One2many("ps.eam.depreciation", "equipment_id",
                                            string="Lịch khấu hao", groups="account.group_account_manager")
    eam_depreciation_total = fields.Monetary("Tổng khấu hao ghi nhận", compute="_compute_eam_depreciation_total",
                                             compute_sudo=True)

    @api.depends("depreciation_recorded", "eam_depreciation_ids.state", "eam_depreciation_ids.opening_depreciation",
                 "eam_depreciation_ids.entry_ids.state", "eam_depreciation_ids.entry_ids.amount_total")
    def _compute_eam_depreciation_total(self):
        for equipment in self:
            schedule = equipment.eam_depreciation_ids.filtered(lambda item: item.state != "draft")
            equipment.eam_depreciation_total = (
                schedule.opening_depreciation + sum(schedule.entry_ids.filtered(
                    lambda entry: entry.state == "posted"
                ).mapped("amount_total")) if schedule else equipment.depreciation_recorded
            )

    @api.depends("eam_depreciation_total", "cost", "operation_ids.planned_hours", "operation_ids.running_hours",
                 "operation_ids.total_qty", "operation_ids.good_qty", "operation_ids.ideal_cycle_seconds")
    def _compute_eam_summary(self):
        super()._compute_eam_summary()
        for equipment in self:
            schedule = equipment.sudo().eam_depreciation_ids.filtered(lambda item: item.state != "draft")
            gross = schedule.acquisition_value if schedule else equipment.cost
            equipment.eam_book_value = max(0, gross - equipment.eam_depreciation_total)
