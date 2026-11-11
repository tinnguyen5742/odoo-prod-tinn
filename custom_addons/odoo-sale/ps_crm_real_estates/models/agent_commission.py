from odoo import api, models


class AgentCommission(models.Model):
    _inherit = 'agent.commission'

    @api.model
    def _get_property_commission_defaults(self, rent_id=False, sell_id=False):
        if rent_id:
            transaction = self.env['property.tenancy'].browse(rent_id)
            property_type = 'rent'
        elif sell_id:
            transaction = self.env['property.booking'].browse(sell_id)
            property_type = 'sell'
        else:
            return {}
        values = transaction.property_id._get_commission_values() if transaction.property_id else {}
        values['property_type'] = property_type
        return values

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        rent_id = defaults.get('rent_id', self.env.context.get('default_rent_id'))
        sell_id = defaults.get('sell_id', self.env.context.get('default_sell_id'))
        for field_name, value in self._get_property_commission_defaults(rent_id, sell_id).items():
            if field_name in fields_list and f'default_{field_name}' not in self.env.context:
                defaults[field_name] = value
        return defaults

    @api.onchange('rent_id', 'sell_id')
    def _onchange_property_commission(self):
        for commission in self:
            commission.update(self._get_property_commission_defaults(
                commission.rent_id.id, commission.sell_id.id,
            ))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            rent_id = values.get('rent_id', self.env.context.get('default_rent_id'))
            sell_id = values.get('sell_id', self.env.context.get('default_sell_id'))
            for field_name, value in self._get_property_commission_defaults(rent_id, sell_id).items():
                values.setdefault(field_name, self.env.context.get(f'default_{field_name}', value))
        return super().create(vals_list)
