from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PsSequenceFormat(models.Model):
    _name = "ps.sequence.format"
    _description = "Sequence Segment Line"
    _order = "segment_number"

    segment_number = fields.Integer(string="Segment Number", required=True)
    type = fields.Selection([
        ("constant", "Constant"),
        ("year_no_cent", "Current Year without Century"),
        ("year_with_cent", "Current Year with Century"),
        ("month", "Month"),
        ("day", "Day"),
        ("day_of_year", "Day of the Year"),
        ("week", "Week of the Year"),
        ("day_of_week", "Day of the Week"),
        ("hour24", "Hour 00->24"),
        ("hour12", "Hour 00->12"),
        ("minute", "Minute"),
        ("second", "Second"),
    ], string="Type", required=True)
    value = fields.Char(string="Value")
    sequence_id = fields.Many2one(
        "ir.sequence", string="Sequence", ondelete="cascade"
    )
    company_id = fields.Many2one(
        related="sequence_id.company_id", store=True, readonly=True
    )

    @api.constrains("type", "value")
    def _check_value_required(self):
        for record in self:
            if record.type == "constant" and not record.value:
                raise ValidationError(_("Value is required when type is Constant"))
            elif record.type != "constant" and record.value:
                raise ValidationError(_("Value should be empty when type is not Constant"))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for seq in records.mapped("sequence_id"):
            seq._x_sync_prefix_from_segments()
        return records

    def write(self, vals):
        res = super().write(vals)
        for seq in self.mapped("sequence_id"):
            seq._x_sync_prefix_from_segments()
        return res

    def unlink(self):
        seqs = self.mapped("sequence_id")
        res = super().unlink()
        for seq in seqs:
            seq._x_sync_prefix_from_segments()
        return res
