from odoo import _, api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mfg_sequencing_prefix = fields.Char(
        string="Sequencing Prefix",
        config_parameter="ps_mfg.production_sequencing_prefix",
        default="TTSX%(y)s%(month)s.",
        help="Prefix used to automatically generate code for Production Sequencing (e.g., SEQ., PSQ.)",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        seq = (
            self.env["ir.sequence"]
            .sudo()
            .search([("code", "=", "ps.mfg.production.sequencing")], limit=1)
        )
        if seq and seq.prefix:
            res["mfg_sequencing_prefix"] = seq.prefix
        return res

    def set_values(self):
        super().set_values()
        for record in self:
            prefix = record.mfg_sequencing_prefix or ""
            sequences = (
                self.env["ir.sequence"]
                .sudo()
                .search([("code", "=", "ps.mfg.production.sequencing")])
            )
            if sequences:
                sequences.write({"prefix": prefix})

    def action_open_production_sequencing_sequence(self):
        seq = (
            self.env["ir.sequence"]
            .sudo()
            .search([("code", "=", "ps.mfg.production.sequencing")], limit=1)
        )
        if not seq:
            seq = self.env.ref(
                "ps_mfg.seq_ps_mfg_production_sequencing", raise_if_not_found=False
            )
        return {
            "name": _("Production Sequencing Sequence"),
            "type": "ir.actions.act_window",
            "res_model": "ir.sequence",
            "view_mode": "form",
            "res_id": seq.id if seq else False,
            "target": "current",
        }
