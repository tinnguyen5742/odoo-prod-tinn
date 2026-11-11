import logging

from odoo import api, models
from odoo.tools.misc import file_path
from odoo.tools.translate import TranslationImporter, get_base_langs

_logger = logging.getLogger(__name__)


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    @api.model
    def _load_module_terms(self, modules, langs, overwrite=False):
        super()._load_module_terms(modules, langs, overwrite=overwrite)
        if self._ps_vn_should_overwrite_terms(modules):
            self._ps_vn_load_i18n_overwrite(langs)

    @api.model
    def _ps_vn_should_overwrite_terms(self, modules):
        """Re-apply after this module, or after account/base reloads its PO."""
        if "ps_vn_accounting" in modules:
            return True
        if not {"account", "base"} & set(modules):
            return False
        return bool(self.sudo().search_count([
            ("name", "=", "ps_vn_accounting"),
            ("state", "in", ("installed", "to upgrade", "to install")),
        ]))

    @api.model
    def _ps_vn_load_i18n_overwrite(self, langs):
        """Load i18n_overwrite/*.po and replace existing translations.

        Standard i18n/*.po keeps the current database value unless the server
        is started with --i18n-overwrite. Menu labels for account and om_* live
        here so they apply on every upgrade of this module.
        """
        importer = TranslationImporter(self.env.cr, verbose=False)
        loaded = False
        for lang in langs:
            for filename in get_base_langs(lang):
                relative_path = f"ps_vn_accounting/i18n_overwrite/{filename}.po"
                try:
                    po_path = file_path(relative_path)
                except FileNotFoundError:
                    continue
                _logger.info(
                    "module ps_vn_accounting: loading overwrite translation file %s for language %s",
                    po_path,
                    lang,
                )
                importer.load_file(po_path, lang)
                loaded = True
        if loaded:
            importer.save(force_overwrite=True)
