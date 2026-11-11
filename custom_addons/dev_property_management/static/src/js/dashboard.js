/** @odoo-module */
import { registry } from '@web/core/registry';
import { useService } from "@web/core/utils/hooks";
const { Component, onWillStart, onMounted } = owl
// import { jsonrpc } from "@web/core/network/rpc_service";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { loadJS } from "@web/core/assets";

export class PropertyDashboard extends Component {

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.rpc = this.env.services.rpc
        onWillStart(this.onWillStart);
        onMounted(this.onMounted);
    }

    async onWillStart() {
        await this.fetch_property_data();
        await this.getGreetings()
        await loadJS("https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js")
    }

    async onMounted() {
        this.render_property_chart_data();
        this.render_property_filter();
    }

    async getGreetings() {
        var self = this;
        const now = new Date();
        const hours = now.getHours();
        if (hours >= 5 && hours < 12) {
            self.greetings = "Good Morning";
        }
        else if (hours >= 12 && hours < 18) {
            self.greetings = "Good Afternoon";
        }
        else {
            self.greetings = "Good Evening";
        }
    }

    // downloadReport(e) {
    //     e.stopPropagation();
    //     e.preventDefault();

    //     var opt = {
    //         margin: 1,
    //         filename: 'PropertyDashboard.pdf',
    //         image: { type: 'jpeg', quality: 0.98 },
    //         html2canvas: { scale: 2 },
    //         jsPDF: { unit: 'px', format: [1920, 1080], orientation: 'landscape' }
    //     };
    //     html2pdf().set(opt).from(document.getElementById("dashboard")).save()

    // }

    downloadReport() {
        const style = document.createElement('style');
        style.media = 'print';
        style.innerHTML = `
            @media print {
                .o_main_navbar, .o_control_panel { display: none !important; }
                canvas { width: 100% !important; height: auto !important; }
                #downloadBtn { display: none !important; }
                .gridstack-wrapper { background-color: white !important; }
                .card { break-inside: avoid !important; page-break-inside: avoid !important; }
            }
        `;
        document.head.appendChild(style);

        window.dispatchEvent(new Event('resize'));
        setTimeout(() => window.print(), 200);
    }

    _downloadChart(e) {
        const chart = e.target.offsetParent.children[2].children[0]; // Get the chart canvas element
        const imageDataURL = chart.toDataURL('image/png'); // Generate image data URL
        const filename = chart.id + 'PropertyDashboard.png'; // Set your preferred filename
        const link = document.createElement('a');
        link.href = imageDataURL;
        link.download = filename;
        link.click();
    }

    // Filters================================
    render_property_filter() {
        rpc('/all_property_filter').then(function (data) {

            var owners = data[0]
            var partners = data[1]
            var propertys = data[3]
            var recidencys = data[2]
            var durations = data[4]

            owners?.forEach(owner => {
                const option = document.createElement('option');
                option.value = owner?.id;
                option.textContent = owner?.name;
                document.querySelector('#owner_selection')?.appendChild(option);
            });

            partners?.forEach(partner => {
                const option = document.createElement('option');
                option.value = partner?.id;
                option.textContent = partner?.name;
                document.querySelector('#partner_selection')?.appendChild(option);
            });

            propertys?.forEach(property => {
                const option = document.createElement('option');
                option.value = property?.id;
                option.textContent = property?.name;
                document.querySelector('#property_selection')?.appendChild(option);
            });

            recidencys?.forEach(recidency => {
                const option = document.createElement('option');
                option.value = recidency?.id;
                option.textContent = recidency?.name;
                document.querySelector('#recidency_selection')?.appendChild(option);
            });

        })
    }
    _onchangePropertyFilter(ev) {
        this.flag = 1
        var owner_selection = document.querySelector('#owner_selection').value
        var partner_selection = document.querySelector('#partner_selection').value
        var property_selection = document.querySelector('#property_selection').value
        var recidency_selection = document.querySelector('#recidency_selection').value
        var duration_selection = document.querySelector('#duration_selection').value

        this.render_property_chart_data();
        var self = this;

        rpc('/property/filter-apply', {
            'data': {
                'owner': owner_selection,
                'partner': partner_selection,
                'property': property_selection,
                'recidency': recidency_selection,
                'duration': duration_selection,
            }
        }).then(function (data) {

            // count box click that time pass data
            self.total_lead_data = data['total_lead_data']
            self.total_oppertunity_data = data['total_oppertunity_data']
            self.all_owner_data = data['all_owner_data']
            self.all_tenancy_data = data['all_tenancy_data']
            self.rented_property_data = data['rented_property_data']
            self.total_property_data = data['total_property_data']
            self.sellable_property_data = data['sellable_property_data']
            self.all_booking_data = data['all_booking_data']
            self.owner_draft_pay = data['owner_draft_pay']
            self.owner_paid = data['owner_paid']
            self.due_payment_data = data['due_payment_data']
            self.done_payment_data = data['done_payment_data']
            self.payment_data = data['payment_data']

            // after change value display on xml side count
            document.querySelector('#total_lead_data').innerHTML = data['total_lead_data'].length
            document.querySelector('#total_oppertunity_data').innerHTML = data['total_oppertunity_data'].length
            document.querySelector('#all_owner_data').innerHTML = data['all_owner_data'].length
            document.querySelector('#all_tenancy_data').innerHTML = data['all_tenancy_data'].length
            document.querySelector('#rented_property_data').innerHTML = data['rented_property_data'].length
            document.querySelector('#total_property_data').innerHTML = data['total_property_data'].length
            document.querySelector('#sellable_property_data').innerHTML = data['sellable_property_data'].length
            document.querySelector('#all_booking_data').innerHTML = data['all_booking_data'].length
            document.querySelector('#owner_draft_pay').innerHTML = data['owner_draft_pay'].length
            document.querySelector('#owner_paid').innerHTML = data['owner_paid'].length
            document.querySelector('#due_payment_data').innerHTML = data['due_payment_data'].length
            document.querySelector('#done_payment_data').innerHTML = data['done_payment_data'].length
            document.querySelector('#payment_data').innerHTML = data['payment_data'].length
        })
    }
    // // counters-------------------------------
    // fetch_property_data() 
    // {
    //     this.flag = 0
    //     var self = this;
    //     var def1 = rpc('/get/property/tiles/data').then(function (result) 

    //     {

    async fetch_property_data() {
        var self = this;
        const result = await rpc('/get/property/tiles/data');
        self.total_lead_data = result['total_lead_data']
        self.total_oppertunity_data = result['total_oppertunity_data']
        self.all_owner_data = result['all_owner_data']
        self.all_tenancy_data = result['all_tenancy_data']
        self.rented_property_data = result['rented_property_data']
        self.total_property_data = result['total_property_data']
        self.sellable_property_data = result['sellable_property_data']
        self.all_booking_data = result['all_booking_data']
        self.owner_draft_pay = result['owner_draft_pay']
        self.owner_paid = result['owner_paid']
        self.due_payment_data = result['due_payment_data']
        self.done_payment_data = result['done_payment_data']
        self.payment_data = result['payment_data']
        self.user_name = result['user_name']
        self.user_img = result['user_img']
        return result;
    }

    action_property_lead(e) {
        e.stopPropagation();
        e.preventDefault();
        var options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
        //		if (this.flag == 0) {
        var rec_id = e.currentTarget.getAttribute('rec-id');
        var action = e.currentTarget.id || false;
        var domain = false;

        if (action == 'total_lead_datas') {
            domain = [["id", "in", this.total_lead_data]];
        } else if (action == 'total_oppertunity_datas') {
            domain = [["id", "in", this.total_oppertunity_data]]
        } else if (rec_id != 'undefined') {
            domain = [["id", "=", rec_id]]
        }

        this.action.doAction({
            name: _t(" Lead/Oppertunity"),
            type: 'ir.actions.act_window',
            res_model: 'crm.lead',
            domain: domain,
            view_mode: 'list,form',
            views: [
                [false, 'list'],
                [false, 'form']
            ],
            target: 'current'
        }, options)
    }

    action_owner_pay(e) {
        e.stopPropagation();
        e.preventDefault();
        var options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
        //		if (this.flag == 0) {
        var rec_id = e.currentTarget.getAttribute('rec-id');
        var action = e.currentTarget.id || false;
        var domain = false;

        if (action == 'owner_draft_pays') {
            domain = [["id", "in", this.owner_draft_pay]];
        } else if (action == 'owner_paids') {
            domain = [["id", "in", this.owner_paid]]
        }

        this.action.doAction({
            name: _t("Payment Details"),
            type: 'ir.actions.act_window',
            res_model: 'track.owner.payment',
            domain: domain,
            view_mode: 'list,form',
            views: [
                [false, 'list'],
                [false, 'form']
            ],
            target: 'current'
        }, options)
    }

    action_all_owner(e) {
        e.stopPropagation();
        e.preventDefault();
        var options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
        //		if (this.flag == 0) {
        var rec_id = e.currentTarget.getAttribute('rec-id');
        var action = e.currentTarget.id || false;
        var domain = false;

        if (action == 'all_owner_datas') {
            domain = [["id", "in", this.all_owner_data]];
        } else if (rec_id != 'undefined') {
            domain = [["id", "=", rec_id]]
        }

        this.action.doAction({
            name: _t(" All Owner"),
            type: 'ir.actions.act_window',
            res_model: 'res.partner',
            domain: domain,
            view_mode: 'list,form',
            views: [
                [false, 'list'],
                [false, 'form']
            ],
            target: 'current'
        }, options)
    }
    action_all_tenancy(e) {
        e.stopPropagation();
        e.preventDefault();
        var options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
        //		if (this.flag == 0) {
        var rec_id = e.currentTarget.getAttribute('rec-id');
        var action = e.currentTarget.id || false;
        var domain = false;

        if (action == 'all_tenancy_datas') {
            domain = [["id", "in", this.all_tenancy_data]];
        } else if (rec_id != 'undefined') {
            domain = [["id", "=", rec_id]]
        }

        this.action.doAction({
            name: _t(" All Tenancy"),
            type: 'ir.actions.act_window',
            res_model: 'property.tenancy',
            domain: domain,
            view_mode: 'list,form',
            views: [
                [false, 'list'],
                [false, 'form']
            ],
            target: 'current'
        }, options)
    }
    action_rented_property(e) {
        e.stopPropagation();
        e.preventDefault();
        var options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
        //		if (this.flag == 0) {
        var rec_id = e.currentTarget.getAttribute('rec-id');
        var action = e.currentTarget.id || false;
        var domain = false;

        if (action == 'rented_property_datas') {
            domain = [["id", "in", this.rented_property_data]];
        } else if (action == 'sellable_property_datas') {
            domain = [["id", "in", this.sellable_property_data]]
        } else if (action == 'total_property_datas') {
            domain = [["id", "in", this.total_property_data]]
        } else if (rec_id != 'undefined') {
            domain = [["id", "=", rec_id]]
        }

        this.action.doAction({
            name: _t("All Property"),
            type: 'ir.actions.act_window',
            res_model: 'property.property',
            domain: domain,
            view_mode: 'list,form',
            views: [
                [false, 'list'],
                [false, 'form']
            ],
            target: 'current'
        }, options)
    }
    action_booking_property(e) {
        e.stopPropagation();
        e.preventDefault();
        var options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
        //		if (this.flag == 0) {
        var rec_id = e.currentTarget.getAttribute('rec-id');
        var action = e.currentTarget.id || false;
        var domain = false;

        if (action == 'all_booking_datas') {
            domain = [["id", "in", this.all_booking_data]];
        } else if (rec_id != 'undefined') {
            domain = [["id", "=", rec_id]]
        }

        this.action.doAction({
            name: _t(" Salleble Property"),
            type: 'ir.actions.act_window',
            res_model: 'property.booking',
            domain: domain,
            view_mode: 'list,form',
            views: [
                [false, 'list'],
                [false, 'form']
            ],
            target: 'current'
        }, options)
    }
    action_payment_property(e) {
        e.stopPropagation();
        e.preventDefault();
        var options = {
            on_reverse_breadcrumb: this.on_reverse_breadcrumb,
        };
        //		if (this.flag == 0) {
        var rec_id = e.currentTarget.getAttribute('rec-id');
        var action = e.currentTarget.id || false;
        var domain = false;
        if (action == 'due_payment_datas') {
            domain = [["id", "in", this.due_payment_data]];
        } else if (action == 'done_payment_datas') {
            domain = [["id", "in", this.done_payment_data]]
        } else if (action == 'payment_datas') {
            domain = [["id", "in", this.payment_data]]
        } else if (rec_id != 'undefined') {
            domain = [["id", "=", rec_id]]
        }

        this.action.doAction({
            name: _t("Invoice"),
            type: 'ir.actions.act_window',
            res_model: 'account.move',
            domain: domain,
            view_mode: 'list,form',
            views: [
                [false, 'list'],
                [false, 'form']
            ],
            target: 'current'
        }, options)
    }

    // Chart=========================
    async render_property_chart_data() {


        var owner_selection = document.querySelector('#owner_selection').value
        var partner_selection = document.querySelector('#partner_selection').value
        var property_selection = document.querySelector('#property_selection').value
        var recidency_selection = document.querySelector('#recidency_selection').value
        var duration_selection = document.querySelector('#duration_selection').value
        var source_chart_selection = document.querySelector('#source_chart_selection').value
        var deal_chart_selection = document.querySelector('#deal_chart_selection').value
        var type_chart_selection = document.querySelector('#type_chart_selection').value
        var all_payment_chart_selection = document.querySelector('#all_payment_chart_selection').value

        var self = this;

        await rpc("/property/chart/data", {
            'data': {
                'owner_id': owner_selection,
                'partner_id': partner_selection,
                'property_id': property_selection,
                'recidency_id': recidency_selection,
                'duration': duration_selection,
            }
        }).then(function (data) {
            var ctx = document.querySelector("#source_chart_data");
            if (!ctx) return;

            if (ctx.chart) {
                ctx.chart.destroy(); // Destroy the existing chart instance
            }
            var newChart = new Chart(ctx, {
                type: source_chart_selection,
                data: data.source_chart_data,
                options: {
                    maintainAspectRatio: false,

                    onClick: (evt, elements) => {
                        if (elements.length > 0) {
                            const element = elements[0];
                            const clickedIndex = element.index;
                            const clickedLabel = data.source_chart_data.labels[clickedIndex];
                            const clickedValue = data.source_chart_data.datasets[0].detail[clickedIndex]
                            var options = {
                            };
                            self.action.doAction({
                                name: _t(clickedLabel),
                                type: 'ir.actions.act_window',
                                res_model: 'crm.lead',
                                domain: [["id", "in", clickedValue]],
                                view_mode: 'list,form',
                                views: [
                                    [false, 'list'],
                                    [false, 'form']
                                ],
                                target: 'current'
                            }, options)
                        } else {
                        }
                    }
                }
            });
            ctx.chart = newChart;
            var ctx = document.querySelector("#deal_chart_data");
            if (!ctx) return;

            if (ctx.chart) {
                ctx.chart.destroy(); // Destroy the existing chart instance
            }
            var newChart = new Chart(ctx, {
                type: deal_chart_selection,
                data: data.deal_chart_data,
                options: {
                    maintainAspectRatio: false,

                    onClick: (evt, elements) => {
                        if (elements.length > 0) {
                            const element = elements[0];
                            const clickedIndex = element.index;
                            const clickedLabel = data.deal_chart_data.labels[clickedIndex];
                            const clickedValue = data.deal_chart_data.datasets[0].detail[clickedIndex]
                            var options = {
                            };
                            self.action.doAction({
                                name: _t(clickedLabel),
                                type: 'ir.actions.act_window',
                                res_model: 'property.booking',
                                domain: [["id", "in", clickedValue]],
                                view_mode: 'list,form',
                                views: [
                                    [false, 'list'],
                                    [false, 'form']
                                ],
                                target: 'current'
                            }, options)
                        } else {
                        }
                    }
                }
            });
            ctx.chart = newChart;
            var ctx = document.querySelector("#type_chart_data");
            if (!ctx) return;

            if (ctx.chart) {
                ctx.chart.destroy(); // Destroy the existing chart instance
            }
            var newChart = new Chart(ctx, {
                type: type_chart_selection,
                data: data.type_chart_data,
                options: {
                    maintainAspectRatio: false,

                    onClick: (evt, elements) => {
                        if (elements.length > 0) {
                            const element = elements[0];
                            const clickedIndex = element.index;
                            const clickedLabel = data.type_chart_data.labels[clickedIndex];
                            const clickedValue = data.type_chart_data.datasets[0].detail[clickedIndex]
                            var options = {
                            };
                            self.action.doAction({
                                name: _t(clickedLabel),
                                type: 'ir.actions.act_window',
                                res_model: 'property.property',
                                domain: [["id", "in", clickedValue]],
                                view_mode: 'list,form',
                                views: [
                                    [false, 'list'],
                                    [false, 'form']
                                ],
                                target: 'current'
                            }, options)
                        } else {
                        }
                    }
                }
            });
            ctx.chart = newChart;
            var ctx = document.querySelector("#all_payment_chart_data");
            if (!ctx) return;

            if (ctx.chart) {
                ctx.chart.destroy(); // Destroy the existing chart instance
            }
            var newChart = new Chart(ctx, {
                type: all_payment_chart_selection,
                data: data.all_payment_chart_data,
                options: {
                    maintainAspectRatio: false,

                    onClick: (evt, elements) => {
                        if (elements.length > 0) {
                            const element = elements[0];
                            const clickedIndex = element.index;
                            const clickedLabel = data.all_payment_chart_data.labels[clickedIndex];
                            const clickedValue = data.all_payment_chart_data.datasets[0].detail[clickedIndex]
                            var options = {
                            };
                            self.action.doAction({
                                name: _t(clickedLabel),
                                type: 'ir.actions.act_window',
                                res_model: 'account.payment',
                                domain: [["id", "in", clickedValue]],
                                view_mode: 'list,form',
                                views: [
                                    [false, 'list'],
                                    [false, 'form']
                                ],
                                target: 'current'
                            }, options)
                        } else {
                        }
                    }
                }
            });
            ctx.chart = newChart;
            // =================List===============
            var upcoming_lead_list = data['upcoming_lead_list'];
            var tbody = document.querySelector("#my_table_upcoming_lead_list tbody");
            if (!tbody) {
                console.warn("tbody not found, waiting for DOM...");
                tbody = document.querySelector("#my_table_out_of_stock_list tbody");
            }

            if (tbody) {
                tbody.innerHTML = '';
                for (var i = 0; i < upcoming_lead_list.length; i++) {
                    // Create a new row
                    var row = document.createElement("tr");
                    // Create cells for each property in the object
                    for (var key in upcoming_lead_list[i]) {
                        if (key !== 'id') {
                            var cell = document.createElement("td");
                            if (upcoming_lead_list[i][key].length == 2) {
                                cell.textContent = upcoming_lead_list[i][key][1];
                                row.appendChild(cell);
                            }
                            else if (key === 'date_deadline') {
                                var cell = document.createElement("td");
                                var date_deadline = upcoming_lead_list[i]['date_deadline']
                                if (date_deadline) {
                                    var arr1 = date_deadline.split('-');
                                    cell.textContent = arr1[2] + '-' + arr1[1] + '-' + arr1[0];
                                }
                                else {
                                    cell.textContent = '-'
                                }
                                row.appendChild(cell);
                            }
                            else {
                                if (upcoming_lead_list[i][key] == false) {
                                    cell.textContent = ' ';
                                    row.appendChild(cell);
                                } else {
                                    cell.textContent = upcoming_lead_list[i][key];
                                    row.appendChild(cell);
                                }
                            }

                        }
                    }
                    var buttonCell = document.createElement("td");
                    var button = document.createElement("button");
                    button.textContent = "View";
                    button.setAttribute("data-id", upcoming_lead_list[i].id);
                    button.addEventListener("click", function () {
                        var id = this.getAttribute("data-id");
                        // Call your function with the ID
                        lead_tree_button_function(id);
                    });
                    button.style.backgroundColor = "Pink";
                    button.style.color = "black";
                    button.style.padding = "6px 12px";
                    buttonCell.appendChild(button);
                    row.appendChild(buttonCell);
                    tbody.appendChild(row);
                }
            }

            function lead_tree_button_function(id) {
                var options = {
                };
                self.action.doAction({
                    name: _t("Upcoming Lead"),
                    type: 'ir.actions.act_window',
                    res_model: 'crm.lead',
                    domain: [["id", "=", id]],
                    view_mode: 'list,form',
                    views: [
                        [false, 'list'],
                        [false, 'form']
                    ],
                    target: 'current'
                }, options)
            }

            var pending_rent_list = data['pending_rent_list'];
            var tbody = document.querySelector("#my_table_pending_rent_list tbody");
            if (!tbody) {
                console.warn("tbody not found, waiting for DOM...");
                tbody = document.querySelector("#my_table_out_of_stock_list tbody");
            }

            if (tbody) {
                tbody.innerHTML = '';
                for (var i = 0; i < pending_rent_list.length; i++) {
                    // Create a new row
                    var row = document.createElement("tr");
                    // Create cells for each property in the object
                    for (var key in pending_rent_list[i]) {
                        if (key !== 'id') {
                            var cell = document.createElement("td");
                            if (pending_rent_list[i][key].length == 2) {
                                cell.textContent = pending_rent_list[i][key][1];
                                row.appendChild(cell);
                            }
                            else if (key === 'date') {
                                var cell = document.createElement("td");
                                var date = pending_rent_list[i]['date']
                                if (date) {
                                    var arr1 = date.split('-');
                                    cell.textContent = arr1[2] + '-' + arr1[1] + '-' + arr1[0];
                                }
                                else {
                                    cell.textContent = '-'
                                }
                                row.appendChild(cell);
                            }
                            else {
                                if (pending_rent_list[i][key] == false) {
                                    cell.textContent = ' ';
                                    row.appendChild(cell);
                                } else {
                                    cell.textContent = pending_rent_list[i][key];
                                    row.appendChild(cell);
                                }
                            }

                        }
                    }
                    var buttonCell = document.createElement("td");
                    var button = document.createElement("button");
                    button.textContent = "View";
                    button.setAttribute("data-id", pending_rent_list[i].id);
                    button.addEventListener("click", function () {
                        var id = this.getAttribute("data-id");
                        // Call your function with the ID
                        rent_tree_button_function(id);
                    });
                    button.style.backgroundColor = "Pink";
                    button.style.color = "black";
                    button.style.padding = "6px 12px";
                    buttonCell.appendChild(button);
                    row.appendChild(buttonCell);
                    tbody.appendChild(row);
                }
            }

            function rent_tree_button_function(id) {
                var options = {
                };
                self.action.doAction({
                    name: _t("Pending Rent"),
                    type: 'ir.actions.act_window',
                    res_model: 'rent.schedule',
                    domain: [["id", "=", id]],
                    view_mode: 'list,form',
                    views: [
                        [false, 'list'],
                        [false, 'form']
                    ],
                    target: 'current'
                }, options)
            }
        })
    }
    async _onchangeSourceChart(ev) {
        var owner_selection = document.querySelector('#owner_selection').value
        var partner_selection = document.querySelector('#partner_selection').value
        var property_selection = document.querySelector('#property_selection').value
        var recidency_selection = document.querySelector('#recidency_selection').value
        var duration_selection = document.querySelector('#duration_selection').value
        var source_chart_selection = document.querySelector('#source_chart_selection').value

        var self = this;
        await rpc("/source/chart/data",
            {
                'data':
                {
                    'owner_id': owner_selection,
                    'partner_id': partner_selection,
                    'property_id': property_selection,
                    'recidency_id': recidency_selection,
                    'duration': duration_selection,

                }
            }).then(function (data) {
                var ctx = document.querySelector("#source_chart_data");
                if (!ctx) return;

                if (ctx.chart) {
                    ctx.chart.destroy(); // Destroy the existing chart instance
                }
                var newChart = new Chart(ctx, {
                    type: source_chart_selection,
                    data: data.source_chart_data,
                    options: {
                        maintainAspectRatio: false,

                        onClick: (evt, elements) => {
                            if (elements.length > 0) {
                                const element = elements[0];
                                const clickedIndex = element.index;
                                const clickedLabel = data.source_chart_data.labels[clickedIndex];
                                const clickedValue = data.source_chart_data.datasets[0].detail[clickedIndex]
                                var options = {
                                };
                                self.action.doAction({
                                    name: _t(clickedLabel),
                                    type: 'ir.actions.act_window',
                                    res_model: 'crm.lead',
                                    domain: [["id", "in", clickedValue]],
                                    view_mode: 'list,form',
                                    views: [
                                        [false, 'list'],
                                        [false, 'form']
                                    ],
                                    target: 'current'
                                }, options)
                            } else {
                            }
                        }
                    }
                });
                ctx.chart = newChart;
            });
    }
    async _onchangeDealChart(ev) {
        var owner_selection = document.querySelector('#owner_selection').value
        var partner_selection = document.querySelector('#partner_selection').value
        var property_selection = document.querySelector('#property_selection').value
        var recidency_selection = document.querySelector('#recidency_selection').value
        var duration_selection = document.querySelector('#duration_selection').value
        var deal_chart_selection = document.querySelector('#deal_chart_selection').value

        var self = this;
        await rpc("/deal/chart/data",
            {
                'data':
                {
                    'owner_id': owner_selection,
                    'partner_id': partner_selection,
                    'property_id': property_selection,
                    'recidency_id': recidency_selection,
                    'duration': duration_selection,

                }
            }).then(function (data) {
                var ctx = document.querySelector("#deal_chart_data");
                if (!ctx) return;

                if (ctx.chart) {
                    ctx.chart.destroy(); // Destroy the existing chart instance
                }
                var newChart = new Chart(ctx, {
                    type: deal_chart_selection,
                    data: data.deal_chart_data,
                    options: {
                        maintainAspectRatio: false,

                        onClick: (evt, elements) => {
                            if (elements.length > 0) {
                                const element = elements[0];
                                const clickedIndex = element.index;
                                const clickedLabel = data.deal_chart_data.labels[clickedIndex];
                                const clickedValue = data.deal_chart_data.datasets[0].detail[clickedIndex]
                                var options = {
                                };
                                self.action.doAction({
                                    name: _t(clickedLabel),
                                    type: 'ir.actions.act_window',
                                    res_model: 'property.booking',
                                    domain: [["id", "in", clickedValue]],
                                    view_mode: 'list,form',
                                    views: [
                                        [false, 'list'],
                                        [false, 'form']
                                    ],
                                    target: 'current'
                                }, options)
                            } else {
                            }
                        }
                    }
                });
                ctx.chart = newChart;
            });
    }
    async _onchangeTypeChart(ev) {
        var owner_selection = document.querySelector('#owner_selection').value
        var partner_selection = document.querySelector('#partner_selection').value
        var property_selection = document.querySelector('#property_selection').value
        var recidency_selection = document.querySelector('#recidency_selection').value
        var duration_selection = document.querySelector('#duration_selection').value
        var type_chart_selection = document.querySelector('#type_chart_selection').value

        var self = this;
        await rpc("/type/chart/data",
            {
                'data':
                {
                    'owner_id': owner_selection,
                    'partner_id': partner_selection,
                    'property_id': property_selection,
                    'recidency_id': recidency_selection,
                    'duration': duration_selection,

                }
            }).then(function (data) {
                var ctx = document.querySelector("#type_chart_data");
                if (!ctx) return;

                if (ctx.chart) {
                    ctx.chart.destroy(); // Destroy the existing chart instance
                }
                var newChart = new Chart(ctx, {
                    type: type_chart_selection,
                    data: data.type_chart_data,
                    options: {
                        maintainAspectRatio: false,

                        onClick: (evt, elements) => {
                            if (elements.length > 0) {
                                const element = elements[0];
                                const clickedIndex = element.index;
                                const clickedLabel = data.type_chart_data.labels[clickedIndex];
                                const clickedValue = data.type_chart_data.datasets[0].detail[clickedIndex]
                                var options = {
                                };
                                self.action.doAction({
                                    name: _t(clickedLabel),
                                    type: 'ir.actions.act_window',
                                    res_model: 'property.property',
                                    domain: [["id", "in", clickedValue]],
                                    view_mode: 'list,form',
                                    views: [
                                        [false, 'list'],
                                        [false, 'form']
                                    ],
                                    target: 'current'
                                }, options)
                            } else {
                            }
                        }
                    }
                });
                ctx.chart = newChart;
            });
    }
    async _onchangePaymentChart(ev) {
        var owner_selection = document.querySelector('#owner_selection').value
        var partner_selection = document.querySelector('#partner_selection').value
        var property_selection = document.querySelector('#property_selection').value
        var recidency_selection = document.querySelector('#recidency_selection').value
        var all_payment_chart_selection = document.querySelector('#all_payment_chart_selection').value
        var duration_selection = document.querySelector('#duration_selection').value

        var self = this;
        await rpc("/payment/chart/data",
            {
                'data':
                {
                    'owner_id': owner_selection,
                    'partner_id': partner_selection,
                    'property_id': property_selection,
                    'recidency_id': recidency_selection,
                    'duration': duration_selection,

                }
            }).then(function (data) {
                var ctx = document.querySelector("#all_payment_chart_data");
                if (!ctx) return;

                if (ctx.chart) {
                    ctx.chart.destroy(); // Destroy the existing chart instance
                }
                var newChart = new Chart(ctx, {
                    type: all_payment_chart_selection,
                    data: data.all_payment_chart_data,
                    options: {
                        maintainAspectRatio: false,

                        onClick: (evt, elements) => {
                            if (elements.length > 0) {
                                const element = elements[0];
                                const clickedIndex = element.index;
                                const clickedLabel = data.all_payment_chart_data.labels[clickedIndex];
                                const clickedValue = data.all_payment_chart_data.datasets[0].detail[clickedIndex]
                                var options = {
                                };
                                self.action.doAction({
                                    name: _t(clickedLabel),
                                    type: 'ir.actions.act_window',
                                    res_model: 'account.payment',
                                    domain: [["id", "in", clickedValue]],
                                    view_mode: 'list,form',
                                    views: [
                                        [false, 'list'],
                                        [false, 'form']
                                    ],
                                    target: 'current'
                                }, options)
                            } else {
                            }
                        }
                    }
                });
                ctx.chart = newChart;
            });
    }


}
PropertyDashboard.template = "propertyDashboard"
registry.category("actions").add("open_property_dashboard", PropertyDashboard)
