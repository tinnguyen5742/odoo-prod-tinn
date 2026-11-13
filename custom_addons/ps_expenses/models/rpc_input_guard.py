"""Kiểm quyền trước khi Odoo dựng pseudo-record từ đầu vào RPC của PS.

Readonly/create guards không bảo vệ onchange. Related compute có thể chạy
sudo, vì vậy phải xét ID gốc, defaults và cả cây lệnh quan hệ trước super().
PS kiểm toàn bộ quan hệ. Ngoài PS, chỉ kiểm nguồn Expenses/PS trong cây
đầu vào, kể cả wizard native hoặc model ngoài namespace. Không đổi CRUD,
không cấp quyền hoặc tự cho phép tách khoản chi PS.
"""
from odoo import api, models
from odoo.exceptions import AccessError


class PsTeRpcInputGuard(models.AbstractModel):
    _inherit = 'base'

    def _ps_rpc_protected_model(self):
        return self._name.startswith('ps.te.') or self._name == 'hr.expense' or self._name.startswith('hr.expense.')

    def _ps_rpc_check_ids(self, ids, seen=None):
        if not ids:
            return
        if any(type(record_id) is not int or record_id <= 0 for record_id in ids):
            raise AccessError('Liên kết hồ sơ không hợp lệ hoặc không được phép truy cập.')
        # Không tin sudo/context do caller truyền; check cả tập, không search
        # lọc mất ID cấm đọc rồi tiếp tục tính trên phần còn lại.
        records = self.with_user(self.env.uid).sudo(False).browse(list(dict.fromkeys(ids)))
        try:
            records.check_access('read')
        except AccessError:
            # Odoo cho nhân viên đọc danh tính HR qua public projection, không
            # qua private hr.employee. Giữ đúng đường đó cho form tạo chuyến;
            # không áp dụng fallback này cho hồ sơ/tiền/chứng từ PS.
            if self._name == 'hr.employee':
                public = self.env['hr.employee.public'].with_user(self.env.uid).sudo(False).browse(records.ids)
                public.check_access('read')
                if len(public.exists()) == len(records):
                    return
            # Không đưa display_name/công ty của bản ghi cấm đọc vào lỗi RPC.
            raise AccessError('Không được phép đọc hồ sơ liên kết.') from None
        if len(records.exists()) != len(records):
            raise AccessError('Liên kết hồ sơ không hợp lệ hoặc không được phép truy cập.')
        if self._name == 'ps.te.expense.report':
            for record in records:
                record._assert_viewer()
        elif self._name == 'ps.te.expense.line':
            records.mapped('report_id')._ps_rpc_check_ids(records.mapped('report_id').ids)
            records.mapped('native_expense_id')._ps_rpc_check_ids(records.mapped('native_expense_id').ids)
        elif self._transient and self._ps_rpc_protected_model():
            # Origin của wizard/split line đã lưu cũng không là quyền đọc
            # khoản chi. Duyệt liên kết persistent, có visited để chặn chu kỳ.
            seen = set(seen or ())
            pending = records.filtered(lambda record: (record._name, record.id) not in seen)
            seen.update((record._name, record.id) for record in pending)
            for name, field in pending._fields.items():
                if field.relational and self.env[field.comodel_name]._ps_rpc_protected_model():
                    linked = pending.mapped(name)
                    linked._ps_rpc_check_ids(linked.ids, seen)

    def _ps_rpc_check_values(self, values, depth=0, protected_only=False):
        if depth > 16 or not isinstance(values, dict):
            raise AccessError('Cấu trúc liên kết hồ sơ không hợp lệ.')
        check_current = not protected_only or self._ps_rpc_protected_model()
        if check_current and values.get('id'):
            self._ps_rpc_check_ids([values['id']])
        for name, value in values.items():
            field = self._fields.get(name)
            if not field or not field.relational or not value:
                continue
            target = self.env[field.comodel_name]
            check_target = not protected_only or target._ps_rpc_protected_model()
            if field.type == 'many2one':
                if isinstance(value, dict):
                    target._ps_rpc_check_values(value, depth + 1, protected_only)
                elif check_target:
                    # Odoo chấp nhận ID hoặc cặp (ID, display_name).
                    record_id = value[0] if isinstance(value, (list, tuple)) and value else value
                    target._ps_rpc_check_ids([record_id])
            elif field.type in ('one2many', 'many2many'):
                if not isinstance(value, (list, tuple)):
                    if check_target:
                        raise AccessError('Cấu trúc liên kết hồ sơ không hợp lệ.')
                    continue
                for command in value:
                    if isinstance(command, dict):
                        target._ps_rpc_check_values(command, depth + 1, protected_only)
                    elif type(command) is int and check_target:
                        target._ps_rpc_check_ids([command])
                    elif isinstance(command, (list, tuple)) and command:
                        operation = command[0]
                        if type(operation) is not int or operation not in range(7):
                            if check_target:
                                raise AccessError('Cấu trúc liên kết hồ sơ không hợp lệ.')
                            continue
                        if check_target and operation in (1, 2, 3, 4):
                            if len(command) < 2:
                                raise AccessError('Cấu trúc liên kết hồ sơ không hợp lệ.')
                            target._ps_rpc_check_ids([command[1]])
                        if operation in (0, 1):
                            if len(command) != 3:
                                raise AccessError('Cấu trúc liên kết hồ sơ không hợp lệ.')
                            target._ps_rpc_check_values(command[2], depth + 1, protected_only)
                        elif check_target and operation == 6:
                            if len(command) != 3 or not isinstance(command[2], (list, tuple)):
                                raise AccessError('Cấu trúc liên kết hồ sơ không hợp lệ.')
                            target._ps_rpc_check_ids(command[2])
                    elif check_target:
                        raise AccessError('Cấu trúc liên kết hồ sơ không hợp lệ.')

    def _ps_rpc_check_defaults(self):
        context = self.env.context
        active_model = context.get('active_model')
        if isinstance(active_model, str) and active_model in self.env.registry:
            target = self.env[active_model]
            if target._ps_rpc_protected_model():
                ids = context.get('active_ids') or ([context['active_id']] if context.get('active_id') else [])
                target._ps_rpc_check_ids(ids)
        # Các wizard native này dùng active_ids như expense IDs bất kể
        # active_model. Kiểm trước child default_get lấy dữ liệu sau super().
        if self._name in ('hr.expense.refuse.wizard', 'hr.expense.post.wizard', 'hr.expense.approve.duplicate'):
            self.env['hr.expense']._ps_rpc_check_ids(context.get('active_ids') or [])
        self._ps_rpc_check_values({key[8:]: value for key, value in self.env.context.items()
                                  if isinstance(key, str) and key.startswith('default_')},
                                  protected_only=not self._name.startswith('ps.te.'))

    @api.model
    def default_get(self, fields_list):
        self._ps_rpc_check_defaults()
        defaults = super().default_get(fields_list)
        self._ps_rpc_check_values(defaults, protected_only=not self._name.startswith('ps.te.'))
        return defaults

    def onchange(self, values, field_names, fields_spec):
        if self._ps_rpc_protected_model():
            self._ps_rpc_check_ids(self.ids)
        self._ps_rpc_check_defaults()
        self._ps_rpc_check_values(values, protected_only=not self._name.startswith('ps.te.'))
        return super().onchange(values, field_names, fields_spec)
