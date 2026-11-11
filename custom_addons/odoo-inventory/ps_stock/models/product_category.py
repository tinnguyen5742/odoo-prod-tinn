from odoo import models, fields, api


class ProductCategory(models.Model):
    _inherit = 'product.category'

    x_code_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Product Code Sequence',
        domain="[('code', '=', 'product.product.code.default')]",
        context={
            'default_code': 'product.product.code.default',
            'default_x_use_segment_format': True,
        },
        tracking=True,
    )
    x_sequence_preview = fields.Char(
        string='Sequence Preview',
        compute='_compute_x_sequence_preview',
        help="Preview of the next sequence number for the product code.",
    )

    @api.depends('x_code_sequence_id', 'x_code_sequence_id.x_sequence_preview')
    def _compute_x_sequence_preview(self):
        for cat in self:
            cat.x_sequence_preview = cat.x_code_sequence_id.x_sequence_preview or ''

    def action_create_product_code_sequence(self):
        self.ensure_one()
        prefix_value = (self.name or 'PR')[:3].upper()
        sequence = self.env['ir.sequence'].sudo().create({
            'name': f'Product Code - {self.display_name}',
            'code': 'product.product.code.default',
            'company_id': self.env.company.id,
            'padding': 6,
            'x_use_segment_format': True,
            'x_format_line_ids': [(0, 0, {
                'segment_number': 1,
                'type': 'constant',
                'value': prefix_value,
            })],
        })
        self.x_code_sequence_id = sequence.id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ir.sequence',
            'res_id': sequence.id,
            'view_mode': 'form',
            'target': 'current',
        }
