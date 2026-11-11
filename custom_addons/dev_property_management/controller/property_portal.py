from odoo.addons.portal.controllers.portal import CustomerPortal

from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo import fields, http, _
# from odoo.addons.portal.controllers.mail import _message_post_helper
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager, get_records_pager
from odoo.osv import expression
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import werkzeug



class PropertyWeb(CustomerPortal):

    @http.route(['/my/property_details'], type='http', auth="public", website=True)
    def portal_my_property(self, **kw):
        
        city_ids = request.env['property.city'].sudo().search([])
        property_ids=request.env['property.property'].sudo().search([('parent_id','=',False)])
        print('==============proprty_ids===========',property_ids)
        values = {
            'city_ids': city_ids,
            'properties': [],
            'property_ids':property_ids,
            
        }
        return request.render("dev_property_management.portal_my_property_details", values)


	
    @http.route(['/my/property_search'], type='http', auth="public", website=True, methods=['POST'], csrf=False)
    def property_search(self, **post):
        
        property_type = post.get('property_type')   # buy or rent
        select_city = post.get('select_city')
        search_query = post.get('search_query')
        category_type = post.get('type')            # residential/commercial/industrial/land

        domain = []

        # Apply filters
        if property_type:
            request.session['property_purpose'] = property_type
            # domain.append(('property_purpose', '=', property_type))
            domain += [
        '|',
        ('property_purpose', '=', property_type),
        ('property_purpose', '=', 'parent')
    ]
        if select_city:
            try:
                domain.append(('city_id', '=', int(select_city)))
            except ValueError:
                pass
        if search_query:
            try:
                domain.append(('id', '=', int(search_query)))
            except ValueError:
                pass

        if category_type and category_type != 'Any Type':
            domain.append(('property_type', '=', category_type))

        # Fetch properties
        properties = request.env['property.property'].sudo().search(domain)

        # City list for dropdown
        property_ids=request.env['property.property'].sudo().search([('parent_id','=',False)])
        city_ids = request.env['property.city'].sudo().search([])

        # Prepare context for template
        values = {
            'properties': properties,
            'property_ids':property_ids,
            'city_ids': city_ids,
            'selected_values': {
                'property_type': property_type,
                'city_id': select_city,
                'search_query': search_query,
                'category_type': category_type,
            },
            
        }

        return request.render("dev_property_management.search_property_view", values)
        

    @http.route('/get/projects/by_city', type='json', auth='public', website=True)
    def get_projects_by_city(self, city_id):
        if not city_id:
            return []
        projects = request.env['property.property'].sudo().search([('city_id', '=', int(city_id))])
        return [{'id': p.id, 'name': p.name} for p in projects]


    @http.route('/property/pdf/download/<int:property_id>', type='http', auth='public')
    def download_pdf(self, property_id):
        
        pdf_content = pdf = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'dev_property_management.menu_property_pdf_template',
            property_id,
        )[0]

        property = request.env['property.property'].sudo().browse(property_id)
        filename = f"Property_Report_{property.name}.pdf"

        return request.make_response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]
        )

     


#      VIEW PACKAGES

    @http.route(['/my/property_details/<int:property_id>/view'], type='http', auth="public", methods=['POST'], website=True)
    def my_property_details(self,property_id,  **post):

        property_sudo = request.env['property.property'].sudo().browse(property_id)
        suggested_property_pool = request.env['property.property'].sudo()
        suggested_property_details = suggested_property_pool.search([('property_purpose','=',property_sudo.property_purpose),('parent_id','=',False),('id','!=',property_sudo.id),('city_id','=',property_sudo.city_id.id)],  limit=2)

        values = self._prepare_portal_layout_values()
        values.update({
            'property_id': property_sudo,
            'suggested_property_details': suggested_property_details.sudo(),
            'property_purpose': request.session.get('property_purpose'),

            
    	})
        print('=====values=====',values)
        return request.render('dev_property_management.website_all_property_details', values)
   	

#    	
    @http.route(['/my/property_registration/<int:property_id>/thank_you'], type='http', auth="public", methods=['POST'], website=True)
    def customer_registration(self, property_id, access_token=None, **post):
        cr, uid, context, pool = request.cr, request.uid, request.context, request.env
		
        package_rec = request.env['property.property'].sudo().browse(property_id)

        property_type = request.session.get('property_purpose')

#    	lead_name = "Enquiry of " + post['name'] + " for " + pkg_id.package_id.name

        print ("property_id==============",property_id)

        lead_id = pool['crm.lead'].sudo().create({
            'name':  post['name']+ ' Inquiry For ' + package_rec.name or ' ' ,
            'contact_name':post['name'],
            'email_from': post['email'],
            'phone': post['mobile'],
            'property_id': property_id,
            'property_purpose': property_type,
            # 'description': post['massage'] or ' ',
            'type': 'lead',
            
    	})
        print("lead_id========",lead_id)
        return request.render('dev_property_management.website_property_thank_you',{'dev_company':lead_id.company_id,'reference_number':lead_id.number})
    	 	
    	
    	
    	
    	
    	
