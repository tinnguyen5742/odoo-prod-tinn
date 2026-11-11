from odoo import api, fields, models


class Property(models.Model):
    _inherit = 'property.property'

    total_square_foot = fields.Float(string='Total Size(m²)')
    total_carpet_area = fields.Float(string='Carpet Area(m²)')

    property_length = fields.Float(string='Length (m)')
    property_width = fields.Float(string='Width (m)')
    plot_area = fields.Float(string='Plot Area (m²)')
    built_area = fields.Float(string='Built-up Area (m²)')
    construction_land_area = fields.Float(string='Construction Land Area (m²)')
    actual_area = fields.Float(string='Actual Area (m²)')
    usable_area = fields.Float(string='Usable Area (m²)')
    frontage = fields.Float(string='Frontage (m)')
    internal_frontage = fields.Float(string='Internal Frontage (m)')
    rear_width = fields.Float(string='Rear Width (m)')
    main_road_distance = fields.Float(string='Distance to Main Road (m)')
    main_alley_width = fields.Float(string='Main Alley Width (m)')
    secondary_alley_width = fields.Float(string='Secondary Alley Width (m)')

    currency_id = fields.Many2one(
        'res.currency', string='Currency', default=lambda self: self.env.company.currency_id,
    )
    commission_type = fields.Selection(
        [('fixed', 'Fixed'), ('percentage', 'Percentage')],
        string='Commission Type', default='fixed',
    )
    commission_fixed_amount = fields.Monetary(string='Fixed Amount')
    commission_percentage = fields.Float(string='Percentage')

    def _get_commission_values(self):
        self.ensure_one()
        return {
            'commission_type': self.commission_type,
            'commission_fixed_amount': self.commission_fixed_amount,
            'commission_percentage': self.commission_percentage,
        }

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        parent_id = defaults.get('parent_id', self.env.context.get('default_parent_id'))
        if parent_id:
            parent = self.browse(parent_id)
            for field_name, value in parent._get_commission_values().items():
                if field_name in fields_list and f'default_{field_name}' not in self.env.context:
                    defaults[field_name] = value
        return defaults

    @api.onchange('parent_id')
    def _onchange_parent_commission(self):
        for property_record in self:
            if property_record.parent_id:
                property_record.update(property_record.parent_id._get_commission_values())

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            parent_id = values.get('parent_id', self.env.context.get('default_parent_id'))
            if parent_id:
                parent = self.browse(parent_id)
                for field_name, value in parent._get_commission_values().items():
                    values.setdefault(field_name, self.env.context.get(f'default_{field_name}', value))
        return super().create(vals_list)
