/** @odoo-module **/
import { registerThreadAction } from "@mail/core/common/thread_actions";
import { _t } from "@web/core/l10n/translation";

registerThreadAction("ps_elearning-back-to-course", {
    condition: ({ thread }) =>
        thread && thread.model === "discuss.channel" && thread.x_is_slide_channel,
    icon: "fa fa-fw fa-arrow-left",
    name: _t("Back to Course"),
    sequence: 10,
    sequenceGroup: 5,
    async open({ store, thread }) {
        const result = await store.env.services.orm.call(
            "discuss.channel", "action_open_linked_course", [[thread.id]]
        );
        if (result) {
            store.env.services.action.doAction(result);
        }
    },
});
