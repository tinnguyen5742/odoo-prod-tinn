import { patch } from "@web/core/utils/patch";
import { CoursePage } from "@website_slides/interactions/course_page";

patch(CoursePage.prototype, {
    updateProgressbar(channelCompletion) {
        super.updateProgressbar(...arguments);
        // Khóa có đánh giá bắt buộc: tải lại để server quyết định
        // hiển thị Completed hay khối "Mandatory Requirement!"
        if (
            Math.min(100, channelCompletion) === 100
            && document.querySelector(".o_ps_evaluation_required")
        ) {
            window.location.reload();
        }
    },
});