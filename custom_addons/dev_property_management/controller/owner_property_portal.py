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



class Owner_Portal(CustomerPortal):
    # def _prepare_home_portal_values(self, counters):
    #     values = super()._prepare_home_portal_values(counters)
    #     Owner_property = request.env['property.property']
    #     owner_property_count = Owner_property.search_count([
    #          ('owner_partner_id', '=', request.env.user.partner_id.id)]
            
    #     )
        
    #     values['property_count'] = owner_property_count
    #     return values
    
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        
        if 'owner_property_count' in counters:
            Owner_property = request.env['property.property'].sudo()
            owner_property_count = Owner_property.search_count([
                ('owner_partner_id', '=', request.env.user.partner_id.id)  	 
            ])
            values['owner_property_count'] = owner_property_count
        return values

    @http.route(['/my/Owner_property_details', '/my/Owner_property_details/page/<int:page>'], type='http', auth="user", website=True)
    def portal_property(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None,
                                 groupby='none', search=None, search_in=None, **kw):
        values = self._prepare_portal_layout_values()
        property_details_pool = request.env['property.property']
        
        domain = [
            ('owner_partner_id', '=', request.env.user.partner_id.id)
            
        ]

        searchbar_sortings = {
            'number': {'label': _('Number'), 'order': 'number desc'},
            'property_type': {'label': _('Property Type'), 'order': 'property_type desc'},
            'owner_partner_id': {'label': _('Owner Name'), 'order': 'owner_partner_id desc'},
            'property_purpose': {'label': _('Purpose'), 'order': 'property_purpose desc'},
            'state': {'label': _('Status'), 'order': 'state desc'},
        }

        # default sortby order
        if not sortby:
            sortby = 'number'
            
        if groupby == 'property_purpose':
             sortby = 'property_purpose'
        elif groupby == 'state':
             sortby = 'state'
        elif groupby == 'property_type':
             sortby = 'property_type'

        sort_order = searchbar_sortings[sortby]['order']

        searchbar_groupby = {
            'none': {'input': 'none', 'label': _('All')},
            'property_purpose': {'input': 'property_purpose', 'label': _('Purpose')},
            'property_type': {'input': 'property_type', 'label': _('Property Type')},
            'state': {'input': 'state', 'label': _('Status')},
        }

        property_count = property_details_pool.search_count(domain)
        
        searchbar_inputs = {
            'number': {'input': 'number', 'label': _('Search by Number')},
            'property_type': {'input': 'property_type', 'label': _('Search by Property Type')},
            'state': {'input': 'state', 'label': _('Search by Status')},
           
        }

        if not search and search_in:
            search_in = 'number'
        if search and search_in:
            search_domain = []
            if search_in in ('number'):
                search_domain = [('number', 'ilike', search)]
            if search_in in ('property_type'):
                search_domain = [('property_type', 'ilike', search)]
            if search_in in ('state'):
                search_domain = [('state', 'ilike', search)]
            if search_in in ('property_purpose'):
                search_domain = [('property_purpose', 'ilike', search)]
            if search_in in ('all'):
                search_domain = ['|','|','|','|',('number', 'ilike', search),('property_type', 'ilike', search),('state', 'ilike', search),
                                ('property_purpose', 'ilike', search)]
            domain += search_domain



        pager = portal_pager(
            url="/my/Owner_property_details",
            url_args={'date_bproperty_typein': date_begin, 'date_end': date_end, 'sortby': sortby, 'search_in': search_in,
                      'search': search},
            total=property_count,
            page=page,
            step=self._items_per_page
        )
        property_details = property_details_pool.search(domain, order=sort_order, limit=self._items_per_page,
                                                offset=pager['offset'])
        request.session['booking_history'] = property_details.ids[:100]

        
        if groupby == 'state':
            grouped_property = [request.env['property.property'].concat(*g) for k, g in
                                  groupbyelem(property_details, itemgetter('state'))]
        elif groupby == 'property_purpose':
            grouped_property = [request.env['property.property'].concat(*g) for k, g in
                                  groupbyelem(property_details, itemgetter('property_purpose'))]
        elif groupby == 'property_type':
            grouped_property = [request.env['property.property'].concat(*g) for k, g in
                                  groupbyelem(property_details, itemgetter('property_type'))]                          
        else:
            grouped_property = [property_details]

        values.update({
            'date': date_begin,
            'property_details': property_details.sudo(),
            'page_name': 'property_details_tree',
            'grouped_property': grouped_property,
            'pager': pager,
            'default_url': '/my/Owner_property_details',
            # 'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'search': search,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_groupby': searchbar_groupby,
            # 'filterby': filterby,
            'sortby': sortby,
            'groupby': groupby,
        })

        return request.render("dev_property_management.portal_owner_properties_details", values)
    
    @http.route(['/my/Owner_property_details/<int:order_id>'], type='http', auth="public", website=True)
    def portal_owner_property_detail_page(self, order_id, report_type=None, access_token=None, message=False, download=False,
                                   **kw):
        print('====================================fromproperty====================')
        try:
            owner_property_sudo = self._document_check_access('property.property', order_id,
                                                              access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if report_type in ('html', 'pdf', 'text'):
                return self._show_report(model=owner_property_sudo, report_type=report_type,report_ref='dev_property_management.menu_property_pdf_template',download=download)

        values = {
            'owner_property_sudo': owner_property_sudo,
            'page_name': 'property_details_pages',
            'report_type': 'html',
            'token': access_token,
            # 'bootstrap_formatting': True,
        }
        # if owner_property_sudo.company_id:
        #     values['res_company'] = owner_property_sudo.company_id
        if owner_property_sudo.name:
            history = request.session.get('booking_history', [])
        values.update(get_records_pager(history, owner_property_sudo))
        return request.render('dev_property_management.portal_owner_property_detail_form', values)
   
