import datetime,calendar
from odoo import http
from odoo.http import request
from odoo import models, fields, api, _
from operator import itemgetter
import itertools
import operator
from datetime import date, timedelta
from collections import defaultdict

class ProjectFilter(http.Controller):
    """The ProjectFilter class provides the filter option to the js.
    When applying the filter returns the corresponding data."""

    @http.route('/booking/property_filter', auth='public', type='json')
    def booking_property_filter(self,**kw):
        user_name = request.env.user.name
        user_img = request.env.user.image_1920

        return{
            'user_name':user_name,
            'user_img':user_img,
        }

    @http.route('/booking_property/all_filter', auth='public', type='json')
    def all_filter(self):
        
        booking_owner_list = []
        main_property_list = []
        sub_property_list = []
        
        owner_ids = request.env['res.partner'].search([('is_owner','!=',False)])
        main_property_ids = request.env['property.property'].search([('parent_id','=',False)])
        sub_property_ids = request.env['property.property'].search([('parent_id','!=',False)])
        singale_property_ids = request.env['property.property'].search([('parent_id','=',False), ('single_unit','=',True)])
               
        for owner_id in owner_ids:
            dic = {'name': owner_id.name,
                   'id': owner_id.id}
            booking_owner_list.append(dic)
        for main_property_id in main_property_ids:
            dic = {'name': main_property_id.name,
                   'id': main_property_id.id}
            main_property_list.append(dic)
        for sub_property_id in sub_property_ids:
            dic = {'name': sub_property_id.name,
                   'id': sub_property_id.id}
            sub_property_list.append(dic)
        
        return [booking_owner_list,main_property_list,sub_property_list]


    @http.route('/bookproperty_dashboard_filter_apply', auth='public', type='json')
    def bookpropertyFilterApply(self, kw):
        request = kw['request']
        # driver_domain = []
        owner_domain = []
        property_domain = []
        book_unbook_domain = []
        main_property_domain = []
        single_property_domain = [('single_unit','=',True)]
        sub_property_domain = []

        if request:
            if request['ownerr']:
                owner_id = request['ownerr']
                if not owner_id == "all":
                    owner_id = int(owner_id)
                    owner_domain = [('owner_partner_id.id', 'in', [owner_id])]
            if request['propertyy']:
                property_id = request['propertyy']
                if not property_id == "all":
                    property_id = property_id
                    property_domain = [('property_purpose', 'in', [property_id])]
            if request['book_unbook']:
                book_unbook_id = request['book_unbook']
                if not book_unbook_id == "all":
                    book_unbook_id = book_unbook_id
                    if book_unbook_id == "booking":
                        book_unbook_domain = [('state', '=', 'sold')]  # Replace 'status' and 'booked' with your actual field and value
                    elif book_unbook_id == "unbooking":
                        book_unbook_domain = [('state', '!=', 'sold')]  # Replace 'status' and 'unbooked' with your actual field and value
            if request['main_property']:
                main_property_id = request['main_property']
                if not main_property_id == "all":
                    main_property_id = int(main_property_id)
                    main_property_domain = [('parent_id', '=', main_property_id)]
            if request['sub_property']:
                sub_property_id = request['sub_property']
                if not sub_property_id == "all":
                    sub_property_id = int(sub_property_id)
                    sub_property_domain = [('id', '=', sub_property_id)] 

        return {'owner_domain':owner_domain,'main_property_domain':main_property_domain,'sub_property_domain':sub_property_domain,
                 'book_unbook_domain':book_unbook_domain,'property_domain':property_domain,}


    @http.route('/get/booking', auth='public', type='json')
    def getBookingData(self, **kw):
        
        all_color_list = ['#00daa3', '#f06c67', '#0c9fa1', '#cf9ab5', '#bce459', '#3f8eae', '#ed843f', '#00c4aa',
                          '#966ca2', '#e2d65e', '#d56e80', '#c99a5c', '#61e180', '#bf784b', '#fec863', '#7269ad'] 
        
        owner_domain = []
        book_unbook_domain = []
        main_property_domain = []
        sub_property_domain = []
        property_domain = []

        domains = self.bookpropertyFilterApply(kw)
        if domains:
            if domains['owner_domain']:
                owner_domain = domains['owner_domain']
            if domains['book_unbook_domain']:
                book_unbook_domain = domains['book_unbook_domain']
            if domains['main_property_domain']:
                main_property_domain = domains['main_property_domain']
            if domains['sub_property_domain']:
                sub_property_domain = domains['sub_property_domain']
            if domains['property_domain']:
                property_domain = domains['property_domain']
            
        
        combined_domain = owner_domain + book_unbook_domain + property_domain + sub_property_domain

        booking_property = request.env['property.property'].search_read(owner_domain + book_unbook_domain + property_domain + main_property_domain +sub_property_domain,
                                                                  fields=['property_type', 'parent_id', 'owner_partner_id','name', 'id', 'state'])

        
        p_id = kw.get('request').get('main_property')

        # Check if p_id is a valid integer or is 'all'
        if p_id and p_id != 'all' and p_id.isdigit(): #check isdigit vaue is int or string
            p_id = int(p_id)                          #convert in to integer
        else:
            p_id = None  # Set p_id to None or handle as needed

        # Only search if p_id is not None (i.e., not 'all')
        if p_id:
            singale_property_ids = request.env['property.property'].search_read(
                combined_domain + [('parent_id', '=', False), ('single_unit', '=', True), ('id', '=', p_id)],
                fields=['property_type', 'parent_id', 'owner_partner_id','name', 'id', 'state']
            )
            f_property = booking_property + singale_property_ids
        else:
            f_property = booking_property  # Proceed with only the booking_property if p_id is 'all'

        # Group properties by their 'parent_id' (Main Property)
        
        property_groups = {}
        property_booking_data = {}

        # This will store the count of sub-properties for each main property
        main_property_counts = {}

        # Loop through the list of properties (both main and sub-properties)
        for property in f_property:
            parent_property = property.get('parent_id')  # Access the 'parent_id' field

            if parent_property:
                parent_id = parent_property[0]  # The first element is the parent_id (ID)
                parent_name = parent_property[1] if len(parent_property) > 1 else None  # The second element might be the parent name

                if parent_name:  # Only group by parent name if it's available
                    # Grouping sub-properties by parent name
                    if parent_name not in property_groups:
                        property_groups[parent_name] = []
                    property_groups[parent_name].append(property)

                    # Count the number of sub-properties for each main property
                    if parent_name not in main_property_counts:
                        main_property_counts[parent_name] = 0
                    main_property_counts[parent_name] += 1

                    # Creating booking data for sub-properties under the parent
                    booking_status = "NB"  # Default is NO (Not Booked)
                    if property['state'] == 'sold': 
                        booking_status = "BO"
                    if property['state'] == 'on_rent': 
                    	booking_status = "ONR"
                   
                    if parent_name not in property_booking_data:
                        property_booking_data[parent_name] = []

                    property_booking_data[parent_name].append({
                        'sub_property_name': property['name'],  # Sub-property name
                        'owner': property['owner_partner_id'],
                        'booking_status': booking_status,       # Booking status (BO or NB)
                        'id': property['id'],                   # Property ID
                        'parent_id': property.get('parent_id')  # Parent ID for sub-property
                    })
            else:
                # If no parent_id exists, treat this as a main property with no sub-properties
                parent_name = property['name']

                # Grouping main properties by their name
                if parent_name not in property_groups:
                    property_groups[parent_name] = []
                property_groups[parent_name].append(property)

                # Creating booking data for main properties
                booking_status = "NB"  # Default is NO (Not Booked)
                if property['state'] == 'sold': 
                    booking_status = "BO"
                if property['state'] == 'on_rent': 
                	booking_status = "ONR"
                
                if parent_name not in property_booking_data:
                    property_booking_data[parent_name] = []

                property_booking_data[parent_name].append({
                    'sub_property_name': property['name'],  # Main property name
                    'owner': property['owner_partner_id'],
                    'booking_status': booking_status,       # Booking status (BO or NB)
                    'id': property['id'],                   # Property ID
                    'parent_id': None                       # Main property has no parent_id
                })

        # Now sort the main properties by the number of sub-properties (in descending order)
        sorted_main_properties = sorted(property_groups.items(), key=lambda x: main_property_counts.get(x[0], 0), reverse=True)

        # Create a new sorted dictionary for property_groups and property_booking_data
        sorted_property_groups = {}
        sorted_property_booking_data = {}

        # Populate the sorted dictionaries
        for parent_name, properties in sorted_main_properties:
            sorted_property_groups[parent_name] = properties
            sorted_property_booking_data[parent_name] = property_booking_data[parent_name]

        # Return the sorted results
        return {
            'property_groups': sorted_property_groups,  # Main properties sorted by number of sub-properties
            'property_booking_data': sorted_property_booking_data  # Corresponding booking data sorted
        }




        






        


        


        
        
        
        
        
    
    
    
    
    

    
   
