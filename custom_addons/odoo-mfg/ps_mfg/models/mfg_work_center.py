from odoo import _, api, fields, models


class PsMfgWorkCenter(models.Model):
    _name = "ps.mfg.work.center"
    _description = "MFG Work Center"
    _check_company_auto = True
    _inherit = ["mail.thread"]

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    name = fields.Char(string="Worker Center Name", required=True, tracking=True)
    code = fields.Char(string="Code", required=True, tracking=True)
    description = fields.Html(string="Description")
    enabled = fields.Boolean(string="Enabled", default=True, tracking=True)
    efficiency = fields.Float(
        string="Efficiency (%)",
        tracking=True,
        help="The efficiency of the worker center in percentage.",
    )
    cost_per_hour = fields.Float(
        string="Cost per Hour",
        tracking=True,
        help="The cost per hour for using this worker center.",
    )
    location_id = fields.Many2one(
        "stock.location",
        "Location",
        required=True,
        tracking=True,
        domain="[('usage', '=', 'internal')]",
        check_company=True,
        help="The location associated with this worker center.",
    )
    expense_account_id = fields.Many2one(
        "account.account",
        string="Expense Account",
        required=True,
        tracking=True,
        help="The account used for recording expenses related to this worker center.",
    )
    wip_account_id = fields.Many2one(
        "account.account",
        string="WIP Account",
        required=True,
        tracking=True,
        help="The account used for recording work in progress related to this worker center.",
    )
    mo_prefix = fields.Char(
        string="MO Prefix",
        required=True,
        help="The prefix used for manufacturing orders associated with this worker center.",
    )
    mo_sequence_id = fields.Many2one(
        "ir.sequence",
        string="MO Sequence",
        help="The sequence used for generating manufacturing order numbers for this worker center.",
    )
    comp_request_prefix = fields.Char(
        string="Component Request Prefix",
        required=True,
        help="The prefix used for component requests associated with this worker center.",
    )
    comp_request_sequence_id = fields.Many2one(
        "ir.sequence",
        string="Component Request Sequence",
        help="The sequence used for generating component request numbers for this worker center.",
    )
    receipt_request_prefix = fields.Char(
        string="Receipt Request Prefix",
        required=True,
        help="The prefix used for receipt requests associated with this worker center.",
    )
    receipt_request_sequence_id = fields.Many2one(
        "ir.sequence",
        string="Receipt Request Sequence",
        help="The sequence used for generating receipt request numbers for this worker center.",
    )

    _work_center_code_unique = models.Constraint(
        "UNIQUE(code, company_id)",
        _("The code must be unique within the same company."),
    )
    _work_center_name_unique = models.Constraint(
        "UNIQUE(name, company_id)",
        _("The name must be unique within the same company."),
    )

    _SEQUENCE_SPECS = [
        ("mo_sequence_id", "mo_prefix", "MO Sequence"),
        (
            "comp_request_sequence_id",
            "comp_request_prefix",
            "Component Request Sequence",
        ),
        (
            "receipt_request_sequence_id",
            "receipt_request_prefix",
            "Receipt Request Sequence",
        ),
    ]

    @staticmethod
    def _default_sequence_prefix(prefix):
        prefix = (prefix or "").strip().rstrip("/")
        if prefix:
            return f"{prefix}/%(year)s%(month)s."
        return "%(year)s%(month)s."

    def _create_sequences(self):
        """Create missing ir.sequence records (prefix + year + month + sequence)."""
        IrSequence = self.env["ir.sequence"]
        for work_center in self:
            for seq_field, prefix_field, label in self._SEQUENCE_SPECS:
                if work_center[seq_field]:
                    continue
                prefix = self._default_sequence_prefix(work_center[prefix_field])
                sequence = IrSequence.create(
                    {
                        "name": f"{label} for {work_center.name}",
                        "code": f"ps.mfg.work.center.{seq_field}",
                        "prefix": prefix,
                        "padding": 5,
                        "company_id": work_center.company_id.id,
                    }
                )
                work_center[seq_field] = sequence.id

    def _open_sequence(self, sequence):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "ir.sequence",
            "view_mode": "form",
            "res_id": sequence.id,
            "target": "current",
        }

    def action_open_mo_sequence(self):
        return self._open_sequence(self.mo_sequence_id)

    def action_open_comp_request_sequence(self):
        return self._open_sequence(self.comp_request_sequence_id)

    def action_open_receipt_request_sequence(self):
        return self._open_sequence(self.receipt_request_sequence_id)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._create_sequences()
        return records

    def write(self, vals):
        res = super().write(vals)
        # Trường hợp sequence chưa được tạo khi cập nhật
        if (
            "mo_prefix" in vals
            or "comp_request_prefix" in vals
            or "receipt_request_prefix" in vals
        ):
            self._create_sequences()
        return res
