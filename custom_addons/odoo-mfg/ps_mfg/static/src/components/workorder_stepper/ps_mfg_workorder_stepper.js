import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formatFloat } from "@web/views/fields/formatters";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

/**
 * Stepper hiển thị tiến độ các công đoạn của lệnh SX:
 *   ●──●──○──○  Bắt đầu → CĐ1 (80/100) → CĐ2 (40/100) ...
 * Các bước trải đều toàn chiều ngang, highlight cặp Từ → Đến đang chọn; click
 * một công đoạn hợp lệ (`selectable`, khi form còn sửa được) để chọn làm "Đến
 * công đoạn" (onchange sẽ tự điền "Từ công đoạn"); công đoạn không hợp lệ bị làm mờ.
 */
export class PsMfgWorkorderStepper extends Component {
    static template = "ps_mfg.WorkorderStepper";
    static props = { ...standardFieldProps };

    get progress() {
        return this.props.record.data[this.props.name] || false;
    }

    get steps() {
        return this.progress ? this.progress.steps : [];
    }

    get canSelect() {
        return !this.props.readonly;
    }

    /** Vị trí bước "Đến" (-1 nếu chưa chọn); các bước ≤ vị trí này được nối màu primary. */
    get toIndex() {
        const toId = this.progress && this.progress.to_id;
        return toId ? this.steps.findIndex((step) => step.id === toId) : -1;
    }

    /** Chỉ công đoạn hợp lệ cho "Đến công đoạn" (server tính sẵn `selectable`) mới click được. */
    isSelectable(step, index) {
        return this.canSelect && index > 0 && Boolean(step.selectable);
    }

    isDone(step, index) {
        const total = this.progress.product_qty;
        return index > 0 && total > 0 && step.done_qty >= total;
    }

    stepClass(step, index) {
        const progress = this.progress;
        const classes = [];
        if (index > 0 && step.id === progress.to_id) {
            classes.push("o_ps_step_to");
        } else if (step.id === (progress.from_id || false)) {
            classes.push("o_ps_step_from");
        }
        if (this.isDone(step, index)) {
            classes.push("o_ps_step_done");
        }
        if (index <= this.toIndex) {
            classes.push("o_ps_step_reached");
        }
        if (this.isSelectable(step, index)) {
            classes.push("o_ps_step_selectable");
        } else if (this.canSelect && index > 0 && step.id !== progress.to_id) {
            classes.push("o_ps_step_disabled");
        }
        return classes.join(" ");
    }

    stepPercent(step) {
        const total = this.progress.product_qty;
        if (!total) {
            return 0;
        }
        return Math.max(0, Math.min(100, (step.done_qty / total) * 100));
    }

    stepQty(step) {
        return `${formatFloat(step.done_qty)} / ${formatFloat(this.progress.product_qty)}`;
    }

    stepTitle(step, index) {
        if (index === 0) {
            return _t("Start");
        }
        const title = `${step.code} ${step.name}`;
        if (this.canSelect && !step.selectable && step.id !== this.progress.to_id) {
            return `${title} - ${_t("No semi-finished quantity available from previous work orders")}`;
        }
        return title;
    }

    onSelect(step, index) {
        if (!this.isSelectable(step, index)) {
            return;
        }
        this.props.record.update({
            to_workorder_id: { id: step.id, display_name: step.name },
        });
    }
}

export const psMfgWorkorderStepper = {
    component: PsMfgWorkorderStepper,
    displayName: _t("Work Order Stepper"),
    supportedTypes: ["json"],
};

registry.category("fields").add("ps_mfg_workorder_stepper", psMfgWorkorderStepper);
