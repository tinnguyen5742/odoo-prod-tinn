from odoo.addons.portal.controllers.portal import CustomerPortal

from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo import fields, http, _
# from odoo.addons.portal.controllers.mail import _message_post_helper
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager, get_records_pager
from odoo.osv import expression
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from datetime import timedelta
from odoo.tools import groupby as groupbyelem
from operator import itemgetter
from odoo.osv.expression import OR
from collections import OrderedDict
import werkzeug



class Tenant_Portal(CustomerPortal):
    # def _prepare_home_portal_values(self, counters):
    #     values = super()._prepare_home_portal_values(counters)
    #     tenant_property = request.env['property.tenancy']
    #     tenant_property_count = tenant_property.search_count([
    #         ('partner_id', '=', request.env.user.partner_id.id)
    #         ]
    #         #  ('state', '!=', 'draft')
    #     )
    #     values['tenant_property_count'] = tenant_property_count
    #     return values
    
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        
        if 'tenant_property_count' in counters:
            tenant_property = request.env['property.tenancy'].sudo()
            tenant_property_count = tenant_property.search_count([
                ('partner_id', '=', request.env.user.partner_id.id)  	 
            ])
            values['tenant_property_count'] = tenant_property_count
        return values

    @http.route(['/my/tenant_property_details', '/my/tenant_property_details/page/<int:page>'], type='http', auth="user", website=True)
    def portal_tenant_property(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None,
                                 groupby='none', search=None, search_in=None, **kw):
        values = self._prepare_portal_layout_values()
        property_details_pool = request.env['property.tenancy']

        domain = [
            ('partner_id', '=', request.env.user.partner_id.id)
            # ('partner_id', '=', request.env.user.partner_id.id),
            # ('state', '!=', 'draft')
        ]

        searchbar_sortings = {
            'name': {'label': _('Name'), 'order': 'name desc'},
            'property_type': {'label': _('Property Type'), 'order': 'property_type desc'},
            'confirmation_date': {'label': _('Confirmation Name'), 'order': 'confirmation_date desc'},
        }

        # default sortby order
        # default sortby order
        if not sortby:
            sortby = 'confirmation_date'

        if groupby == 'owner_partner_id':
             sortby = 'owner_partner_id'
        elif groupby == 'state':
             sortby = 'state'
        elif groupby == 'property_type':
             sortby = 'property_type'

        today = fields.Date.today()
        this_week_end_date = fields.Date.to_string(fields.Date.from_string(today) + timedelta(days=7))
        week_ago = datetime.today() - timedelta(days=7)
        month_ago = (datetime.today() - relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
        starting_of_year = datetime.now().date().replace(month=1, day=1)
        ending_of_year = datetime.now().date().replace(month=12, day=31)

        def sd(date):
            return fields.Datetime.to_string(date)

        def previous_week_range(date):
            start_date = date + timedelta(-date.weekday(), weeks=-1)
            end_date = date + timedelta(-date.weekday() - 1)
            return {'start_date': start_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'end_date': end_date.strftime('%Y-%m-%d %H:%M:%S')}

        searchbar_filters = {
            'all': {'label': _('All'), 'domain': []},
            'today': {'label': _('Today'),
                      'domain': [('date', '>=', datetime.strftime(date.today(), '%Y-%m-%d 00:00:00')),
                                 ('date', '<=', datetime.strftime(date.today(), '%Y-%m-%d 23:59:59'))]},
            'yesterday': {'label': _('Yesterday'), 'domain': [('date', '=', datetime.strftime(date.today() - timedelta(days=1), '%Y-%m-%d 00:00:00'))]},
            'week': {'label': _('This Week'),
                     'domain': [('date', '>=', sd(datetime.today() + relativedelta(days=-today.weekday()))),
                                ('date', '<=', this_week_end_date)]},
            'last_seven_days': {'label': _('Last 7 Days'),
                                'domain': [('date', '>=', sd(week_ago)),
                                           ('date', '<=', sd(datetime.today()))]},
            'last_week': {'label': _('Last Week'),
                          'domain': [('date', '>=', previous_week_range(datetime.today()).get('start_date')),
                                     ('date', '<=', previous_week_range(datetime.today()).get('end_date'))]},

            'last_month': {'label': _('Last 30 Days'),
                           'domain': [('date', '>=', month_ago), ('date', '<=', sd(datetime.today()))]},
            'month': {'label': _('This Month'),
                      'domain': [
                          ("date", ">=", sd(today.replace(day=1))),
                          ("date", "<",
                           (today.replace(day=1) + relativedelta(months=1)).strftime('%Y-%m-%d 00:00:00'))
                      ]
                      },
            'year': {'label': _('This Year'),
                     'domain': [
                         ("date", ">=", sd(starting_of_year)),
                         ("date", "<=", sd(ending_of_year)),
                     ]
                     }
        }
        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']
        
        if groupby == 'owner_partner_id':
             sortby = 'name'
        elif groupby == 'state':
             sortby = 'state'
        elif groupby == 'property_type':
             sortby = 'property_type'
             
        sort_order = searchbar_sortings[sortby]['order']

        searchbar_groupby = {
            'none': {'input': 'none', 'label': _('All')},
            'owner_partner_id': {'input': 'owner_partner_id', 'label': _('Owner')},
            'property_type': {'input': 'property_type', 'label': _('Property Type')},
            'state': {'input': 'state', 'label': _('Status')},
        }

        property_count = property_details_pool.search_count(domain)
        
        searchbar_inputs = {
            'name': {'input': 'name', 'label': _('Search by Name')},
            'property_type': {'input': 'property_type', 'label': _('Search by Property Type')},
            'state': {'input': 'state', 'label': _('Search by Status')},
            # 'partner_id': {'input': 'partner_id', 'label': _('Search by Customer')},
            # 'email': {'input': 'email', 'label': _('Search by Email')},
        }

        if not search and search_in:
            search_in = 'name'
        if search and search_in:
            search_domain = []
            if search_in in ('name'):
                search_domain = [('name', 'ilike', search)]
            if search_in in ('property_type'):
                search_domain = [('property_type', 'ilike', search)]
            if search_in in ('state'):
                search_domain = [('state', 'ilike', search)]
            if search_in in ('all'):
                search_domain = ['|','|','|','|',('name', 'ilike', search),('property_type', 'ilike', search),('state', 'ilike', search),
                                ('property_id', 'ilike', search)]
            domain += search_domain

        pager = portal_pager(
            url="/my/tenant_property_details",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 'search_in': search_in,
                      'search': search},
            total=property_count,
            page=page,
            step=self._items_per_page
        )
        property_details = property_details_pool.search(domain, order=sort_order, limit=self._items_per_page,
                                                offset=pager['offset'])
        request.session['booking_history'] = property_details.ids[:100]

        if groupby == 'owner_partner_id':
            grouped_property = [request.env['property.tenancy'].concat(*g) for k, g in
                                  groupbyelem(property_details, itemgetter('owner_partner_id'))]
        elif groupby == 'state':
            grouped_property = [request.env['property.tenancy'].concat(*g) for k, g in
                                  groupbyelem(property_details, itemgetter('state'))]
        elif groupby == 'property_type':
            grouped_property = [request.env['property.tenancy'].concat(*g) for k, g in
                                  groupbyelem(property_details, itemgetter('property_type'))]                          
        else:
            grouped_property = [property_details]

        values.update({
            'date': date_begin,
            'property_details': property_details.sudo(),
            'page_name': 'tenant_property_tree',
            'grouped_property': grouped_property,
            'pager': pager,
            'default_url': '/my/tenant_property_details',
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'search': search,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_groupby': searchbar_groupby,
            'filterby': filterby,
            'sortby': sortby,
            'groupby': groupby,
        })

        return request.render("dev_property_management.portal_tenant_properties_details", values)
    
    @http.route(['/my/tenant_property_details/<int:order_id>'], type='http', auth="public", website=True)
    def portal_tenant_property_detail_page(self, order_id, report_type=None, access_token=None, message=False, download=False,
                                   **kw):
        try:
            tenant_property_sudo = self._document_check_access('property.tenancy', order_id,
                                                              access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if report_type in ('html', 'pdf', 'text'):
                return self._show_report(model=tenant_property_sudo, report_type=report_type,report_ref='dev_property_management.menu_tenancy_pdf_template',download=download)

        values = {
            'tenant_property_sudo': tenant_property_sudo,
            'page_name': 'property_details_page',
            'report_type': 'html',
            'token': access_token,
            # 'bootstrap_formatting': True,
        }
        # if owner_property_sudo.company_id:
        #     values['res_company'] = owner_property_sudo.company_id
        if tenant_property_sudo.name:
            history = request.session.get('booking_history', [])
        values.update(get_records_pager(history, tenant_property_sudo))
        return request.render('dev_property_management.portal_tenant_property_detail_form', values)
   
