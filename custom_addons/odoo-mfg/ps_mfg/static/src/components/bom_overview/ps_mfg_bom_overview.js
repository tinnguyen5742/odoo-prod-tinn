import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatFloat } from "@web/views/fields/formatters";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class PsMfgBomLine extends Component {
    static template = "ps_mfg.BomOverviewLine";
    static props = {
        data: Object,
        precision: Number,
        showUom: Boolean,
        isFolded: { type: Boolean, optional: true },
        toggleFolded: { type: Function, optional: true },
    };
    static defaultProps = { isFolded: true, toggleFolded: () => {} };

    setup() {
        this.actionService = useService("action");
        this.formatFloat = formatFloat;
    }

    get data() {
        return this.props.data;
    }

    get identifier() {
        return `${this.data.type}_${this.data.index}`;
    }

    get hasChildren() {
        return (
            (this.data.components && this.data.components.length > 0) ||
            (this.data.operations && this.data.operations.length > 0)
        );
    }

    get hasFoldButton() {
        return this.data.level > 0 && this.hasChildren;
    }

    get marginMultiplicator() {
        return this.data.level - (this.hasFoldButton ? 1 : 0);
    }

    goToRecord() {
        if (!this.data.link_id || !this.data.link_model) {
            return;
        }
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: this.data.link_model,
            res_id: this.data.link_id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

export class PsMfgBomComponentsBlock extends Component {
    static template = "ps_mfg.BomOverviewComponentsBlock";
    static components = { PsMfgBomLine, PsMfgBomComponentsBlock };
    static props = {
        data: Object,
        precision: Number,
        showUom: Boolean,
        unfoldAll: Boolean,
        foldSeq: Number,
    };
    static defaultProps = { unfoldAll: false, foldSeq: 0 };

    setup() {
        this.actionService = useService("action");
        this.state = useState({
            folds: {},
            opFolds: {},
            opsFolded: !this.props.unfoldAll,
            opsDefaultFolded: false,
        });
        onWillUpdateProps((nextProps) => {
            if (nextProps.foldSeq !== this.props.foldSeq) {
                this.state.folds = {};
                this.state.opFolds = {};
                this.state.opsFolded = !nextProps.unfoldAll;
                this.state.opsDefaultFolded = !nextProps.unfoldAll;
            }
        });
    }

    get data() {
        return this.props.data;
    }

    get isGrouped() {
        return !!this.data.ps_unassigned_components;
    }

    get unassignedComponents() {
        return this.data.ps_unassigned_components || this.data.components || [];
    }

    get hasOperations() {
        return !!this.data.operations && this.data.operations.length > 0;
    }

    toggleLineFolded(index) {
        this.state.folds[index] = !this.state.folds[index];
    }

    isLineFolded(index) {
        const folded = this.state.folds[index];
        return folded === undefined ? true : folded;
    }

    toggleOperationsFolded() {
        this.state.opsFolded = !this.state.opsFolded;
    }

    toggleOpFolded(opIndex) {
        this.state.opFolds[opIndex] = !this.isOpFolded(opIndex);
    }

    isOpFolded(opIndex) {
        const folded = this.state.opFolds[opIndex];
        return folded === undefined ? this.state.opsDefaultFolded : folded;
    }

    opComponentCount(op) {
        return (op.ps_components || []).length;
    }

    goToOperation(op) {
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "ps.mfg.routing",
            res_id: op.operation_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    foldIdentifier(line) {
        return `${line.type}_${line.index}`;
    }

    isSubBom(line) {
        return line.type === "bom" && !!line.components && line.components.length > 0;
    }
}

export class PsMfgBomTable extends Component {
    static template = "ps_mfg.BomOverviewTable";
    static components = { PsMfgBomLine, PsMfgBomComponentsBlock };
    static props = {
        data: Object,
        precision: Number,
        showUom: Boolean,
        unfoldAll: Boolean,
        foldSeq: Number,
    };

    setup() {
        this.actionService = useService("action");
        this.formatFloat = formatFloat;
    }

    goToProduct() {
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: this.props.data.link_model,
            res_id: this.props.data.link_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    get data() {
        return this.props.data;
    }
}

export class PsMfgBomControlPanel extends Component {
    static template = "ps_mfg.BomOverviewControlPanel";
    static components = { ControlPanel };
    static props = {
        variants: Object,
        showVariants: Boolean,
        currentVariantId: [Number, Boolean],
        unfoldAll: Boolean,
        changeVariant: Function,
        toggleFoldAll: Function,
    };

    setup() {
        this.controlPanelDisplay = {};
    }

    get variantEntries() {
        return Object.entries(this.props.variants || {});
    }

    updateVariant(ev) {
        this.props.changeVariant(ev.target.value);
    }
}

export class PsMfgBomOverview extends Component {
    static template = "ps_mfg.BomOverview";
    static components = { PsMfgBomControlPanel, PsMfgBomTable };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            bomData: {},
            variants: {},
            bomQty: 1,
            currentVariantId: false,
            precision: 2,
            showVariants: false,
            showUom: false,
            uomName: "",
            unfoldAll: false,
            foldSeq: 0,
        });
        onWillStart(async () => this.loadData());
    }

    get activeId() {
        return this.props.action.context.active_id || this.props.action.params?.active_id;
    }

    async loadData() {
        const data = await this.orm.call("report.ps.mfg.bom_structure", "get_html", [
            this.activeId,
            this.state.bomQty || 1,
            this.state.currentVariantId || false,
        ]);
        this.state.bomData = data.lines || {};
        this.state.variants = data.variants || {};
        this.state.bomQty = data.bom_qty || 1;
        this.state.uomName = data.bom_uom_name || "";
        this.state.showVariants = !!data.is_variant_applied;
        this.state.showUom = !!data.is_uom_applied;
        this.state.precision = data.precision ?? 2;
        if (!this.state.showVariants) {
            this.state.currentVariantId = false;
        }
    }

    async onChangeVariant(variantId) {
        const parsed = variantId ? parseInt(variantId, 10) : false;
        if (parsed !== this.state.currentVariantId) {
            this.state.currentVariantId = parsed;
            await this.loadData();
        }
    }

    toggleFoldAll() {
        this.state.unfoldAll = !this.state.unfoldAll;
        this.state.foldSeq += 1;
    }
}

registry.category("actions").add("ps_mfg_bom_overview", PsMfgBomOverview);
