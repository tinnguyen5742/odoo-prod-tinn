
import { registry } from '@web/core/registry';
const { Component, onWillStart, onMounted, onWillRender, useState, useRef } = owl;
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";

export class bookingDashboard extends Component {
    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.rpc = this.env.services.rpc;
        this.state = useState({
            booking_data: { value: [] },
            type_chart_data: { value: {} },
            user_name: { value: 'User Image' },
            user_img: { value: 'User Name' }
        });
        onWillStart(this.onWillStart);
        onMounted(this.onMounted);
        onWillRender(this.onWillRender);
    }

    async onWillStart() {
        await this.getUserDetail();
        await this.getGreetings();
        await loadJS("https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js");
    }

    async onWillRender() {
        // This can be used if you need something before the component renders.
    }

    async onMounted() {
        await this.renderbookingDashboardFilter();
        await this.getBookingData();
        // this.render_upcoming_reservation_list(this.state.rowsPerPage, this.state.currentUpcResLst_page);
    }

    async getUserDetail() {
        var self = this;
        rpc('/booking/property_filter').then(function (response) {
            self.state.user_name.value = response['user_name'];
            self.state.user_img.value = response['user_img'];
        });
    }

    getBookingData(requestData) {
        var self = this;
        var request = {};

        if (requestData) {
            request = requestData;
        }

        rpc('/get/booking', { 'request': request }).then(function (response) {
            console.log("Response from the server:", response);

            if (response && response.property_groups && response.property_booking_data) {
                self.state.booking_data.value = response.property_groups; // Use property_groups for the calendar
                self.preparebookingCalender(response.property_booking_data); // Pass property_booking_data to the calendar function

                if (response[1] && response[1].type_chart_data) {
                    self.renderChart(response[1].type_chart_data);
                } else {
                    console.warn("No data received from the server.");
                }
            } else {
                console.warn("No booking data or property data received from the server.");
                self.state.booking_data.value = [];
                self.preparebookingCalender([]); // Pass empty data to preparebookingCalender
            }
        }).catch(function (error) {
            console.error("Error during RPC call:", error);
        });
    }

    async preparebookingCalender(propertyBookingData) {
        var self = this;
        var tbody = document.querySelector("#bookingCalender tbody");
        tbody.innerHTML = ''; // Clear existing table body

        // Ensure property_booking_data exists and is an object
        if (propertyBookingData && typeof propertyBookingData === 'object') {

            Object.keys(propertyBookingData).forEach(function (mainProperty) {
                let subProperties = propertyBookingData[mainProperty];

                // Create a row for the main property in the first column
                let tr = document.createElement('tr');

                // Create the first cell for the main property with grey background color
                let td = document.createElement('td');
                // td.style = "border:1px solid #d6d6d6; text-align:center; font-weight:600; background-color: #f0f0f0;";  // grey background
                td.style = "border:1px solid #d6d6d6; text-align:center; font-weight:800; font-size:17px;background-color: #f0f0f0; height: 90px;";
                td.textContent = mainProperty;
                tr.appendChild(td);

                // Create empty cells for sub-properties in the first row
                for (let i = 0; i < 5; i++) {
                    var emptyCell = document.createElement('td');
                    emptyCell.style = "text-align:center;background-color: #f0f0f0;";
                    tr.appendChild(emptyCell);
                }

                tbody.appendChild(tr); // Add the row for the main property

                // Now, create rows for sub-properties
                for (let i = 0; i < subProperties.length; i += 5) {
                    tr = document.createElement('tr'); // New row for sub-properties

                    // Create empty first cell (to align with the main property)
                    let emptyCell = document.createElement('td');
                    emptyCell.style = "text-align:center;";
                    tr.appendChild(emptyCell);

                    // Add up to 5 sub-properties to the current row
                    for (let j = i; j < i + 5; j++) {
                        // Skip this iteration if the subProperty is invalid (e.g., undefined or null)
                        if (!subProperties[j]) {
                            continue; // Skip adding a <td> for missing sub-property
                        }

                        var subPropertyTd = document.createElement('td');
                        subPropertyTd.style = "border:1px solid #d6d6d6; font-size:15px; text-align:left; height: 110px;";

                        var subProperty = subProperties[j];
                        var span = document.createElement('span');
                        span.style = "display:block; margin:5px 2px 5px 6px; cursor:pointer;";
                        // span.textContent = subProperty.sub_property_name + " - " + subProperty.owner+subProperty.booking_status;
                        // span.textContent = subProperty.sub_property_name + " - " + subProperty.owner + " - " + subProperty.booking_status;
                        span.innerHTML = `
                        
                        <strong>Owner:</strong> ${subProperty.owner[1] ? subProperty.owner[1] : ' '}<br>
                        <strong>Sub-property:</strong> ${subProperty.sub_property_name}<br>
                        <strong>Status:</strong> ${subProperty.booking_status}
                    `;

                        if (subProperty.booking_status === "BO" || subProperty.booking_status === "ONR") {
                            span.style.backgroundColor = "rgba(237, 84, 122, 0.4)";
                            span.style.margin = "1px 1px 1px 3px"; // Set margin directly here
                            span.style.padding = "11px";
                        }

                        // Add click event for sub-property details
                        span.addEventListener("click", (function (subId) {
                            return function () {
                                self.openPropertyDetails(subId);
                            };
                        })(subProperty.id));

                        subPropertyTd.appendChild(span);
                        tr.appendChild(subPropertyTd); // Add sub-property cell to the row
                    }

                    tbody.appendChild(tr); // Add the row for sub-properties
                }
            });
        } else {
            console.warn("property_booking_data is not available or is in an incorrect format.");
        }
    }
    // Function to open the property details based on the clicked property ID
    openPropertyDetails(id) {
        var self = this;
        self.action.doAction({
            name: _t("Booking"),
            type: 'ir.actions.act_window',
            res_model: 'property.property',
            domain: [["id", "in", [id]]],
            view_mode: 'list,form',
            views: [
                [false, 'list'],
                [false, 'form']
            ],
            target: 'current'
        });
    }

    // Function to open the main property details based on the clicked parent property ID
    mainPropertyDetails(id) {
        var self = this;
        self.action.doAction({
            name: _t("Booking"),
            type: 'ir.actions.act_window',
            res_model: 'property.property',
            domain: [["id", "in", [id]]],
            view_mode: 'list,form',
            views: [
                [false, 'list'],
                [false, 'form']
            ],
            target: 'current'
        });
    }

    async getGreetings() {
        var self = this;
        const now = new Date();
        const hours = now.getHours();
        if (hours >= 5 && hours < 12) {
            self.greetings = "Good Morning";
        } else if (hours >= 12 && hours < 18) {
            self.greetings = "Good Afternoon";
        } else {
            self.greetings = "Good Evening";
        }
    }

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

    renderbookingDashboardFilter() {
        rpc('/booking_property/all_filter').then(function (data) {

            var ownerrs = data[0];
            ownerrs?.forEach(ownerr => {
                const option = document.createElement('option');
                option.value = ownerr.id;
                option.textContent = ownerr.name;
                document.querySelector('#ownerr_selection')?.appendChild(option);
            });
            var main_propertys = data[1];
            main_propertys?.forEach(main_property => {
                const option = document.createElement('option');
                option.value = main_property.id;
                option.textContent = main_property.name;
                document.querySelector('#main_property_selection')?.appendChild(option);
            });
            var sub_propertys = data[2];
            sub_propertys?.forEach(sub_property => {
                const option = document.createElement('option');
                option.value = sub_property.id;
                option.textContent = sub_property.name;
                document.querySelector('#sub_property_selection')?.appendChild(option);
            });
            var book_unbooks = data[3];
            book_unbooks?.forEach(book_unbook => {
                const option = document.createElement('option');
                option.value = book_unbook.id;
                option.textContent = book_unbook.name;
                document.querySelector('#book_unbook_selection')?.appendChild(option);
            });
            var propertyys = data[4];
            propertyys?.forEach(propertyy => {
                const option = document.createElement('option');
                option.value = propertyy.id;
                option.textContent = propertyy.name;
                document.querySelector('#propertyy_selection')?.appendChild(option);
            });
        });
    }

    _onchangebookingFilter(ev) {
        var ownerr_selection = document.querySelector('#ownerr_selection').value;
        var main_property_selection = document.querySelector('#main_property_selection').value;
        var sub_property_selection = document.querySelector('#sub_property_selection').value;
        var book_unbook_selection = document.querySelector('#book_unbook_selection').value;
        var propertyy_selection = document.querySelector('#propertyy_selection').value;

        const requestData = {
            'ownerr': ownerr_selection, 'main_property': main_property_selection, 'sub_property': sub_property_selection,
            'book_unbook': book_unbook_selection, 'propertyy': propertyy_selection
        };
        this.getBookingData(requestData);
    }
}

bookingDashboard.template = "bookingDashboard";
registry.category("actions").add("open_booking_property_dashboard", bookingDashboard);
