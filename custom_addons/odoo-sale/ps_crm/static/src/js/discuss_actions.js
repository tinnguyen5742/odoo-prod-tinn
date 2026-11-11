/** @odoo-module **/
import { threadActionsRegistry } from "@mail/core/common/thread_actions";

// Disable action Cài đặt thông báo, cài đặt nang cao ở user/ admin mới có quyền xem
const isNotChannelCreator = ({ store, thread }) =>
    thread?.model === "discuss.channel" &&
    !store.self.main_user_id?.eq(thread.create_uid);

const notificationSettings = threadActionsRegistry.get("notification-settings");
if (notificationSettings) {
    notificationSettings.disabledCondition = isNotChannelCreator;
}

const advancedSettings = threadActionsRegistry.get("advanced-settings");
if (advancedSettings) {
    advancedSettings.disabledCondition = isNotChannelCreator;
}
