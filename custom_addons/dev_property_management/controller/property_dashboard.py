# -*- coding: utf-8 -*-
##############################################################################
import datetime
from odoo import http
from odoo.http import request
from odoo import models, fields, api, _
from operator import itemgetter
import itertools
import operator
from datetime import date, timedelta


class ProjectFilter(http.Controller):
    """The ProjectFilter class provides the filter option to the js.
    When applying the filter returns the corresponding data."""

    @http.route('/all_property_filter', auth='public', type='json')
    def all_property_filter(self):
        
        owner_list = []
        partner_list = []
        recidency_list = []
        owner_ids = request.env['res.partner'].search([('is_owner','=',True)])
        partner_ids = request.env['res.partner'].search([('is_tenant','=',True)])
        recidency_ids = request.env['residential.type'].search([])
               
        for owner_id in owner_ids:
            dic = {'name': owner_id.name,
                   'id': owner_id.id}
            owner_list.append(dic)
        for partner_id in partner_ids:
            dic = {'name': partner_id.name,
                   'id': partner_id.id}
            partner_list.append(dic)
        for recidency_id in recidency_ids:
            dic = {'name': recidency_id.name,
                   'id': recidency_id.id}
            recidency_list.append(dic)    
        return [owner_list,partner_list,recidency_list]

    @http.route('/get/property/tiles/data', auth='public', type='json')
    def get_property_data(self, **kwargs):
        
        today = date.today()
        owner_domain = [('is_owner','=',True)]
        customer_domain = [('is_tenant','=',True)]
        property_domain = []
        booking_domain = []
        tenancy_domain = []
        payment_domain = []
        lead_domain = []
        cls_lead_domain = []
        opp_domain = []
        owner_payment_domain = []
        
        if not kwargs.get('duration'):
            booking_domain = [('confirmation_date', '=', today)]
            tenancy_domain = [('confirmation_date', '=', today)]
            lead_domain = [('create_date', '>=', today),('create_date', '<=', today)]
            cls_lead_domain = [('create_date', '>=', today)]
            property_domain = [('create_date', '>=', today),('create_date', '<=', today)]
            payment_domain = [('invoice_date', '=', today)]
            opp_domain = [('date_deadline', '>=', today),('date_deadline', '<=', today)]
            
            owner_payment_domain = [('create_date', '>=', today),('create_date', '<=', today)]

        if kwargs:
            if kwargs['owner_id']:
                if kwargs['owner_id'] != 'all':
                    owner_id = int(kwargs['owner_id'])
                    owner_domain += [('id', '=', int(owner_id))]
                    property_domain += [('owner_partner_id','=',owner_id)]
                    tenancy_domain += [('owner_partner_id', '=', owner_id)]
                    booking_domain += [('owner_partner_id', '=', owner_id)]
                    payment_domain += [('partner_id','=',owner_id)]
                    lead_domain += [('partner_id','=',owner_id)]
                    opp_domain += [('partner_id','=',owner_id)]
                    owner_payment_domain += [('owner_partner_id','=',owner_id)]
            if kwargs['partner_id']:
                if kwargs['partner_id'] != 'all':
                    partner_id = int(kwargs['partner_id'])
                    tenancy_domain += [('partner_id', '=', int(partner_id))]
                    lead_domain += [('partner_id','=',partner_id)]
                    opp_domain += [('partner_id','=',partner_id)]
                    owner_payment_domain += [('partner_id','=',partner_id)]
            if kwargs['property_id']:
                if kwargs['property_id'] != 'all':
                    property_id = kwargs['property_id']
                    property_domain += [('property_purpose','=',property_id)]
                    owner_payment_domain += [('property_id.property_purpose','=',property_id)]
            if kwargs['recidency_id']:
                if kwargs['recidency_id'] != 'all':
                    recidency_id = int(kwargs['recidency_id'])
                    property_domain += [('residential_type_id','=',recidency_id)]
                    booking_domain += [('property_id.residential_type_id', '=', recidency_id)]
            if kwargs['duration']:
                duration = kwargs['duration']
                if duration != "all":
                    duration = int(duration)
                    filter_date = today  - timedelta(days=duration)
                    booking_domain += [('confirmation_date', '>=', filter_date), ('confirmation_date', '<=', today)]
                    tenancy_domain += [('confirmation_date', '>=', filter_date), ('confirmation_date', '<=', today)]
                    lead_domain += [('create_date', '>=', filter_date), ('create_date', '<=', today)]
                    owner_payment_domain += [('create_date', '>=', filter_date), ('create_date', '<=', today)]
                    
                    cls_lead_domain += [('create_date', '>=', filter_date), ('create_date', '<=', today)]
                    property_domain += [('create_date', '>=', filter_date), ('create_date', '<=', today)]
                    opp_domain += [('date_deadline', '>=', filter_date), ('date_deadline', '<=', today)]                   
                    payment_domain += [('invoice_date', '>=', filter_date), ('invoice_date', '<=', today)]

        total_lead_data = request.env['crm.lead'].search([('type','=','lead'),('property_id', '!=', False)] + lead_domain)
        total_oppertunity_data = request.env['crm.lead'].search([('type','=','opportunity')] + opp_domain)
        all_owner_data = request.env['res.partner'].search(owner_domain)
        all_tenancy_data = request.env['property.tenancy'].search(tenancy_domain)
        rented_property_data = request.env['property.property'].search([('property_purpose','=','rent')] + property_domain)
        total_property_data = request.env['property.property'].search(property_domain)
        sellable_property_data = request.env['property.property'].search([('property_purpose','=','sell')] + property_domain)
        all_booking_data = request.env['property.booking'].search(booking_domain)
        payment_domain += [('rent_schedule_id','!=',False)]
        due_payment_domain = []
        due_payment_domain += [('payment_state','!=','paid')]
        done_payment_domain = []
        done_payment_domain += [('payment_state','=','paid')]
        
        due_payment_data = request.env['account.move'].search(due_payment_domain)
        done_payment_data = request.env['account.move'].search(done_payment_domain)
        payment_data = due_payment_data + done_payment_data
        user_name = request.env.user.name
        user_img = request.env.user.image_1920
        
        owner_draft_pay_ids = request.env['track.owner.payment'].search([('payment_state','=','draft')] + owner_payment_domain)
        owner_paid_ids = request.env['track.owner.payment'].search([('payment_state','=','paid')] + owner_payment_domain)
        return{
            'total_lead_data': total_lead_data.ids,
            'total_oppertunity_data': total_oppertunity_data.ids,
            'all_owner_data': all_owner_data.ids,
            'all_tenancy_data': all_tenancy_data.ids,
            'rented_property_data': rented_property_data.ids,
            'total_property_data': total_property_data.ids,
            'sellable_property_data': sellable_property_data.ids,
            'all_booking_data': all_booking_data.ids,
            'due_payment_data': due_payment_data and due_payment_data.ids or [],
            'done_payment_data': done_payment_data and done_payment_data.ids or [],
            'payment_data': payment_data.ids or [],
            'user_img': user_img,
            'user_name': user_name,
            
            'owner_draft_pay': owner_draft_pay_ids and owner_draft_pay_ids.ids or [],
            'owner_paid': owner_paid_ids.ids,
        }

    @http.route('/property/chart/data', auth='public', type='json')
    def get_property_chart_data(self, **kw):
        
        all_color_list = ['#00daa3', '#f06c67', '#0c9fa1', '#cf9ab5', '#bce459', '#3f8eae', '#ed843f', '#00c4aa',
                          '#966ca2', '#e2d65e', '#d56e80', '#c99a5c', '#61e180', '#bf784b', '#fec863', '#7269ad']     
    
        data=kw['data']
        today = date.today()
        owner_domain = [('is_owner','=',True)]
        customer_domain = [('is_tenant','=',True)]
        property_domain = []
        booking_domain = []
        deal_domain = [("state","=","confirmed")]
        tenancy_domain = []
        payment_domain = []
        lead_domain = []
        opp_domain = []
        opp_domain_lst = []
        rent_domain_lst = []
        # if data.get('duration') == 0:
        if not data.get('duration'):
            booking_domain = [('confirmation_date', '=', today)]
            tenancy_domain = [('confirmation_date', '=', today)]
            lead_domain = [('create_date', '>=', today),('create_date', '<=', today)]
            property_domain = [('create_date', '>=', today),('create_date', '<=', today)]
            payment_domain = [('date', '=', today)]
            deal_domain = [('booking_date', '=', today)]
            opp_domain = [('date_deadline', '>=', today),('date_deadline', '<=', today)]
            opp_domain_lst = [('date_deadline', '>', today)]
            rent_domain_lst = [('date', '>=', today),('date', '<=', today)]

        if data:
            if data['owner_id']:
                if data['owner_id'] != 'all':
                    owner_id = int(data['owner_id'])
                    owner_domain += [('id', '=', int(owner_id))]
                    property_domain += [('owner_partner_id','=',owner_id)]
                    deal_domain += [('owner_partner_id','=',owner_id)]
                    lead_domain += [('partner_id','=',owner_id)]
                    payment_domain += [('partner_id','=',owner_id)]
                    opp_domain_lst += [('partner_id','=',owner_id)]
                    rent_domain_lst += [('property_id.owner_partner_id','=',owner_id)]
            if data['partner_id']:
                if data['partner_id'] != 'all':
                    partner_id = int(data['partner_id'])
                    tenancy_domain += [('id', '=', int(partner_id))]
                    lead_domain += [('partner_id','=',partner_id)]
                    property_domain += [('tenant_partner_id','=',partner_id)]
                    opp_domain_lst += [('partner_id','=',partner_id)]
                    rent_domain_lst += [('partner_id','=',partner_id)]
            if data['property_id']:
                if data['property_id'] != 'all':
                    property_id = data['property_id']  
                    property_domain += [('property_purpose', '=', property_id)]
                    deal_domain += [('property_id.property_purpose', '=', property_id)]
                    rent_domain_lst += [('property_id.property_purpose', '=', property_id)]
            if data['recidency_id']:
                if data['recidency_id'] != 'all':
                    recidency_id = int(data['recidency_id'])
                    property_domain += [('residential_type_id.id','=',recidency_id)]
                    booking_domain += [('property_type','=',recidency_id)]
                    deal_domain += [('property_id.residential_type_id','=',recidency_id)]
                    rent_domain_lst += [('property_id.residential_type_id','=',recidency_id)]
            # if data['duration'] != 0:
            if data['duration']:
                duration = data['duration']
                # if duration:
                if duration != "all":
                    duration = int(duration)
                    filter_date = today  - timedelta(days=duration)
                    booking_domain += [('confirmation_date', '>=', filter_date), ('confirmation_date', '<=', today)]
                    deal_domain += [('booking_date', '>=', filter_date), ('booking_date', '<=', today)]
                    tenancy_domain += [('confirmation_date', '>=', filter_date), ('confirmation_date', '<=', today)]
                    lead_domain += [('create_date', '>=', filter_date), ('create_date', '<=', today)]
                    property_domain += [('create_date', '>=', filter_date), ('create_date', '<=', today)]
                    opp_domain += [('date_deadline', '>=', filter_date), ('date_deadline', '<=', today)] 
                    # opp_domain_lst += [('date_deadline', '>=', filter_date), ('date_deadline', '<=', today)] 
                    rent_domain_lst += [('date', '>=', filter_date), ('date', '<=', today)]                   
                    payment_domain += [('date', '>=', filter_date), ('date', '<=', today)]

        # =======================Source Chart 11111111======================
        top_repeated_source=[]
        top_repeated_source_chart=[]
        top_source_repeat_time=[]
        top_customer_order = request.env['crm.lead'].search(lead_domain)
        
        source_data = []
        for s_data in top_customer_order:

            source_data.append({
                                'source_id':s_data.source_id.name or 'Other',
                                'id':s_data.id or False,
                                'name':s_data.name or 'Other',
            })
        
        n_lines = sorted(source_data, key=itemgetter('source_id'))
        groups = itertools.groupby(n_lines, key=operator.itemgetter('source_id'))
        lines = [{'source_id': k, 'values': [x for x in v]} for k, v in groups]

        source_ids_lst=[]
        for x in lines:
            source_id_lst = []
            for id in x['values']:
                source_id_lst.append(id['id'])
            source_ids_lst.append(source_id_lst)
            source_ids_lst=sorted(source_ids_lst, key=lambda x: len(x), reverse=True)
        for line in lines:
            top_repeated_source.append(
                {'source': line.get('source_id')[0:], 'repeated_time': len(line.get('values'))})
        top_repeated_source = (sorted(top_repeated_source, key=lambda i: i['repeated_time'], reverse=True))
        for rep_source_data in top_repeated_source:
            top_repeated_source_chart.append(rep_source_data.get('source'))
            top_source_repeat_time.append(rep_source_data.get('repeated_time'))

        source_chart_data = {
            'labels': top_repeated_source_chart,
            'datasets': [{
                'label': "Top Repeated Source",
                'backgroundColor': all_color_list[:len(top_repeated_source_chart)],
                'data': top_source_repeat_time,
                'detail':source_ids_lst
            }]
        }

        # ============================Total Deal 2222222222=======================
        
        top_repeated_deal = []
        top_repeated_deal_chart = []
        top_de_deal_time = []
        deal_ids_lst = []

        top_deal_order = request.env['property.booking'].search_read(deal_domain, fields=['booking_date', 'name'])
        n_lines = sorted(top_deal_order, key=itemgetter('booking_date'))

        groups = itertools.groupby(n_lines, key=lambda x: x['booking_date'].strftime('%B'))
        lines = [{'month': k, 'values': list(v)} for k, v in groups]
        for line in lines:
            top_repeated_deal.append({'deal': line['month'], 'repeated_time': len(line['values'])})
            deal_ids_lst.append([deal['id'] for deal in line['values']])
        top_repeated_deal = sorted(top_repeated_deal, key=lambda x: x['repeated_time'], reverse=True)
        for rep_deal_data in top_repeated_deal:
            top_repeated_deal_chart.append(rep_deal_data['deal'])
            top_de_deal_time.append(rep_deal_data['repeated_time'])
        deal_chart_data = {
            'labels': top_repeated_deal_chart,
            'datasets': [{
                'label': "Deal",
                'backgroundColor': all_color_list[:len(top_repeated_deal_chart)],
                'data': top_de_deal_time,
                'detail': deal_ids_lst
            }]
        }
        
        # =============================property type 333333333333==================
        top_repeated_type=[]
        top_repeated_type_chart=[]
        top_type_repeat_time=[]
        
        top_type_order = request.env['property.property'].search_read(property_domain, fields=['property_type', 'name'])
        n_lines = sorted(top_type_order, key=itemgetter('property_type'))
        groups = itertools.groupby(n_lines, key=operator.itemgetter('property_type'))
        lines = [{'property_type': k, 'values': [x for x in v]} for k, v in groups]

        type_ids_lst=[]
        for x in lines:
            type_id_lst = []
            for id in x['values']:
                type_id_lst.append(id['id'])
            type_ids_lst.append(type_id_lst)
            type_ids_lst=sorted(type_ids_lst, key=lambda x: len(x), reverse=True)

        property_type_selection = dict(request.env['property.property']._fields['property_type'].selection)
        for line in lines:
            source_label = property_type_selection.get(line.get('property_type'), line.get('property_type'))
            top_repeated_type.append(
                {'source': source_label, 'repeated_time': len(line.get('values'))})
        top_repeated_type = (sorted(top_repeated_type, key=lambda i: i['repeated_time'], reverse=True))
        for rep_type_data in top_repeated_type:
            top_repeated_type_chart.append(rep_type_data.get('source'))
            top_type_repeat_time.append(rep_type_data.get('repeated_time'))

        type_chart_data = {
            'labels': top_repeated_type_chart,
            'datasets': [{
                'label': "Property Type",
                'backgroundColor': all_color_list[:len(top_repeated_type_chart)],
                'data': top_type_repeat_time,
                'detail':type_ids_lst
            }]
        }

        # ============================Payment Type 44444444=============
        top_repeated_payment=[]
        top_repeated_payment_chart=[]
        top_payment_repeat_time=[]
        
        top_payment = request.env['account.payment'].search_read(payment_domain, fields=['state', 'partner_id'])
        n_lines = sorted(top_payment, key=itemgetter('state'))
        groups = itertools.groupby(n_lines, key=operator.itemgetter('state'))
        lines = [{'state': k, 'values': [x for x in v]} for k, v in groups]

        payment_ids_lst=[]
        for x in lines:
            payment_id_lst = []
            for id in x['values']:
                payment_id_lst.append(id['id'])
            payment_ids_lst.append(payment_id_lst)
            payment_ids_lst=sorted(payment_ids_lst, key=lambda x: len(x), reverse=True)

        payment_state_selection = dict(request.env['account.payment']._fields['state'].selection)
        for line in lines:
            state_label = payment_state_selection.get(line.get('state'), line.get('state'))
            top_repeated_payment.append(
                {'source': state_label, 'repeated_time': len(line.get('values'))})
        top_repeated_payment = (sorted(top_repeated_payment, key=lambda i: i['repeated_time'], reverse=True))
        for rep_pay_data in top_repeated_payment:
            top_repeated_payment_chart.append(rep_pay_data.get('source'))
            top_payment_repeat_time.append(rep_pay_data.get('repeated_time'))

        all_payment_chart_data = {
            'labels': top_repeated_payment_chart,
            'datasets': [{
                'label': "Payment Type",
                'backgroundColor': all_color_list[:len(top_repeated_payment_chart)],
                'data': top_payment_repeat_time,
                'detail':payment_ids_lst
            }]
        }
        # ========================List==============
        upcoming_lead_list = request.env['crm.lead'].search_read(opp_domain_lst,fields=['name','partner_id','phone','date_deadline'],limit=10)
        pending_rent_list = request.env['rent.schedule'].search_read([('state', '=', 'unpaid')] + rent_domain_lst,
                                                                    fields=['name','property_id','tenancy_id','rent_amount','date'],limit=10)

        return{
            'source_chart_data': source_chart_data,
            'deal_chart_data': deal_chart_data,
            'type_chart_data': type_chart_data,
            'all_payment_chart_data': all_payment_chart_data,
            'upcoming_lead_list': upcoming_lead_list,
            'pending_rent_list': pending_rent_list
        }
      
    @http.route('/source/chart/data', auth='public', type='json')
    def get_source_chart_data(self, **kw):
        
        all_color_list = ['#00daa3', '#f06c67', '#0c9fa1', '#cf9ab5', '#bce459', '#3f8eae', '#ed843f', '#00c4aa',
                          '#966ca2', '#e2d65e', '#d56e80', '#c99a5c', '#61e180', '#bf784b', '#fec863', '#7269ad']     
    
        data=kw['data']
        today = date.today()
        lead_domain = []
        owner_domain = []
        tenancy_domain = []
        
        if not data.get('duration'):
            lead_domain = [('create_date', '>=', today),('create_date', '<=', today)]
            
        if data:
            if data['owner_id']:
                if data['owner_id'] != 'all':
                    owner_id = int(data['owner_id'])
                    owner_domain += [('id', '=', int(owner_id))]
                    lead_domain += [('partner_id','=',owner_id)]
            if data['partner_id']:
                if data['partner_id'] != 'all':
                    partner_id = int(data['partner_id'])
                    tenancy_domain += [('id', '=', int(partner_id))]
                    lead_domain += [('partner_id','=',partner_id)]
            if data['duration']:
                duration = data['duration']
                if duration != "all":
                    duration = int(duration)
                    filter_date = today  - timedelta(days=duration)
                    lead_domain += [('create_date', '>=', filter_date), ('create_date', '<=', today)]
                            
        top_repeated_source=[]
        top_repeated_source_chart=[]
        top_source_repeat_time=[]
        
        top_customer_order = request.env['crm.lead'].search(lead_domain)
        
        source_data = []
        for s_data in top_customer_order:

            source_data.append({
                                'source_id':s_data.source_id.name or 'Other',
                                'id':s_data.id or False,
                                'name':s_data.name or 'Other',
            })
        
        n_lines = sorted(source_data, key=itemgetter('source_id'))
        groups = itertools.groupby(n_lines, key=operator.itemgetter('source_id'))
        lines = [{'source_id': k, 'values': [x for x in v]} for k, v in groups]

        source_ids_lst=[]
        for x in lines:
            source_id_lst = []
            for id in x['values']:
                source_id_lst.append(id['id'])
            source_ids_lst.append(source_id_lst)
            source_ids_lst=sorted(source_ids_lst, key=lambda x: len(x), reverse=True)

        for line in lines:
            top_repeated_source.append(
                {'source': line.get('source_id')[0:], 'repeated_time': len(line.get('values'))})
        top_repeated_source = (sorted(top_repeated_source, key=lambda i: i['repeated_time'], reverse=True))
        for rep_source_data in top_repeated_source:
            top_repeated_source_chart.append(rep_source_data.get('source'))
            top_source_repeat_time.append(rep_source_data.get('repeated_time'))

        source_chart_data = {
            'labels': top_repeated_source_chart,
            'datasets': [{
                'label': "Top Repeated Source",
                'backgroundColor': all_color_list[:len(top_repeated_source_chart)],
                'data': top_source_repeat_time,
                'detail':source_ids_lst
            }]
        }
        return{
            'source_chart_data': source_chart_data
        }

    # ===========================chart 22222=================
    @http.route('/deal/chart/data', auth='public', type='json')
    def get_deal_chart_data(self, **kw):
        
        all_color_list = ['#00daa3', '#f06c67', '#0c9fa1', '#cf9ab5', '#bce459', '#3f8eae', '#ed843f', '#00c4aa',
                          '#966ca2', '#e2d65e', '#d56e80', '#c99a5c', '#61e180', '#bf784b', '#fec863', '#7269ad']     
    
        data=kw['data']
        today = date.today()
        deal_domain = [("state","=","confirmed")]
        owner_domain = []
        tenancy_domain = []
        # if data.get('duration') == 0:
        if not data.get('duration'):
            deal_domain = [('booking_date', '=', today)]
            
        if data:
            if data['owner_id']:
                if data['owner_id'] != 'all':
                    owner_id = int(data['owner_id'])
                    owner_domain += [('id', '=', int(owner_id))]
                    deal_domain += [('owner_partner_id','=',owner_id)]
            if data['property_id']:
                if data['property_id'] != 'all':
                    property_id = (data['property_id'])
                    deal_domain += [('property_id.property_purpose','=',property_id)] 
            if data['recidency_id']:
                if data['recidency_id'] != 'all':
                    recidency_id = int(data['recidency_id'])
                    deal_domain += [('property_id.residential_type_id','=',recidency_id)]
            # if data['duration'] != 0:
            if data['duration']:
                duration = data['duration']
                # if duration:
                if duration != "all":
                    duration = int(duration)
                    filter_date = today  - timedelta(days=duration)
                    deal_domain += [('booking_date', '>=', filter_date), ('booking_date', '<=', today)]

        top_repeated_deal = []
        top_repeated_deal_chart = []
        top_de_deal_time = []
        deal_ids_lst = []

        top_deal_order = request.env['property.booking'].search_read(deal_domain, fields=['booking_date', 'name'])
        n_lines = sorted(top_deal_order, key=itemgetter('booking_date'))
        groups = itertools.groupby(n_lines, key=lambda x: x['booking_date'].strftime('%B'))
        lines = [{'month': k, 'values': list(v)} for k, v in groups]
        for line in lines:
            top_repeated_deal.append({'deal': line['month'], 'repeated_time': len(line['values'])})
            deal_ids_lst.append([deal['id'] for deal in line['values']])
        top_repeated_deal = sorted(top_repeated_deal, key=lambda x: x['repeated_time'], reverse=True)
        for rep_deal_data in top_repeated_deal:
            top_repeated_deal_chart.append(rep_deal_data['deal'])
            top_de_deal_time.append(rep_deal_data['repeated_time'])
        deal_chart_data = {
            'labels': top_repeated_deal_chart,
            'datasets': [{
                'label': "Deal",
                'backgroundColor': all_color_list[:len(top_repeated_deal_chart)],
                'data': top_de_deal_time,
                'detail': deal_ids_lst
            }]
        }
        return{
            'deal_chart_data': deal_chart_data
        }

    # ==========================chart 3333333==================
    @http.route('/type/chart/data', auth='public', type='json')
    def get_type_chart_data(self, **kw):
        
        all_color_list = ['#00daa3', '#f06c67', '#0c9fa1', '#cf9ab5', '#bce459', '#3f8eae', '#ed843f', '#00c4aa',
                          '#966ca2', '#e2d65e', '#d56e80', '#c99a5c', '#61e180', '#bf784b', '#fec863', '#7269ad']     
    
        data=kw['data']
        today = date.today()
        property_domain = []
                
        if not data.get('duration'):
            property_domain = [('create_date', '>=', today),('create_date', '<=', today)]
        if data:
            if data['owner_id']:
                if data['owner_id'] != 'all':
                    owner_id = int(data['owner_id'])
                    property_domain += [('owner_partner_id','=',owner_id)]
            if data['partner_id']:
                if data['partner_id'] != 'all':
                    partner_id = int(data['partner_id'])
                    property_domain += [('tenant_partner_id','=',partner_id)]
            if data['property_id']:
                if data['property_id'] != 'all':
                    property_id = (data['property_id'])
                    property_domain += [('property_purpose','=',property_id)]        
            if data['recidency_id']:
                if data['recidency_id'] != 'all':
                    recidency_id = int(data['recidency_id'])
                    property_domain += [('residential_type_id.id','=',recidency_id)]
            if data['duration']:
                duration = data['duration']
                if duration != "all":
                    duration = int(duration)
                    filter_date = today  - timedelta(days=duration)
                    property_domain += [('create_date', '>=', filter_date), ('create_date', '<=', today)]
                            
        top_repeated_type=[]
        top_repeated_type_chart=[]
        top_type_repeat_time=[]
        
        top_type_order = request.env['property.property'].search_read(property_domain, fields=['property_type', 'name'])
        n_lines = sorted(top_type_order, key=itemgetter('property_type'))
        groups = itertools.groupby(n_lines, key=operator.itemgetter('property_type'))
        lines = [{'property_type': k, 'values': [x for x in v]} for k, v in groups]

        type_ids_lst=[]
        for x in lines:
            type_id_lst = []
            for id in x['values']:
                type_id_lst.append(id['id'])
            type_ids_lst.append(type_id_lst)
            type_ids_lst=sorted(type_ids_lst, key=lambda x: len(x), reverse=True)

        property_type_selection = dict(request.env['property.property']._fields['property_type'].selection)
        for line in lines:
            source_label = property_type_selection.get(line.get('property_type'), line.get('property_type'))
            top_repeated_type.append(
                {'source': source_label, 'repeated_time': len(line.get('values'))})
        top_repeated_type = (sorted(top_repeated_type, key=lambda i: i['repeated_time'], reverse=True))
        for rep_type_data in top_repeated_type:
            top_repeated_type_chart.append(rep_type_data.get('source'))
            top_type_repeat_time.append(rep_type_data.get('repeated_time'))

        type_chart_data = {
            'labels': top_repeated_type_chart,
            'datasets': [{
                'label': "Property Type",
                'backgroundColor': all_color_list[:len(top_repeated_type_chart)],
                'data': top_type_repeat_time,
                'detail':type_ids_lst
            }]
        }
        return{
            'type_chart_data': type_chart_data
        }

    # ==========================4444444444444444444=========================
    @http.route('/payment/chart/data', auth='public', type='json')
    def get_payment_chart_data(self, **kw):
        
        all_color_list = ['#00daa3', '#f06c67', '#0c9fa1', '#cf9ab5', '#bce459', '#3f8eae', '#ed843f', '#00c4aa',
                          '#966ca2', '#e2d65e', '#d56e80', '#c99a5c', '#61e180', '#bf784b', '#fec863', '#7269ad']     
    
        data=kw['data']
        today = date.today()
        payment_domain = []
                
        if not data.get('duration'):
            payment_domain = [('date', '=', today)]
        if data:
            if data['owner_id']:
                if data['owner_id'] != 'all':
                    owner_id = int(data['owner_id'])
                    payment_domain += [('partner_id','=',owner_id)]
            if data['duration']:
                duration = data['duration']
                if duration != "all":
                    duration = int(duration)
                    filter_date = today  - timedelta(days=duration)
                    payment_domain += [('date', '>=', filter_date), ('date', '<=', today)]

        top_repeated_payment=[]
        top_repeated_payment_chart=[]
        top_payment_repeat_time=[]
        
        top_payment = request.env['account.payment'].search_read(payment_domain, fields=['state', 'partner_id'])
        n_lines = sorted(top_payment, key=itemgetter('state'))
        groups = itertools.groupby(n_lines, key=operator.itemgetter('state'))
        lines = [{'state': k, 'values': [x for x in v]} for k, v in groups]

        payment_ids_lst=[]
        for x in lines:
            payment_id_lst = []
            for id in x['values']:
                payment_id_lst.append(id['id'])
            payment_ids_lst.append(payment_id_lst)
            payment_ids_lst=sorted(payment_ids_lst, key=lambda x: len(x), reverse=True)

        payment_state_selection = dict(request.env['account.payment']._fields['state'].selection)
        for line in lines:
            state_label = payment_state_selection.get(line.get('state'), line.get('state'))
            top_repeated_payment.append(
                {'source': state_label, 'repeated_time': len(line.get('values'))})
        top_repeated_payment = (sorted(top_repeated_payment, key=lambda i: i['repeated_time'], reverse=True))
        for rep_pay_data in top_repeated_payment:
            top_repeated_payment_chart.append(rep_pay_data.get('source'))
            top_payment_repeat_time.append(rep_pay_data.get('repeated_time'))

        all_payment_chart_data = {
            'labels': top_repeated_payment_chart,
            'datasets': [{
                'label': "Payment Type",
                'backgroundColor': all_color_list[:len(top_repeated_payment_chart)],
                'data': top_payment_repeat_time,
                'detail':payment_ids_lst
            }]
        }
        return{
           'all_payment_chart_data': all_payment_chart_data 
        }

    @http.route('/property/filter-apply', auth='public', type='json')
    def property_filter_apply(self, **kw):
        data = kw['data']
        owner_id = data['owner']
        partner_id = data['partner']
        property_id = data['property']
        recidency_id = data['recidency']
        duration = data['duration']
        
        result = self.get_property_data(owner_id=owner_id,partner_id=partner_id,property_id=property_id,recidency_id=recidency_id,duration=duration)
        return result
