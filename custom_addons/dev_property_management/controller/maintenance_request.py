# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, http, _
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
#from odoo.addons.payment.controllers.portal import PaymentProcessing
#from odoo.addons.portal.controllers.mail import _message_post_helper
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager, get_records_pager
from odoo.osv import expression
import werkzeug
from datetime import datetime, date
from odoo.tools import groupby as groupbyelem
from operator import itemgetter
from odoo.tools import float_compare


class CustomerPortal(CustomerPortal):

    def get_default_data_mai(self):
        values = {}
        team_id = request.env['maintenance.team'].sudo().search([])
        priority = ['Very Low','Very','Normal','High']
        values['mai_type']= ['corrective','preventive']
        values['team_id']= team_id or False
        values['priority'] = priority
        
        tenancy_id = request.env['property.tenancy'].sudo().search([('partner_id','=',request.env.user.partner_id.id),('state','=','confirm')],limit=1)
        values['tenancy_id'] = tenancy_id
        return values

    @http.route('/create/maintenance_request_new', auth='user', website=True, type='http', csrf_token=True)
    def create_maintenance_request(self, **kw):
        values = self.get_default_data_mai()
        
        return request.render('dev_property_management.website_maintenance_request_siu', values)
        
    @http.route(['/dev_maintenance_portal/maintenance_request_submitted_siu'], type='http', auth="user", methods=['POST'], website=True)
    def maintenance_request_submitted(self, **post):
        cr, uid, context, pool = http.request.cr, http.request.uid, http.request.context, request.env
#        maintenance_type = post['maintenance_type']
        priority = 0
        if post['priority_name'] == 'Very':
            priority = 1
        if post['priority_name'] == 'Normal':
            priority = 2
        if post['priority_name'] == 'High':
            priority = 3
        description = str(post['subject']) +': - '+str(post['issue_details'])
        tenancy_id = int(post['tenancy_id']) if post.get('tenancy_id') else False
        property_id = int(post['property_ids']) if post.get('property_ids') else False

        maintenance_id = pool['maintenance.request'].sudo().create({
            'name': post.get('subject'),
            'priority': str(priority),
            'description': description,
            'tenancy_id': tenancy_id,
            'property_id': property_id,
        })
 
        # maintenance_id = pool['maintenance.request'].sudo().create({
        #     'name':post['subject'],
        #     'priority':str(priority),
        #     'description':description,
        #     'tenancy_id':int(post.get('tenancy_id')),
        #     'property_id':int(post.get('property_ids')),
            
        # })
        maintenance_id._onchange_property()
        maintenance_id._onchange_tenancy_id()
        if maintenance_id:
            return request.render("dev_property_management.website_maintenance_thank_you", {'default_url': '/create/vistor_request',})





