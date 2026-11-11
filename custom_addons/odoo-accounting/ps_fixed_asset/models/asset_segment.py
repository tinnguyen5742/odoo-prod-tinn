from odoo import models, fields, api

class PSAssetSegment(models.Model):
    _name = 'ps.asset.segment'
    _description = 'Asset Segment'
    _rec_name = 'segment_type'

    segment_type = fields.Char(string='Segment Type', required=True)
    width = fields.Integer(string='Width', default=3)
    line_ids = fields.One2many('ps.asset.segment.line', 'segment_id', string='Segment Values')


class PSAssetSegmentLine(models.Model):
    _name = 'ps.asset.segment.line'
    _description = 'Asset Segment Line'
    _rec_name = 'code' 

    segment_id = fields.Many2one('ps.asset.segment', string='Asset Segment', ondelete='cascade')
    segment_type_related = fields.Char(related='segment_id.segment_type', store=True)
    
    code = fields.Char(string='Value Code', required=True)
    name = fields.Char(string='Description', required=True)
    active = fields.Boolean(string='Active', default=True)

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for record in self:
            if record.code and record.name:
                record.display_name = f"{record.code} - {record.name}"
            else:
                record.display_name = record.code or record.name

    
  