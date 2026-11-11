from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    proposal_ids = fields.Many2many(
        "ps.mfg.proposal",
        "ps_mfg_proposal_picking_rel",
        "picking_id",
        "proposal_id",
        string="MFG Proposals",
        readonly=True,
        copy=False,
    )

    component_request_ids = fields.Many2many(
        "ps.mfg.component.request",
        string="Component Requests",
        compute="_compute_component_request_ids",
        store=True,
        readonly=True,
        help="MFG Component Requests linked via stock moves in this transfer.",
    )

    @api.depends("move_ids.component_request_line_id.request_id")
    def _compute_component_request_ids(self):
        for picking in self:
            picking.component_request_ids = (
                picking.move_ids.component_request_line_id.request_id
            )

    def _action_done(self):
        res = super()._action_done()
        for picking in self:
            for proposal in picking.proposal_ids:
                if all(p.state == "done" for p in proposal.picking_ids):
                    proposal.message_post(
                        body=_(
                            "All transfer pickings for this proposal have been completed."
                        )
                    )
                    # Legacy handling for old requests created prior to multi-transfer
                    for req in proposal.component_request_ids.filtered(
                        lambda r: r.legacy_transfer
                    ):
                        all_req_pickings = req.proposal_ids.picking_ids
                        if (
                            req.state == "approved"
                            and all_req_pickings
                            and all(p.state == "done" for p in all_req_pickings)
                        ):
                            req.state = "done"
                            req.message_post(
                                body=_(
                                    "Material transfer completed via proposal %s. Request marked as Done.",
                                    proposal.display_name,
                                )
                            )
            # Modern multi-transfer: check if requests are fully transferred
            requests = picking.component_request_ids.filtered(
                lambda r: not r.legacy_transfer
            )
            if requests:
                requests._check_transfer_complete()
        return res

    def action_print_component_pick(self):
        """In Phiếu yêu cầu lấy NVL cho các phiếu chuyển được chọn."""
        if not self:
            raise UserError(self.env._("Select at least one transfer to print."))
        # Mẫu phiếu không dùng external layout → bỏ qua wizard cấu hình layout công ty
        return (
            self.env.ref("ps_mfg.action_report_component_pick")
            .with_context(discard_logo_check=True)
            .report_action(self.sorted("id"))
        )

    def action_cancel(self):
        res = super().action_cancel()
        for picking in self:
            for proposal in picking.proposal_ids:
                proposal.message_post(
                    body=_(
                        "Transfer picking %s has been cancelled.", picking.display_name
                    )
                )
        return res
