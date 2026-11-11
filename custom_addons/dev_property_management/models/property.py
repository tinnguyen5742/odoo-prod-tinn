# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import mimetypes
from datetime import date


class Property(models.Model):
    _name = 'property.property'
    _description = 'Property'
    _rec_name = 'complete_name'
    _inherit = ['mail.thread','portal.mixin']
    
    def _compute_access_url(self):
        super(Property, self)._compute_access_url()
        for property in self:
            property.access_url = '/my/Owner_property_details/%s' % (property.id)
            # property.access_url = '/my/property_details/%s' % (property.id)
            
    def _get_report_base_filename(self):
        self.ensure_one()
        return '%s %s' % (_('Owner Property'), self.number)
   
    @api.model
    def create(self, vals_list):
        for vals in vals_list:
            vals['number'] = self.env['ir.sequence'].next_by_code('property.number') or '/'
        return super(Property, self).create(vals_list)

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for property in self:
            if property.parent_id:
                property.complete_name = '%s/%s' % (property.parent_id.complete_name, property.name)
            else:
                property.complete_name = property.name

    @api.constrains('brochure')
    def _check_brochure(self):
        if self.brochure and self.brochure_name:
            mimetype = mimetypes.guess_type(self.brochure_name)[0]
            if mimetype != 'application/pdf':
                raise ValidationError('Brochure must be a PDF Document !')

    @api.constrains('construct_year')
    def _check_construct_year(self):
        if self.construct_year and len(str(abs(self.construct_year))) != 4:
            raise ValidationError(_('Construction Year should contain 4 digits !'))

    @api.depends('construct_year')
    def _compute_property_age(self):
        for property in self:
            age = ''
            if property.construct_year:
                differance = date.today().year - property.construct_year
                age = str(differance) + ' years old'
            property.property_age = age

    def _compute_total_carpet_area(self):
        for property in self:
            area = 0
            if property.area_measurement_ids:
                for area_measurement in property.area_measurement_ids:
                    area += area_measurement.carpet_area
            property.total_carpet_area = area

    def view_child_properties(self):
        child_property_ids = self.env['property.property'].search([('parent_id', '=', self.id)])
        action = self.env.ref('dev_property_management.action_subproperty_dev_property_management').sudo().read()[0]
        if len(child_property_ids) > 1:
            action['domain'] = [('id', 'in', child_property_ids.ids)]
        elif len(child_property_ids) == 1:
            action['views'] = [(self.env.ref('dev_property_management.form_property_dev_property_management').id, 'form')]
            action['res_id'] = child_property_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}  # Ensure 'type' is defined
        return action

    def view_confirmed_booking(self):
        action = self.env.ref('dev_property_management.action_property_booking').sudo().read()[0]
        action['views'] = [(self.env.ref('dev_property_management.form_property_booking').id, 'form')]
        action.update({'res_id': self.booking_id.id})
        action['type'] = 'ir.actions.act_window'  # Ensure 'type' is defined
        return action

    def create_booking(self):
    # Prepare the action to open the booking form view
        return {
            'name': 'Create Booking',
            'type': 'ir.actions.act_window',
            'res_model': 'property.booking',  # The model associated with the booking
            'view_mode': 'form',
            'view_id': self.env.ref('dev_property_management.form_property_booking').id,  # Form view ID
            'target': 'new',  # Open in a modal dialog
            'context': {
                'default_property_id': self.id,  # Pass current property ID if needed
                # Add other default values if required
            },
        }
        

    def generate_tenancy(self):
            tenancy_id = self.env['property.tenancy'].create({'property_id':self.id,
                                                              'owner_partner_id':self.owner_partner_id.id or False,
                                                              'property_type':self.property_type,
                                                              'rent_amount':self.rent_amount,
                                                              'deposit_amount':self.deposit_amount,
                                                        })
#            self.tenancy_id = tenancy_id.id
#            self.tenancy_id.onchange_property_id()
            action = self.env["ir.actions.actions"]._for_xml_id("dev_property_management.action_property_tenancy")
            action['domain'] = [('id', '=', tenancy_id.id)]
            return action
#        
#        else:
            print ("self=====ggggggggg=======",self)
#            return {
#                'type': 'ir.actions.act_window',
#                'res_model': 'property.tenancy',
#                'view_mode': 'form',
#                'context': {
#                        'default_property_id': self.id,
##                        'default_partner_id': self.partner_id and self.partner_id.id,
#                        'default_owner_partner_id': self.owner_partner_id.id or False,
#                        'default_property_type': self.property_type,
#                    },         
#                'target': 'current',
#            }
        

    def _compute_child_property_count(self):
        for property in self:
            child_count = 0
            child_property_ids = property.env['property.property'].search([('parent_id', '=', property._origin.id)])
            if child_property_ids:
                child_count = len(child_property_ids)
            property.child_property_count = child_count
            
    def view_booking_request(self):
        request_ids = self.env['property.booking'].search([('parent_id', '=', self.id)])
        action = self.env.ref('dev_property_management.action_property_booking').sudo().read()[0]
        if len(request_ids) > 1:
            action['domain'] = [('id', 'in', request_ids.ids)]
        elif len(request_ids) == 1:
            action['views'] = [(self.env.ref('dev_property_management.form_property_booking').id, 'form')]
            action['res_id'] = request_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}  # Ensure 'type' is defined
        return action
    
    
    def _compute_booking_request(self):
        for property in self:
            booking=0
            booking_request=property.env['property.booking'].search([('parent_id','=',property._origin.id)])
            if booking_request:
                booking=len(booking_request)
            property.booking_request_count=booking

    @api.onchange('property_type')
    def onchange_property_type(self):
        if self.parent_id and self.property_type:
            if self.property_type != self.parent_id.property_type:
                type_of_property = dict(self.parent_id._fields['property_type'].selection).get(self.parent_id.property_type)
                raise ValidationError(_('''Property Type must be '%s' as per its parent property''') % (type_of_property))

    def set_to_available(self):
        for tenancy_id in self.tenancy_ids:
            if tenancy_id.state == 'running':
                raise ValidationError(_(''''%s' Tenancy is still running, cancel it to move further !''') % (tenancy_id.name))
        agreements_ids = self.env['property.agreement'].search([('property_id', '=', self.id)])
        if agreements_ids:
            for agreement_id in agreements_ids:
                if agreement_id.state == 'running':
                    raise ValidationError(_(''''%s' Agreement is still running, cancel it to move further !''') % (agreement_id.name))
        self.state = 'draft'
        self.booking_id = False
        if self.property_purpose == 'rent':
            self.tenant_partner_id = False


    def view_agreements(self):
        agreements_ids = self.env['property.agreement'].search([('property_id', '=', self.id)])
        action = self.env.ref('dev_property_management.action_property_agreement').sudo().read()[0]
        if len(agreements_ids) > 1:
            action['domain'] = [('id', 'in', agreements_ids.ids)]
        elif len(agreements_ids) == 1:
            action['views'] = [(self.env.ref('dev_property_management.form_property_agreement').id, 'form')]
            action['res_id'] = agreements_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}  # Ensure 'type' is defined
        return action

    def _compute_agreement_count(self):
        for property in self:
            agreements_ids = self.env['property.agreement'].search([('property_id', '=', property.id)])
            counter = len(agreements_ids.ids)
            property.agreement_count = counter

    def _compute_location(self):
        for property in self:
            property.location = (property.latitude, property.longitude)

    @api.onchange('property_purpose')
    def onchange_property_purpose(self):
        if self.property_purpose == 'parent':
            self.parent_id = False

    # def generate_sub_properties(self):
        
    #     for tower in range(1, self.total_towers+1):
    #         per_floor_properties = self.total_floor * self.property_per_floor
    #         property = 1
    #         for p in range(1, per_floor_properties+1):
    #             sub_property = self.copy({'name': self.name + ' - T'+ str(tower) + ' - P' + str(property),
    #                        'property_purpose': 'rent',
    #                         'parent_id': self.id,
                            
    #                         'nearby_connectivity_ids':[(6, 0, self.nearby_connectivity_ids.ids)],
    #                         'amenity_ids':[(6,0,self.amenity_ids.ids)],
    #                         'description':self.description,
    #                         'brochure':self.brochure,


    #                         })

    #             for image in self.property_image_ids:
    #                 image.copy({
    #                     'res_id': sub_property.id,  # Link to the new property
    #                     'res_model': 'property.property',  # Ensure correct model is set
    #                 })
                
                
    #             property += 1
    def generate_sub_properties(self):
        if self.child_property_count > 0:
            return True
        total_count = 0
        if self.generate_dynamicaly_tower and self.tower_line_ids:
            for line in self.tower_line_ids:
                if not line.floot_unit:
                    raise ValidationError('Tower Details Assign Floor Unit')
                i = 1
                res_id= int(self.id)+1
                while i <= line.floot_unit:
                    total_count += 0
                    property_values = {
                        'name': f"{self.name} - T{line.tower_id.name} - F{line.floor_no} - U{i}",
                        'property_purpose': 'rent',
                        'parent_id': self.id,
                        'flat_type_id':self.flat_type_id.id,                    
                        'property_image_ids': [
                            (0, 0, {
                                'name': image.name,
                                'datas': image.datas,
                                'mimetype': image.mimetype,
                                'res_model': 'property.property',
                                'res_id': res_id
                            }) for image in self.property_image_ids
                        ],
                        'floor_plan_image_ids':[
                            (0, 0, {
                                'name': image.name,
                                'datas': image.datas,
                                'mimetype': image.mimetype,
                                'res_model': 'property.property',
                                'res_id': res_id,  # Ensure proper model
                            }) for image in self.floor_plan_image_ids
                        ],
                        'area_measurement_ids':[(0,0,{
                            'name': area.name,
                            'length':area.length,
                            'width':area.width,
                            'height':area.height
                        }) for area in self.area_measurement_ids],
                        'proprty_document_ids':[(0,0,{
                            'name': document.name,
                            'document':document.document,
                            
                        }) for document in self.proprty_document_ids],

                        'description':self.description,
                        'brochure':self.brochure,
                        'nearby_connectivity_ids': [(6, 0, self.nearby_connectivity_ids.ids)],
                        'amenity_ids': [(6, 0, self.amenity_ids.ids)],
                        'street':self.street,
                        'street2':self.street2,
                        'city_id':self.city_id.id or '',
                        'state_id':self.state_id.id or '',
                        'zip':self.zip,
                        'country_id':self.country_id.id or '',
                                            
                    }

                    # Create the new property
                    self.env['property.property'].create(property_values)
                    res_id +=1
                
                
                    i += 1
            print ("total_count========",total_count)
            
        else:
            for tower in range(1, self.total_towers + 1):
                per_floor_properties = self.total_floor * self.property_per_floor
                property_number = 1
                res_id= int(self.id)+1
                for _ in range(per_floor_properties):
                    # Prepare values for the new property
                    property_values = {
                        'name': f"{self.name} - T{tower} - P{property_number}",
                        'property_purpose': 'rent',
                        'parent_id': self.id,
                        'flat_type_id':self.flat_type_id.id,                    
                        'property_image_ids': [
                            (0, 0, {
                                'name': image.name,
                                'datas': image.datas,
                                'mimetype': image.mimetype,
                                'res_model': 'property.property',
                                'res_id': res_id
                            }) for image in self.property_image_ids
                        ],
                        'floor_plan_image_ids':[
                            (0, 0, {
                                'name': image.name,
                                'datas': image.datas,
                                'mimetype': image.mimetype,
                                'res_model': 'property.property',
                                'res_id': res_id,  # Ensure proper model
                            }) for image in self.floor_plan_image_ids
                        ],
                        'area_measurement_ids':[(0,0,{
                            'name': area.name,
                            'length':area.length,
                            'width':area.width,
                            'height':area.height
                        }) for area in self.area_measurement_ids],
                        'proprty_document_ids':[(0,0,{
                            'name': document.name,
                            'document':document.document,
                            
                        }) for document in self.proprty_document_ids],

                        'description':self.description,
                        'brochure':self.brochure,
                        'nearby_connectivity_ids': [(6, 0, self.nearby_connectivity_ids.ids)],
                        'amenity_ids': [(6, 0, self.amenity_ids.ids)],
                        'street':self.street,
                        'street2':self.street2,
                        'city_id':self.city_id.id or '',
                        'state_id':self.state_id.id or '',
                        'zip':self.zip,
                        'country_id':self.country_id.id or '',
                                            
                    }

                    # Create the new property
                    self.env['property.property'].create(property_values)
                    property_number += 1
                    res_id +=1

    
#    41
    def generate_tower_line(self):
        append_tower = []
        self.tower_line_ids = False
        for tower in  self.add_towers:
            i = 1
            while i <= tower.no_of_floor:
                append_tower.append((0, 0, {'tower_id':tower.id ,'floor_no' :int(i)}))
                i += 1
        self.tower_line_ids = append_tower
        return True
    
    def view_tenancies(self):
        tenancy_ids = self.tenancy_ids
        action = self.env.ref('dev_property_management.action_property_tenancy').sudo().read()[0]
        if len(tenancy_ids) > 1:
            action['domain'] = [('id', 'in', tenancy_ids.ids)]
        elif len(tenancy_ids) == 1:
            action['views'] = [(self.env.ref('dev_property_management.form_property_tenancy').id, 'form')]
            action['res_id'] = tenancy_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}  # Ensure 'type' is defined
        return action

    def _compute_tenancy_count(self):
        for property in self:
            counter = len(property.tenancy_ids.ids)
            property.tenancy_count = counter

    def _compute_invoice_count(self):
        for property in self:
            counter = len(property.invoice_ids.ids)
            property.invoice_count = counter

    def view_maintenance_invoices(self):
        invoice_ids = self.invoice_ids
        action = self.env.ref('account.action_move_out_invoice_type').sudo().read()[0]
        action.update({'display_name': 'Maintenance Invoices'})
        if len(invoice_ids) > 1:
            action['domain'] = [('id', 'in', invoice_ids.ids)]
        elif len(invoice_ids) == 1:
            action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
            action['res_id'] = invoice_ids.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action
    
    
    @api.onchange('single_unit')
    def _onchange_single_unit(self):
        if self.single_unit:
            self.is_tower = False  # If single_unit is True, set is_tower to False
            self.generate_dynamicaly_tower = False

    @api.onchange('is_tower')
    def _onchange_is_tower(self):
        if self.is_tower:
            self.single_unit = False
    
    def update_property_type(self):
        records = self.search([('parent_id','=',self.id)])
        for rec in records:
            rec.property_type = self.property_type

    number = fields.Char(string='Number', tracking=1)
    name = fields.Char(string='Name', tracking=1, required=True)
    photo = fields.Binary(string='Photo')
    property_type = fields.Selection(string='Property Type',
                                     selection=[('residential', 'Residential'),
                                                ('commercial', 'Commercial'),
                                                ('industrial', 'Industrial'),
                                                ('land', 'Land')], default='residential',
                                     required=True, tracking=1)
    tag_ids = fields.Many2many('property.tags', string='Tags')
    construct_year = fields.Integer(string='Construct Year', tracking=1)
    parent_id = fields.Many2one('property.property', string='Parent Property', tracking=1)
    complete_name = fields.Char(string='Full Property Name', compute='_compute_complete_name', store=True)
    street = fields.Char(string='Street')
    street2 = fields.Char(string='Street2')
    # city = fields.Char(string='City')
    city_id =fields.Many2one('property.city', string='City')
    state_id = fields.Many2one('res.country.state', string="State")
    zip = fields.Char(string="Zip")
    country_id = fields.Many2one('res.country', string="Country")
    owner_partner_id = fields.Many2one('res.partner', string='Owner', tracking=1)
    tenant_partner_id = fields.Many2one('res.partner', string='Tenant', tracking=1)
    property_purpose = fields.Selection(string='Purpose',
                                        selection=[('parent', 'Parent Property'),
                                                   ('rent', 'For Rent'),
                                                   ('sell', 'For Sell')],
                                        default='rent', tracking=1, required=True)
    property_status = fields.Selection(string='Condition',
                                       selection=[('new', 'Newly Constructed'),
                                                  ('re_sale', 'Re-Sale'),
                                                  ('under_construction', 'Under Construction')],
                                       tracking=1)
    price_amount = fields.Float(string='Selling Price', tracking=1)
    rent_amount = fields.Float(string='Monthly Rent', tracking=1)
    description = fields.Text(string='Description')
    brochure = fields.Binary(string='Brochure')
    brochure_name = fields.Char(string='Brochure Name')
    property_image_ids = fields.One2many('ir.attachment', 'res_id', string='Property Images',domain=[('document_type','=','property_image')],context={
                                            'default_res_model': 'property.property',
                                            'default_res_id': lambda self: self.id,
                                            'default_document_type': 'property_image',
                                           
                                        })
    floor_plan_image_ids = fields.One2many('ir.attachment', 'res_id', string='Floor Plan Images',domain=[('document_type','=','floor_plan')], context={
                                            'default_res_model': 'property.property',
                                            'default_res_id': lambda self: self.id,
                                            'default_document_type': 'floor_plan',
                                        })
    property_age = fields.Char(string='Age of Property', compute='_compute_property_age')
    residential_type_id = fields.Many2one('residential.type', string='Type of Residential', tracking=1)
    is_tower = fields.Boolean(string='Tower', tracking=1)
    
    
    single_unit = fields.Boolean(string='Single', default=True)
    total_towers = fields.Integer(string='Total Tower')
    generate_dynamicaly_tower = fields.Boolean(string='Generate Dynamical Tower', tracking=1)
    add_towers = fields.Many2many('tower.tower',string='Add Tower')
    total_floor = fields.Integer(string='No. of Floor')
    on_floor = fields.Integer(string='On Floor')
    property_number = fields.Char(string='Property Number', copy=False)
    furnishing = fields.Selection(string='Furnishing',
                                  selection=[('non_furnished', 'Non Furnished'),
                                             ('semi_furnished', 'Semi Furnished'),
                                             ('fully_furnished', 'Fully Furnished'),
                                             ], default='non_furnished', tracking=1)
    facing_id = fields.Many2one('property.facing',string='Facing',  tracking=1)
    industrial_location = fields.Selection(string='Location', selection=[('inside_city', 'In City'),
                                                                         ('outside_city', 'Outside of City')],
                                           tracking=1, default='outside_city')
    state = fields.Selection(string='Status', selection=[('draft', 'Available'),
                                                         ('on_rent', 'On Rent'),
                                                         ('sold','Sold')],
                             default='draft', tracking=1, copy=False)
    two_wheeler_parking = fields.Boolean(string='2 Wheeler Parking')
    two_wheeler_parking_allot = fields.Integer(string='2 Wheeler Parking Allotment')
    four_wheeler_parking = fields.Boolean(string='4 Wheeler Parking')
    four_wheeler_parking_allot = fields.Integer(string='4 Wheeler Parking Allotment')
    total_square_foot = fields.Float(string='Total Size(sq.ft.)')
    total_carpet_area = fields.Float(string='Carpet Area(sq.ft.)', compute='_compute_total_carpet_area')
    area_measurement_ids = fields.One2many('property.area.measurement', 'property_id', string='Area Measurement')
    amenity_ids = fields.Many2many('property.amenities', string='Amenities')
    nearby_connectivity_ids = fields.Many2many('nearby.connectivity', string='Nearby Connectivity')
    commercial_type_id = fields.Many2one('commercial.type', string='Type of Commercial', tracking=1)
    industrial_type_id = fields.Many2one('industrial.type', string='Type of Industrial', tracking=1)
    child_property_count = fields.Integer(string='Child Properties', compute='_compute_child_property_count')
    booking_request_count=fields.Integer('booking', compute='_compute_booking_request')
    booking_request_ids = fields.One2many('property.booking', 'property_id', string='Bookings')
    booking_id = fields.Many2one('property.booking', string='Booking', copy=False, tracking=1)
    deposit_amount = fields.Float(string='Security Deposit', copy=False)
    agreement_count = fields.Integer(string='Agreement Counter', compute='_compute_agreement_count')
    property_per_floor = fields.Integer(string='Property Per. Floor')
    tenancy_ids = fields.One2many('property.tenancy', 'property_id', string='Tenancy')
    tenancy_count = fields.Integer(string='Tenancy Counter', compute='_compute_tenancy_count')
    invoice_ids = fields.One2many('account.move', 'property_id', string='Invoices')
    invoice_count = fields.Integer(string='Invoice Counter', compute='_compute_invoice_count')
    land_title_id=fields.Many2one('land.title' , string='Land Title')
    parking_space_id=fields.Many2one('parking.space' ,string='Parking Space')
    proprty_document_ids=fields.One2many('property.document','property_id',string='Document')
    flat_type_id = fields.Many2one('flat.type', string='Flat Type' )
    flat_name=fields.Char(related='residential_type_id.name' )
    tower_line_ids = fields.One2many('property.tower.line', 'property_id', string='Property Tower')
    
    
    floor=fields.Float(string='Floor') 
    bedroom=fields.Float(string='Bedrooms') 
    bathroom=fields.Float(string='Bathrooms') 
    alarms=fields.Selection(string='Alarm', selection=[('fire','Fire Alarm'),('smoke','Smoke Alarm'),('both','Both'),('no_alarm','No Alarm')], default='no_alarm')
    
    
#    def _total_garage(self):
#        for property in self:
#           total=property.two_wheeler_parking_allot +property.four_wheeler_parking_allot
#           property.total_garage=total
#           print("total=======",property.total_garage)
#    
#    
#    total_garage=fields.Integer('Total Garage', compute='_total_garage')


class property_tower_line(models.Model):
    _name = 'property.tower.line'
    _description = 'Property Tower'
    
    property_id = fields.Many2one('property.property', string='Property')
    tower_id = fields.Many2one('tower.tower', string='Tower')
    floor_no = fields.Char(string='Floor No')
    floot_unit = fields.Integer(string='Floor Unit')
    

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
