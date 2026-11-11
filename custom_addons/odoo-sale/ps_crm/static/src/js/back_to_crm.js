/** @odoo-module **/
import { registerThreadAction } from "@mail/core/common/thread_actions";
import { _t } from "@web/core/l10n/translation";

// Thêm nút back to crm ở discuss
registerThreadAction("ps_crm-back-to-crm", {
    condition: ({ thread }) =>
        thread && thread.model === "discuss.channel" && thread.x_is_crm_channel,
    icon: "fa fa-fw fa-arrow-left",
    name: _t("Back to CRM"),
    sequence: 10,
    sequenceGroup: 5,
    async open({ store, thread }) {
        const result = await store.env.services.orm.call(
            "discuss.channel", "action_open_linked_crm", [[thread.id]]
        );
        if (result) {
            store.env.services.action.doAction(result);
        }
    },
});
