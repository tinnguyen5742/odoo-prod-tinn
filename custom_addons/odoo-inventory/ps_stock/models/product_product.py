import logging

from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

DEFAULT_PRODUCT_CODE_SEQUENCE_CODE = 'product.product.code.default'


class ProductProduct(models.Model):
    _inherit = "product.product"

    x_product_code = fields.Char(string="Product Code", copy=False, readonly=True, index=True, help="Unique code for the product, generated based on category prefix and sequence.")

    @api.constrains('x_product_code', 'company_id')
    def _check_product_code(self):
        for product in self:
            if not product.x_product_code:
                raise ValidationError("Product code cannot be empty.")
            existing_product = self.search([
                ('x_product_code', '=', product.x_product_code),
                ('company_id', '=', product.company_id.id),
                ('id', '!=', product.id),
            ], limit=1)
            if existing_product:
                raise ValidationError(f"The product code '{product.x_product_code}' is already in use by another product.")

    @api.model
    def _get_default_product_code_sequence(self, company_id):
        """Return the default fallback ir.sequence for the given company.

        A dedicated sequence is created per company on first use so that each
        company gets its own independent counter. The main-company sequence is
        expected to be created from data/ir_sequence.xml (noupdate=1) so that
        admins can later tweak it from the UI.
        """
        company_id = company_id or self.env.company.id
        Sequence = self.env['ir.sequence'].sudo()
        sequence = Sequence.search(
            [('code', '=', DEFAULT_PRODUCT_CODE_SEQUENCE_CODE), ('company_id', '=', company_id)],
            limit=1,
        )
        if sequence:
            return sequence

        main_company = self.env.ref('base.main_company')
        template = Sequence.search(
            [('code', '=', DEFAULT_PRODUCT_CODE_SEQUENCE_CODE), ('company_id', '=', main_company.id)],
            limit=1,
        )
        sequence = Sequence.create({
            'name': 'PS Stock Default Product Code',
            'code': DEFAULT_PRODUCT_CODE_SEQUENCE_CODE,
            'prefix': '',
            'padding': template.padding if template else 8,
            'implementation': template.implementation if template else 'standard',
            'company_id': company_id,
        })
        _logger.info(
            'Created default product code sequence for company_id=%s (padding=%s)',
            company_id, sequence.padding,
        )
        return sequence

    def _resolve_category_sequence(self):
        """Return the ir.sequence configured for this product's category, or False."""
        self.ensure_one()
        category = self.categ_id
        if category and category.x_code_sequence_id:
            return category.x_code_sequence_id
        return False

    @api.model
    def _action_assign_missing_product_codes(self):
        """Backfill x_product_code on every product that does not have one yet.

        For each product:
          - use the sequence of the product's category prefix if configured;
          - otherwise fall back to the company-specific default sequence.

        Codes are issued one by one through ir.sequence.next_by_id() so that
        each counter advances correctly. Products already carrying a code are
        left untouched. Access is forced through sudo() so the backfill can run
        from migration scripts / post_init_hook regardless of the current user.
        """
        Product = self.sudo().with_context(active_test=False)
        products = Product.search([('x_product_code', '=', False)])
        if not products:
            _logger.info('ps_stock: no product missing x_product_code, nothing to backfill.')
            return 0

        # Pre-fetch category -> sequence mapping to avoid N+1 reads.
        categories = products.mapped('categ_id')
        category_sequence_map = {}
        for category in categories:
            if category and category.x_code_sequence_id:
                category_sequence_map[category.id] = category.x_code_sequence_id

        assigned = 0
        errors = []
        for product in products:
            try:
                sequence = category_sequence_map.get(product.categ_id.id)
                if not sequence:
                    sequence = self._get_default_product_code_sequence(product.company_id.id)
                product.write({'x_product_code': sequence.sudo().next_by_id()})
                assigned += 1
            except Exception as exc:
                errors.append((product.id, product.display_name, str(exc)))
                _logger.exception(
                    'ps_stock: failed to assign x_product_code to product id=%s (%s)',
                    product.id, product.display_name,
                )

        _logger.info(
            'ps_stock: backfilled x_product_code on %s/%s product(s).',
            assigned, len(products),
        )
        if errors:
            details = '\n'.join(
                '  - id=%s (%s): %s' % (pid, name, msg) for pid, name, msg in errors
            )
            _logger.warning(
                'ps_stock: %s product(s) could not be backfilled:\n%s',
                len(errors), details,
            )
        return assigned

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('x_product_code'):
                continue

            category = False
            if vals.get('categ_id'):
                category = self.env['product.category'].browse(vals['categ_id'])
            elif vals.get('product_tmpl_id'):
                tmpl = self.env['product.template'].browse(vals['product_tmpl_id'])
                category = tmpl.categ_id

            sequence = category.x_code_sequence_id if category and category.x_code_sequence_id else False
            if not sequence:
                company_id = vals.get('company_id') or self.env.company.id
                sequence = self._get_default_product_code_sequence(company_id)
            if sequence:
                vals['x_product_code'] = sequence.sudo().next_by_id()

        return super().create(vals_list)
