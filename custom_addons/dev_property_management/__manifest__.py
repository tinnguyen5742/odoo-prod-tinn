# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

{
    'name': 'Property Management for Odoo | Real Estate Rental and Booking',
    'version':'19.0.2.1',
    'sequence': 1,
    'category': 'Services',
    'description': """
Property Management for Odoo 19 runs an entire real estate operation inside Odoo. Configure parent properties, auto-generate floors and units for towers, classify each unit as residential, commercial, industrial, or land, and publish the catalogue on your website. Every inquiry becomes either a booking for sale or a tenancy for rent, with paperwork, finance, and reminders handled in one record.

This app adds a dedicated Property menu with masters for property types, amenities, nearby connectivity, parking, land titles, facing, area, cities, flat types, towers, and tags. Each property carries its full profile and can be booked for sale, rented under a tenancy with an auto-generated rent schedule, or published on the website for prospects to browse and enquire. Bookings, tenancies, agreements, agent commissions, and maintenance invoices all link back to the property.

Key features:
- Build parent properties and auto-generate floors and units so towers and apartment blocks set up in minutes.
- Classify properties as residential, commercial, industrial, or land, with amenities, parking, land titles, facing, and area details.
- Publish properties on the public website with search filters, photo galleries, and an inquiry form that drops a lead into the back office.
- Convert any property inquiry into a booking for sale or a tenancy for rent with one click.
- Walk every booking through Draft, Confirmed, and Cancel, then generate the customer invoice and the booking PDF.
- Auto-create a rent schedule on every tenancy with advance rent plus monthly installments and a calendar view of due dates.
- Send agreement expiry and rent reminder emails on the cadence you configure, with built-in mail templates.
- Renew expired agreements with one click and keep every version with documents attached.
- Raise maintenance invoices straight from a tenancy and link them to the property, partner, and tenancy record.
- Track agent commissions as a fixed amount or a percentage of monthly rent on every tenancy or booking.

How it works: to set up property management in Odoo 19, install the module and configure the masters: cities, flat types, amenities, nearby connectivity, parking, land titles, facing, area units, and the residential, commercial, industrial, and land types. Build each tower as a parent property and let the system auto-generate the floors and units.

To run a sale, capture a property inquiry from the website or the back office, qualify it as a CRM lead, then click Convert to Booking. Pick the property, the customer, and the price; the booking walks through Draft, Confirmed, and Cancel, prints the agreement PDF, and posts the customer invoice.

To run a rental, create a tenancy on the property and the system auto-generates the rent schedule with advance rent and monthly installments. Due dates show on a colour-coded calendar, the rent reminder mail goes out on the cadence you set, and the team can raise maintenance invoices from the same tenancy. Agreement expiry mails fire before and on the expiry date, and renewing the agreement is one click.

To see how the portfolio is performing, open the property and booking dashboards for charts, and the Tenancy Analysis and Booking Analysis pivots for slicing by date, agent, city, or type.

Who it's for: property managers, real estate agencies, landlords, brokers, real estate developers, building owners, and property agents who handle sale, rent, agreements, finance, and customer self-service from one place. Useful for residential, commercial, industrial, and land portfolios alike.

Benefits:
- Run sale, rent, agreements, and maintenance from one property record instead of separate spreadsheets and tools.
- Cut tower setup time by auto-generating floors and units rather than typing each one.
- Stop missing rent collection days with built-in rent reminder emails and a calendar of due dates.
- Pay agents accurately with commission tracked as a fixed amount or a percentage of monthly rent.
- Give owners, tenants, and agents portal access so they see their own records and raise maintenance requests without calling the office.

Compatibility: works with Odoo 19 Community and Enterprise, and with the Accounting, Contacts, CRM, Maintenance, Website, and Mail apps.

Install Property Management to run sale, rent, and tenant operations from one place in Odoo 19.
    """,
    'summary': 'Property Management Real Estate Management Property Buy and Sell Buy and Sell Property Software Property Sale Management Property Sale Booking Property Sale CRM Real Estate Sale Software Real Estate Buy and Sell Portal Sell Property Online Buy Property Online Property Sale Pipeline Property Sale Agreement Sale Deed Management Property Sale Invoice Property Sale Commission Property Marketplace Property Selling System Buyer Inquiry Capture Real Estate Listing Sale Rental Property Management Tenancy Management Property Booking Landlord Software Real Estate CRM Lease Management Tenant Management Property Rental System Real Estate Agency Software Property Listing Portal Residential Property Management Commercial Property Management Industrial Property Management Land Property Management Tower and Apartment Management Rent Schedule Tracker Rent Reminder Email Agreement Management Lease Agreement Renewal Property Maintenance Workflow Real Estate Agent Commission Property Dashboard Sub-Property Auto Generation Due Rent Report Booking and Tenancy Workflow Property Inquiry Lead Capture Property Owner Portal Tenant Portal Self-Service',
    'depends': ['account', 'mail', 'contacts','website','crm','maintenance'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'demo/amenities_data.xml',
        'demo/configuration_demo_data.xml',
        'demo/nearby_connectivity_data.xml',
        'demo/residential_type_data.xml',
        'demo/commercial_type_data.xml',
        'demo/industrial_type_data.xml',
        'demo/rent_type_data.xml',
        'demo/maintenance_type_data.xml',
        'demo/city_data.xml',
        'demo/flat_type_data.xml',
        'demo/Property_data.xml',
        'demo/Property_rent_data.xml',
        'demo/Property_land_data.xml',
        'demo/Property_commercial_data.xml',
        'demo/Property_industrial_data.xml',
        'demo/Property_commercial_sell_data.xml',
        'data/sequence_property.xml',
        'data/sequence_booking.xml',
        'data/sequence_agreement.xml',
        'data/sequence_tenancy.xml',
        'data/sequence_rent.xml',
        'data/lead_sequence.xml',
        'data/template_agreement_expiry_before_days.xml',
        'data/template_agreement_expiry_same_day.xml',
        'data/template_rent_before_days.xml',
        'data/template_rent_same_day.xml',
        'data/cron_agreement_expiry.xml',
        'data/cron_rent_reminder.xml',
        'data/cron_rent_generate_invoice.xml',
        'data/website_menu.xml',
        'views/main_menus.xml',
        'views/lead.xml',
        'views/res_config_settings.xml',
        'views/tags.xml',
        'views/residential_type.xml',
        'views/commercial_type.xml',
        'views/industrial_type.xml',
        'views/amenities.xml',
        'views/nearby_connectivity.xml',
        'views/rent_type.xml',
        'views/maintenance_type.xml',
        'views/partner.xml',
        'views/parent_property.xml',
        'views/property.xml',
        'views/owner.xml',
        'views/tenant.xml',
        'views/agent.xml',
        'views/agreement_template.xml',
        'views/land_title_view.xml',
        'views/parking_space_view.xml',
        'views/facing.xml',
        'views/area_manage_view.xml',
        'views/payments.xml',
        'wizard/maintenance_invoice.xml',
        'wizard/agreement_window.xml',
        'wizard/renew_agreement_window.xml',
        'wizard/add_documents.xml',
        'views/tenancy.xml',
        'views/rent_schedule.xml',
        'views/booking.xml',
        'views/track_owner_payment.xml',
        'wizard/booking_window.xml',
        'views/documents.xml',
        'views/account_move_view.xml',
        'views/maintenance_view.xml',
        'views/agreements.xml',
        'report/tenancy_analysis.xml',
        'report/booking_analysis.xml',
        'report/tenancy_pdf_template.xml',
        'report/tenancy_pdf_menu.xml',
        'report/booking_pdf_template.xml',
        'report/booking_pdf_menu.xml',
        'report/agreement_pdf_template.xml',
        'report/agreement_pdf_menu.xml',
        'report/property_pdf_template.xml',
        'report/property_pdf_menu.xml',
        'report/booking_history_pdf_template.xml',
        'report/booking_history_pdf_menu.xml',
        'wizard/booking_history_report.xml',
        'report/due_rent_pdf_menu.xml',
        'report/due_rent_pdf_template.xml',
        'wizard/due_rent_report.xml',
        'portal_view/portal_owner_property_view.xml',
        'portal_view/portal_tenant_property_view.xml',
        'portal_view/maintenance_request.xml',
        # 'portal_view/portal_property_view.xml',
        
        'portal_view/property_details_registration.xml',
        'portal_view/lead_sequence.xml',
        
        # ===website===
        'portal_view/portal_rent_property_view.xml',
        'portal_view/portal_sell_property_view.xml',
        'portal_view/portal_residential_view.xml',
        'portal_view/portal_commercial_view.xml',
        'portal_view/portal_industrial_view.xml',
        'portal_view/portal_land_view.xml',

        'views/website/website_property_home.xml',
        'views/website/website_property_listing.xml',
        'views/website/website_property_detail.xml',
        # =======
        'data/template_agreement_send_by_mail.xml',
        'views/city.xml',
        'views/tower_tower.xml',
        'views/flat_type.xml',
        'data/sequence_agent.xml',
        'views/agent_commission.xml',
        'views/dashboard.xml',
        'portal_view/portal_agent_commissin_view.xml',

        
        
    ],
    'assets': {
        'web.assets_backend': [
            'dev_property_management/static/src/js/dashboard.js',
            'dev_property_management/static/src/js/bookpropertyDashboard.js',
            'dev_property_management/static/src/js/chart_chart.js',
            'dev_property_management/static/src/css/dashboard_new.css',
            'dev_property_management/static/src/xml/dashboard_templates.xml',
            'dev_property_management/static/src/xml/bookproperty_dashboard.xml',
        ],
        'web.assets_frontend': [
            'dev_property_management/static/src/css/website_property.css',
            'dev_property_management/static/src/js/website_property.js',
        ],
    },
    'demo': [],
    'test': [],
    'css': [],
    'qweb': [],
    'js': [],
    'images': ['images/main_screenshot.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    
    #author and support Details
    'author': 'DevIntelle Consulting Service Pvt.Ltd',
    'website': 'https://www.devintellecs.com',    
    'maintainer': 'DevIntelle Consulting Service Pvt.Ltd', 
    'support': 'devintelle@gmail.com',
    'price':149.0,
    'currency':'EUR',
    #'live_test_url':'https://youtu.be/A5kEBboAh_k',
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
