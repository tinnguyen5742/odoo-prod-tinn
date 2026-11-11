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


class agent_Portal(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        
        if 'agent_commission_property_count' in counters:
            agent_commission_property = request.env['agent.commission'].sudo()
            agent_commission_property_count = agent_commission_property.search_count([
                ('agent_partner_id', '=', request.env.user.partner_id.id)  	 
            ])
            values['agent_commission_property_count'] = agent_commission_property_count
        return values

    @http.route(['/my/agent_commission_property_details', '/my/agent_commission_property_details/page/<int:page>'], type='http', auth="user", website=True)
    def portal_agent_commission_property(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None,
                                 groupby='none', search=None, search_in=None, **kw):
        values = self._prepare_portal_layout_values()
        agent_commission_property_details_pool = request.env['agent.commission'].sudo()

        domain = [
            ('agent_partner_id', '=', request.env.user.partner_id.id)
            
        ]

        searchbar_sortings = {
            'name': {'label': _('Name'), 'order': 'name desc'},
            'rent_id': {'label': _('Rent Property'), 'order': 'rent_id desc'},
            'sell_id': {'label': _('Booking Property'), 'order': 'sell_id desc'},
        }

        # default sortby order
        if not sortby:
            sortby = 'name'
            sortby = 'rent_id'
            sortby = 'sell_id'

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
        sort_order = searchbar_sortings[sortby]['order']

        searchbar_groupby = {
            'none': {'input': 'none', 'label': _('All')},
            'rent_id': {'input': 'rent_id', 'label': _('Rent Property')},
            'sell_id': {'input': 'sell_id', 'label': _('Sell Property')},
            'state': {'input': 'state', 'label': _('Status')},
        }

        property_count = agent_commission_property_details_pool.search_count(domain)
        
        searchbar_inputs = {
            'name': {'input': 'name', 'label': _('Search by Name')},
            'rent_id': {'input': 'rent_id', 'label': _('Search by Rent Property')},
            'sell_id': {'input': 'sell_id', 'label': _('Search by Sell Property')},
            'state': {'input': 'state', 'label': _('Search by Status')},
            
        }

        if not search_in:
            search_in = 'name'
        if search and search_in:
            search_domain = []
            if search_in in ('name', 'all'):
                search_domain = OR([search_domain, [('name', 'ilike', search)]])
            if search_in in ('rent_id', 'all'):
                search_domain = OR([search_domain, [('rent_id', 'ilike', search)]])
            if search_in in ('sell_id', 'all'):
                search_domain = OR([search_domain, [('sell_id', 'ilike', search)]])
            if search_in in ('state', 'all'):
                search_domain = OR([search_domain, [('state', 'ilike', search)]])
           
            domain += search_domain

        pager = portal_pager(
            url="/my/agent_commission_property_details",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 'search_in': search_in,
                      'search': search},
            total=property_count,
            page=page,
            step=self._items_per_page
        )
        property_details = agent_commission_property_details_pool.search(domain, order=sort_order, limit=self._items_per_page,
                                                offset=pager['offset'])
        request.session['agent_commission_history'] = property_details.ids[:100]

        
        if groupby == 'state':
            grouped_property = [request.env['agent.commission'].concat(*g) for k, g in
                                  groupbyelem(property_details, itemgetter('state'))]
        elif groupby == 'rent_id':
            grouped_property = [request.env['agent.commission'].concat(*g) for k, g in
                                  groupbyelem(property_details, itemgetter('rent_id'))]  
        elif groupby == 'sell_id':
            grouped_property = [request.env['agent.commission'].concat(*g) for k, g in
                                  groupbyelem(property_details, itemgetter('sell_id'))]                        
        else:
            grouped_property = [property_details]

        values.update({
            'date': date_begin,
            'property_details': property_details.sudo(),
            'page_name': 'agent_property_details_tree',
            'grouped_property': grouped_property,
            'pager': pager,
            'default_url': '/my/agent_commission_property_details',
            # 'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'search': search,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_groupby': searchbar_groupby,
            'filterby': filterby,
            'sortby': sortby,
            'groupby': groupby,
        })

        return request.render("dev_property_management.portal_agent_commission_properties_details", values)
    
    
