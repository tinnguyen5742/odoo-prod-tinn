# -*- coding: utf-8 -*-
"""
Property Management Website Controller
Modern, responsive property website for Odoo 18.0
"""

from odoo import http, fields
from odoo.http import request
import json
import logging
import base64

_logger = logging.getLogger(__name__)


class PropertyWebsiteController(http.Controller):
    """
    Main controller for property management website
    Handles all public property pages and search functionality
    """

    # ==========================================
    # Public Image Route
    # ==========================================
    
    @http.route('/properties/image/<int:property_id>', type='http', auth='public', website=True)
    def property_image(self, property_id, **kwargs):
        """Serve property images publicly"""
        Property = request.env['property.property'].sudo()
        property_obj = Property.browse(property_id)
        
        if property_obj.exists() and property_obj.photo:
            image_data = base64.b64decode(property_obj.photo)
            return request.make_response(
                image_data,
                headers=[
                    ('Content-Type', 'image/jpeg'),
                    ('Cache-Control', 'public, max-age=86400'),
                ]
            )
        else:
            # Return a placeholder or redirect to static no-image
            return request.redirect('/dev_property_management/static/src/img/no-image.svg')

    @http.route('/properties/gallery/<int:image_id>', type='http', auth='public', website=True)
    def property_gallery_image(self, image_id, **kwargs):
        """Serve property gallery images publicly"""
        PropertyImage = request.env['ir.attachment'].sudo()
        image_obj = PropertyImage.browse(image_id)
        
        if image_obj.exists() and image_obj.datas:
            image_data = base64.b64decode(image_obj.datas)
            return request.make_response(
                image_data,
                headers=[
                    ('Content-Type', 'image/jpeg'),
                    ('Cache-Control', 'public, max-age=86400'),
                ]
            )
        else:
            return request.redirect('/dev_property_management/static/src/img/no-image.svg')

    @http.route('/properties/floorplan/<int:floorplan_id>', type='http', auth='public', website=True)
    def property_floorplan_image(self, floorplan_id, **kwargs):
        """Serve property floor plan images publicly"""
        FloorPlan = request.env['property.floor.plan'].sudo()
        floorplan_obj = FloorPlan.browse(floorplan_id)
        
        if floorplan_obj.exists() and floorplan_obj.image:
            image_data = base64.b64decode(floorplan_obj.image)
            return request.make_response(
                image_data,
                headers=[
                    ('Content-Type', 'image/jpeg'),
                    ('Cache-Control', 'public, max-age=86400'),
                ]
            )
        else:
            return request.redirect('/dev_property_management/static/src/img/no-image.svg')

    @http.route('/properties/brochure/<int:property_id>', type='http', auth='public', website=True)
    def property_brochure(self, property_id, **kwargs):
        """Serve property brochure for download or view"""
        Property = request.env['property.property'].sudo()
        property_obj = Property.browse(property_id)
        
        if property_obj.exists() and property_obj.brochure:
            # Binary field in Odoo is base64 encoded string
            brochure_raw = property_obj.brochure
            
            # Handle both bytes and string (base64)
            if isinstance(brochure_raw, bytes):
                brochure_data = brochure_raw
            else:
                try:
                    brochure_data = base64.b64decode(brochure_raw)
                except Exception as e:
                    _logger.error(f"Error decoding brochure for property {property_id}: {str(e)}")
                    return request.redirect('/properties/all')
            
            # Use original filename if available, otherwise create one
            if property_obj.brochure_name:
                filename = property_obj.brochure_name
            else:
                # Sanitize property name for filename
                safe_name = ''.join(c if c.isalnum() or c in ' -_' else '_' for c in property_obj.name)
                filename = f"{safe_name}_brochure.pdf"
            
            # Detect content type from file data (magic bytes)
            content_type = 'application/octet-stream'
            disposition = 'attachment'
            
            # Check file signature (magic bytes) for common types
            if len(brochure_data) >= 4 and brochure_data[:4] == b'%PDF':
                content_type = 'application/pdf'
                disposition = 'inline'
            elif len(brochure_data) >= 8 and brochure_data[:8] == b'\x89PNG\r\n\x1a\n':
                content_type = 'image/png'
                disposition = 'inline'
            elif len(brochure_data) >= 2 and brochure_data[:2] == b'\xff\xd8':
                content_type = 'image/jpeg'
                disposition = 'inline'
            elif filename.lower().endswith('.pdf'):
                content_type = 'application/pdf'
                disposition = 'inline'
            elif filename.lower().endswith(('.jpg', '.jpeg')):
                content_type = 'image/jpeg'
                disposition = 'inline'
            elif filename.lower().endswith('.png'):
                content_type = 'image/png'
                disposition = 'inline'
            
            # Check if download is explicitly requested
            if kwargs.get('download'):
                disposition = 'attachment'
            
            return request.make_response(
                brochure_data,
                headers=[
                    ('Content-Type', content_type),
                    ('Content-Disposition', f'{disposition}; filename="{filename}"'),
                    ('Content-Length', str(len(brochure_data))),
                ]
            )
        else:
            return request.redirect('/properties/all')

    @http.route('/properties/document/<int:doc_id>', type='http', auth='public', website=True)
    def property_document(self, doc_id, **kwargs):
        """Serve property document for download or view"""
        Document = request.env['property.document'].sudo()
        doc_obj = Document.browse(doc_id)
        
        if doc_obj.exists() and doc_obj.document:
            try:
                doc_data = base64.b64decode(doc_obj.document)
            except Exception as e:
                _logger.error(f"Error decoding document {doc_id}: {str(e)}")
                return request.redirect('/properties/all')
            
            # Get filename
            filename = doc_obj.name or 'document'
            # Sanitize filename
            safe_name = ''.join(c if c.isalnum() or c in ' -_.' else '_' for c in filename)
            
            # Detect content type from magic bytes first
            content_type = 'application/octet-stream'
            disposition = 'attachment'
            
            if len(doc_data) >= 4 and doc_data[:4] == b'%PDF':
                content_type = 'application/pdf'
                disposition = 'inline'
            elif len(doc_data) >= 8 and doc_data[:8] == b'\x89PNG\r\n\x1a\n':
                content_type = 'image/png'
                disposition = 'inline'
            elif len(doc_data) >= 2 and doc_data[:2] == b'\xff\xd8':
                content_type = 'image/jpeg'
                disposition = 'inline'
            elif safe_name.lower().endswith('.pdf'):
                content_type = 'application/pdf'
                disposition = 'inline'
            elif safe_name.lower().endswith(('.jpg', '.jpeg')):
                content_type = 'image/jpeg'
                disposition = 'inline'
            elif safe_name.lower().endswith('.png'):
                content_type = 'image/png'
                disposition = 'inline'
            elif safe_name.lower().endswith('.doc'):
                content_type = 'application/msword'
            elif safe_name.lower().endswith('.docx'):
                content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            elif safe_name.lower().endswith('.xls'):
                content_type = 'application/vnd.ms-excel'
            elif safe_name.lower().endswith('.xlsx'):
                content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            else:
                # Default to PDF if no extension
                if '.' not in safe_name:
                    safe_name += '.pdf'
                    content_type = 'application/pdf'
                    disposition = 'inline'
            
            # Check if download is explicitly requested
            if kwargs.get('download'):
                disposition = 'attachment'
            
            return request.make_response(
                doc_data,
                headers=[
                    ('Content-Type', content_type),
                    ('Content-Disposition', f'{disposition}; filename="{safe_name}"'),
                    ('Content-Length', str(len(doc_data))),
                ]
            )
        else:
            return request.redirect('/properties/all')

    # ==========================================
    # Helper Methods
    # ==========================================
    
    def _get_property_domain(self, property_type=None, property_purpose=None, 
                              city_id=None, search=None, min_price=None, 
                              max_price=None, bedrooms=None, bathrooms=None,
                              furnishing=None, residential_type_id=None,
                              commercial_type_id=None, industrial_type_id=None,
                              industrial_location=None, land_title_id=None):
        """Build domain for property search"""
        # Properties with purpose 'rent' or 'sell' are actual listings (not parent properties)
        domain = [('property_purpose', 'in', ['rent', 'sell'])]
        
        if property_type:
            domain.append(('property_type', '=', property_type))
        
        if property_purpose and property_purpose != 'all':
            domain.append(('property_purpose', '=', property_purpose))
        
        if city_id:
            domain.append(('city_id', '=', int(city_id)))
        
        if search:
            domain.append('|')
            domain.append('|')
            domain.append('|')
            domain.append(('name', 'ilike', search))
            domain.append(('number', 'ilike', search))
            domain.append(('street', 'ilike', search))
            domain.append(('street2', 'ilike', search))
        
        if min_price:
            domain.append('|')
            domain.append(('price_amount', '>=', float(min_price)))
            domain.append(('rent_amount', '>=', float(min_price)))
        
        if max_price:
            domain.append('|')
            domain.append(('price_amount', '<=', float(max_price)))
            domain.append(('rent_amount', '<=', float(max_price)))
        
        if bedrooms:
            domain.append(('bedroom', '>=', int(bedrooms)))
        
        if bathrooms:
            domain.append(('bathroom', '>=', int(bathrooms)))
        
        # Furnishing filter (for residential and commercial)
        if furnishing:
            domain.append(('furnishing', '=', furnishing))
        
        # Residential sub-type filter
        if residential_type_id:
            domain.append(('residential_type_id', '=', int(residential_type_id)))
        
        # Commercial sub-type filter
        if commercial_type_id:
            domain.append(('commercial_type_id', '=', int(commercial_type_id)))
        
        # Industrial sub-type filter
        if industrial_type_id:
            domain.append(('industrial_type_id', '=', int(industrial_type_id)))
        
        # Industrial location filter
        if industrial_location:
            domain.append(('industrial_location', '=', industrial_location))
        
        # Land title filter
        if land_title_id:
            domain.append(('land_title_id', '=', int(land_title_id)))
        
        return domain

    def _get_sort_order(self, sort_by):
        """Get sort order for properties"""
        sort_options = {
            'newest': 'create_date desc',
            'oldest': 'create_date asc',
            'price_low': 'price_amount asc, rent_amount asc',
            'price_high': 'price_amount desc, rent_amount desc',
            # 'name': 'name asc',
        }
        return sort_options.get(sort_by, 'create_date desc')

    def _get_common_context(self):
        """Get common context data for all pages"""
        Property = request.env['property.property'].sudo()
        City = request.env['property.city'].sudo()
        ResidentialType = request.env['residential.type'].sudo()
        CommercialType = request.env['commercial.type'].sudo()
        IndustrialType = request.env['industrial.type'].sudo()
        LandTitle = request.env['land.title'].sudo()
        
        # Get cities that have properties (excluding parent properties)
        city_ids = Property.search([('property_purpose', 'in', ['rent', 'sell'])]).mapped('city_id')
        cities = City.search([('id', 'in', city_ids.ids)])
        
        # Get all type options for filters
        residential_types = ResidentialType.search([])
        commercial_types = CommercialType.search([])
        industrial_types = IndustrialType.search([])
        land_titles = LandTitle.search([])
        
        # Furnishing options
        furnishing_options = [
            ('non_furnished', 'Non Furnished'),
            ('semi_furnished', 'Semi Furnished'),
            ('fully_furnished', 'Fully Furnished'),
        ]
        
        # Industrial location options
        industrial_location_options = [
            ('inside_city', 'In City'),
            ('outside_city', 'Outside of City'),
        ]
        
        # Get property counts by type
        property_counts = {
            'all': Property.search_count([('property_purpose', 'in', ['rent', 'sell'])]),
            'sell': Property.search_count([('property_purpose', '=', 'sell')]),
            'rent': Property.search_count([('property_purpose', '=', 'rent')]),
            'residential': Property.search_count([('property_purpose', 'in', ['rent', 'sell']), ('property_type', '=', 'residential')]),
            'commercial': Property.search_count([('property_purpose', 'in', ['rent', 'sell']), ('property_type', '=', 'commercial')]),
            'industrial': Property.search_count([('property_purpose', 'in', ['rent', 'sell']), ('property_type', '=', 'industrial')]),
            'land': Property.search_count([('property_purpose', 'in', ['rent', 'sell']), ('property_type', '=', 'land')]),
        }
        
        return {
            'cities': cities,
            'property_counts': property_counts,
            'residential_types': residential_types,
            'commercial_types': commercial_types,
            'industrial_types': industrial_types,
            'land_titles': land_titles,
            'furnishing_options': furnishing_options,
            'industrial_location_options': industrial_location_options,
        }

    def _paginate_properties(self, domain, page=1, per_page=12, order='create_date desc'):
        """Paginate property results"""
        Property = request.env['property.property'].sudo()
        
        total = Property.search_count(domain)
        total_pages = (total + per_page - 1) // per_page
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        
        offset = (page - 1) * per_page
        properties = Property.search(domain, limit=per_page, offset=offset, order=order)
        
        return {
            'properties': properties,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
        }

    # ==========================================
    # Main Routes
    # ==========================================

    @http.route(['/properties', '/properties/page/<int:page>'], 
                type='http', auth='public', website=True)
    def properties_home(self, page=1, **kwargs):
        """Main property homepage with search and categories"""
        context = self._get_common_context()
        
        # Get featured properties
        Property = request.env['property.property'].sudo()
        featured_properties = Property.search(
            [('property_purpose', 'in', ['rent', 'sell'])], 
            limit=6, 
            order='create_date desc'
        )
        
        # Get properties for each category
        sell_properties = Property.search(
            [('property_purpose', '=', 'sell')], 
            limit=3
        )
        rent_properties = Property.search(
            [('property_purpose', '=', 'rent')], 
            limit=3
        )
        
        values = {
            **context,
            'featured_properties': featured_properties,
            'sell_properties': sell_properties,
            'rent_properties': rent_properties,
            'active_page': 'home',
        }
        
        return request.render('dev_property_management.website_property_home', values)

    @http.route(['/properties/all', '/properties/all/page/<int:page>'], 
                type='http', auth='public', website=True)
    def properties_all(self, page=1, **kwargs):
        """All properties listing page with filters"""
        return self._property_listing_page(
            page=page,
            page_title='All Properties',
            active_page='all',
            **kwargs
        )

    def _property_listing_page(self, property_type=None, property_purpose=None, 
                                page=1, page_title='Properties', active_page='all', **kwargs):
        """Generic property listing page handler"""
        context = self._get_common_context()
        
        # Get filter parameters
        city_id = kwargs.get('city_id')
        search = kwargs.get('search', '').strip()
        sort_by = kwargs.get('sort_by', 'newest')
        min_price = kwargs.get('min_price')
        max_price = kwargs.get('max_price')
        bedrooms = kwargs.get('bedrooms')
        bathrooms = kwargs.get('bathrooms')
        purpose_filter = kwargs.get('purpose')
        property_type_filter = kwargs.get('property_type_filter')
        
        # Type-specific filters
        furnishing = kwargs.get('furnishing')
        residential_type_id = kwargs.get('residential_type_id')
        commercial_type_id = kwargs.get('commercial_type_id')
        industrial_type_id = kwargs.get('industrial_type_id')
        industrial_location = kwargs.get('industrial_location')
        land_title_id = kwargs.get('land_title_id')
        
        # Override property_purpose if filter is provided
        if purpose_filter and purpose_filter != 'all':
            property_purpose = purpose_filter
        
        # Override property_type if filter is provided
        if property_type_filter and property_type_filter != 'all':
            property_type = property_type_filter
        
        # Build domain
        domain = self._get_property_domain(
            property_type=property_type,
            property_purpose=property_purpose,
            city_id=city_id,
            search=search,
            min_price=min_price,
            max_price=max_price,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            furnishing=furnishing,
            residential_type_id=residential_type_id,
            commercial_type_id=commercial_type_id,
            industrial_type_id=industrial_type_id,
            industrial_location=industrial_location,
            land_title_id=land_title_id,
        )
        
        # Get sort order
        order = self._get_sort_order(sort_by)
        
        # Paginate results
        pagination = self._paginate_properties(domain, page=int(page), order=order)
        
        values = {
            **context,
            **pagination,
            'page_title': page_title,
            'active_page': active_page,
            'current_city_id': int(city_id) if city_id else None,
            'current_search': search,
            'current_sort': sort_by,
            'current_min_price': min_price,
            'current_max_price': max_price,
            'current_bedrooms': bedrooms,
            'current_bathrooms': bathrooms,
            'current_purpose': purpose_filter or property_purpose,
            'current_property_type': property_type_filter or (property_type if not kwargs.get('property_type_filter') else None),
            'property_type': property_type if not property_type_filter else None,
            'property_purpose': property_purpose if not purpose_filter else None,
            # Type-specific current filter values
            'current_furnishing': furnishing,
            'current_residential_type_id': int(residential_type_id) if residential_type_id else None,
            'current_commercial_type_id': int(commercial_type_id) if commercial_type_id else None,
            'current_industrial_type_id': int(industrial_type_id) if industrial_type_id else None,
            'current_industrial_location': industrial_location,
            'current_land_title_id': int(land_title_id) if land_title_id else None,
        }
        
        return request.render('dev_property_management.website_property_listing', values)

    @http.route('/properties/detail/<int:property_id>', 
                type='http', auth='public', website=True)
    def property_detail(self, property_id, **kwargs):
        """Property detail page"""
        Property = request.env['property.property'].sudo()
        property_obj = Property.browse(property_id)
        
        if not property_obj.exists() or property_obj.property_purpose == 'parent':
            return request.redirect('/properties')
        
        context = self._get_common_context()
        
        # Get similar properties
        # similar_domain = [
        #     ('property_purpose', 'in', ['rent', 'sell']),
        #     ('id', '!=', property_id),
        #     ('property_type', '=', property_obj.property_type),
        # ]
        similar_domain = [
            ('property_purpose', '=', property_obj.property_purpose),
            ('id', '!=', property_id),
            ('property_type', '=', property_obj.property_type),
            ('city_id', '=', property_obj.city_id.id)
        ]
        similar_properties = Property.search(similar_domain, limit=3)
        
        values = {
            **context,
            'property': property_obj,
            'similar_properties': similar_properties,
            'active_page': 'detail',
        }
        
        return request.render('dev_property_management.website_property_detail', values)

    @http.route('/properties/inquiry', type='http', auth='public', 
                website=True, methods=['POST'], csrf=True)
    def property_inquiry(self, **kwargs):
        """Handle property inquiry form submission"""
        property_id = kwargs.get('property_id')
        name = kwargs.get('name', '').strip()
        email = kwargs.get('email', '').strip()
        phone = kwargs.get('phone', '').strip()
        message = kwargs.get('message', '').strip()
        
        # Validate required fields - name, email and phone are all required
        if not all([property_id, name, email, phone]):
            return json.dumps({
                'success': False, 
                'error': 'Please fill all required fields (Name, Email, Phone).'
            })
        
        try:
            Property = request.env['property.property'].sudo()
            property_obj = Property.browse(int(property_id))
            
            if not property_obj.exists():
                return json.dumps({
                    'success': False, 
                    'error': 'Property not found.'
                })
            
            # Create CRM lead
            Lead = request.env['crm.lead'].sudo()
            lead_vals = {
                'name': f"Inquiry for {property_obj.name}",
                'contact_name': name,
                'email_from': email,
                'phone': phone,
                'description': message,
                'type': 'lead',
            }
            
            # Add property reference if field exists
            if hasattr(Lead, 'property_id'):
                lead_vals['property_id'] = property_obj.id
                lead_vals['property_purpose'] = property_obj.property_purpose
            
            lead_id = Lead.create(lead_vals)
            
            # Store inquiry info in session for security (don't expose IDs in URL)
            request.session['inquiry_data'] = {
                'property_id': property_obj.id,
                'property_name': property_obj.name,
                'reference_number': lead_id.number,
                'customer_name': name,
            }
            
            return request.redirect('/properties/thank-you')
            
        except Exception as e:
            _logger.error(f"Error creating property inquiry: {str(e)}")
            return json.dumps({
                'success': False, 
                'error': 'An error occurred. Please try again.'
            })

    @http.route('/properties/thank-you', type='http', auth='public', website=True)
    def property_thank_you(self, **kwargs):
        """Thank you page after inquiry submission"""
        # Get inquiry data from session (secure - no URL manipulation possible)
        inquiry_data = request.session.get('inquiry_data', {})
        
        # Clear the session data after reading (one-time use)
        if 'inquiry_data' in request.session:
            del request.session['inquiry_data']
        
        property_obj = None
        dev_company = request.env.company
        
        # Get property if we have data
        if inquiry_data.get('property_id'):
            Property = request.env['property.property'].sudo()
            property_obj = Property.browse(inquiry_data['property_id'])
            if not property_obj.exists():
                property_obj = None
        
        context = self._get_common_context()
        
        values = {
            **context,
            'property': property_obj,
            'property_name': inquiry_data.get('property_name', ''),
            'active_page': 'thank_you',
            'dev_company': dev_company,
            'reference_number': inquiry_data.get('reference_number', ''),
            'customer_name': inquiry_data.get('customer_name', ''),
        }
        
        return request.render('dev_property_management.website_property_thank_you', values)

    @http.route('/properties/search', type='http', auth='public', website=True)
    def property_search(self, **kwargs):
        """Search page - redirects to appropriate listing"""
        search = kwargs.get('search', '').strip()
        city_id = kwargs.get('city_id')
        purpose = kwargs.get('purpose', 'all')
        property_type = kwargs.get('property_type')
        
        # Build query parameters
        params = []
        
        # Add purpose filter if specific purpose selected
        if purpose in ['sell', 'rent']:
            params.append(f'purpose={purpose}')
            
        # Add property type filter if selected
        if property_type:
            params.append(f'property_type_filter={property_type}')
            
        # Add search text if provided
        if search:
            params.append(f'search={search}')
        
        # Add city filter if selected
        if city_id:
            params.append(f'city_id={city_id}')
        
        # Construct final URL
        url = '/properties/all'
        if params:
            url += '?' + '&'.join(params)
        
        return request.redirect(url)

    # ==========================================
    # AJAX Endpoints
    # ==========================================

    @http.route('/properties/api/search', type='json', auth='public', website=True)
    def api_property_search(self, **kwargs):
        """AJAX endpoint for property search with filters"""
        property_type = kwargs.get('property_type')
        property_purpose = kwargs.get('property_purpose')
        city_id = kwargs.get('city_id')
        search = kwargs.get('search', '').strip()
        sort_by = kwargs.get('sort_by', 'newest')
        page = int(kwargs.get('page', 1))
        min_price = kwargs.get('min_price')
        max_price = kwargs.get('max_price')
        bedrooms = kwargs.get('bedrooms')
        bathrooms = kwargs.get('bathrooms')
        
        domain = self._get_property_domain(
            property_type=property_type,
            property_purpose=property_purpose,
            city_id=city_id,
            search=search,
            min_price=min_price,
            max_price=max_price,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
        )
        
        order = self._get_sort_order(sort_by)
        pagination = self._paginate_properties(domain, page=page, order=order)
        
        # Format properties for JSON response
        properties_data = []
        for prop in pagination['properties']:
            properties_data.append({
                'id': prop.id,
                'name': prop.name,
                'number': prop.number,
                'property_type': prop.property_type,
                'property_purpose': prop.property_purpose,
                'price_amount': prop.price_amount,
                'rent_amount': prop.rent_amount,
                'bedroom': prop.bedroom,
                'bathroom': prop.bathroom,
                'floor': prop.floor,
                'city': prop.city_id.name if prop.city_id else '',
                'state': prop.state_id.name if prop.state_id else '',
                'street': prop.street or '',
                'image_url': f'/web/image/property.property/{prop.id}/photo' if prop.photo else '/dev_property_management/static/src/img/no-image.svg',
            })
        
        return {
            'success': True,
            'properties': properties_data,
            'total': pagination['total'],
            'page': pagination['page'],
            'total_pages': pagination['total_pages'],
            'has_prev': pagination['has_prev'],
            'has_next': pagination['has_next'],
        }

    @http.route('/properties/api/cities', type='json', auth='public', website=True)
    def api_get_cities(self, **kwargs):
        """AJAX endpoint to get cities with property counts"""
        Property = request.env['property.property'].sudo()
        City = request.env['property.city'].sudo()
        
        city_ids = Property.search([('property_purpose', 'in', ['rent', 'sell'])]).mapped('city_id')
        cities = City.search([('id', 'in', city_ids.ids)])
        
        cities_data = []
        for city in cities:
            count = Property.search_count([
                ('property_purpose', 'in', ['rent', 'sell']),
                ('city_id', '=', city.id)
            ])
            cities_data.append({
                'id': city.id,
                'name': city.name,
                'property_count': count,
            })
        
        return {
            'success': True,
            'cities': cities_data,
        }

    @http.route('/properties/api/property/<int:property_id>', 
                type='json', auth='public', website=True)
    def api_property_detail(self, property_id, **kwargs):
        """AJAX endpoint to get property details"""
        Property = request.env['property.property'].sudo()
        property_obj = Property.browse(property_id)
        
        if not property_obj.exists() or property_obj.property_purpose == 'parent':
            return {'success': False, 'error': 'Property not found'}
        
        # Get property images
        images = []
        for img in property_obj.property_image_ids:
            images.append({
                'id': img.id,
                'url': f'/web/image/property.image/{img.id}/image',
            })
        
        # Get amenities
        amenities = []
        for amenity in property_obj.amenity_ids:
            amenities.append({
                'id': amenity.id,
                'name': amenity.name,
            })
        
        # Get nearby connectivity
        nearby = []
        for item in property_obj.nearby_connectivity_ids:
            nearby.append({
                'id': item.id,
                'name': item.name,
                'distance': item.distance if hasattr(item, 'distance') else '',
            })
        
        return {
            'success': True,
            'property': {
                'id': property_obj.id,
                'name': property_obj.name,
                'number': property_obj.number,
                'property_type': property_obj.property_type,
                'property_purpose': property_obj.property_purpose,
                'price_amount': property_obj.price_amount,
                'rent_amount': property_obj.rent_amount,
                'deposit_amount': property_obj.deposit_amount,
                'bedroom': property_obj.bedroom,
                'bathroom': property_obj.bathroom,
                'floor': property_obj.floor,
                'furnishing': property_obj.furnishing,
                'city': property_obj.city_id.name if property_obj.city_id else '',
                'state': property_obj.state_id.name if property_obj.state_id else '',
                'street': property_obj.street or '',
                'street2': property_obj.street2 or '',
                'zip': property_obj.zip or '',
                'description': property_obj.description if hasattr(property_obj, 'description') else '',
                'main_image': f'/web/image/property.property/{property_obj.id}/photo' if property_obj.photo else '',
                'images': images,
                'amenities': amenities,
                'nearby': nearby,
                'two_wheeler_parking': property_obj.two_wheeler_parking,
                'four_wheeler_parking': property_obj.four_wheeler_parking,
            }
        }
