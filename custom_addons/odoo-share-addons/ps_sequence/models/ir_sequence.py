import logging
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

SEQUENCE_PREFIX_SUFFIX = {
    "year_with_cent": "%(year)s",
    "year_no_cent": "%(y)s",
    "month": "%(month)s",
    "day": "%(day)s",
    "day_of_year": "%(doy)s",
    "week": "%(woy)s",
    "day_of_week": "%(weekday)s",
    "hour24": "%(h24)s",
    "hour12": "%(h12)s",
    "minute": "%(min)s",
    "second": "%(sec)s",
}


class IrSequence(models.Model):
    _inherit = "ir.sequence"

    x_use_segment_format = fields.Boolean(
        string="Use Segment Format Builder",
        default=False,
    )
    x_format_line_ids = fields.One2many(
        "ps.sequence.format",
        "sequence_id",
        string="Segment Format",
    )
    x_sequence_preview = fields.Char(
        string="Sequence Preview",
        compute="_compute_x_sequence_preview",
    )

    @api.depends(
        "x_format_line_ids",
        "x_format_line_ids.type",
        "x_format_line_ids.value",
        "x_format_line_ids.segment_number",
        "padding",
        "x_use_segment_format",
    )
    def _compute_x_sequence_preview(self):
        now = datetime.now()
        interp = {
            'year': now.strftime('%Y'), 'month': now.strftime('%m'),
            'day': now.strftime('%d'), 'y': now.strftime('%y'),
            'doy': now.strftime('%j'), 'woy': now.strftime('%W'),
            'weekday': now.strftime('%w'), 'h24': now.strftime('%H'),
            'h12': now.strftime('%I'), 'min': now.strftime('%M'),
            'sec': now.strftime('%S'),
        }
        for seq in self:
            if not seq.x_use_segment_format or not seq.x_format_line_ids:
                seq.x_sequence_preview = ""
                continue
            try:
                prefix = seq._x_build_prefix_from_segments()
            except ValidationError:
                seq.x_sequence_preview = ""
                continue
            try:
                rendered = prefix % interp
            except (ValueError, TypeError, KeyError):
                rendered = prefix
            pad = seq.padding or 0
            seq.x_sequence_preview = f"{rendered}{str(1).zfill(pad)}"

    @api.constrains("x_use_segment_format", "x_format_line_ids")
    def _check_segment_lines_required(self):
        self._x_validate_segment_lines()

    def _x_validate_segment_lines(self):
        for seq in self:
            if seq.x_use_segment_format and not seq.x_format_line_ids:
                raise ValidationError(_(
                    "Segment Format lines are required when 'Use Segment Format Builder' is enabled (sequence: %s).",
                    seq.name,
                ))

    def _x_build_prefix_from_segments(self):
        self.ensure_one()
        lines = self.x_format_line_ids.sorted(key=lambda r: r.segment_number)
        prefix = ""
        for line in lines:
            if line.type in SEQUENCE_PREFIX_SUFFIX:
                prefix += SEQUENCE_PREFIX_SUFFIX[line.type]
            elif line.type == "constant":
                prefix += line.value or ""
        if not prefix:
            raise ValidationError(_("Cannot build prefix from empty segment list"))
        return prefix

    def _x_sync_prefix_from_segments(self):
        for seq in self:
            if not seq.x_use_segment_format:
                continue
            prefix = seq._x_build_prefix_from_segments()
            super(IrSequence, seq.sudo()).write({"prefix": prefix})
            _logger.info(
                "Synced prefix for sequence %s (id=%s): %s",
                seq.name, seq.id, prefix,
            )

    @api.model_create_multi
    def create(self, vals_list):
        seqs = super().create(vals_list)
        seqs._x_validate_segment_lines()
        return seqs

    def write(self, vals):
        res = super().write(vals)
        if "x_use_segment_format" in vals or "x_format_line_ids" in vals:
            self._x_validate_segment_lines()
        if self._x_segments_dirty(vals):
            self._x_sync_prefix_from_segments()
        return res

    def _x_segments_dirty(self, vals):
        return (
            "x_format_line_ids" in vals
            or "x_use_segment_format" in vals
            or "padding" in vals
        )
