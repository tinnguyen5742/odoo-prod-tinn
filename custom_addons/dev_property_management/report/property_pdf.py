# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle
#
##############################################################################

from odoo import api, models


class PropertyReport(models.AbstractModel):
    _name = 'report.dev_property_management.property_pdf_template'

    def get_property_images(self, property_id):
        image_list = []
        if property_id.property_image_ids:
            chunks = [image_list[i:i + 2] for i in range(0, len(property_id.property_image_ids), 2)]
            limit = 0
            chunk = 0
            for image in property_id.property_image_ids:
                if limit == 2:
                    limit = 0 
                    chunk += 1
                chunks[chunk].append(image.datas)
                limit += 1
            image_list = chunks
        return image_list

    def get_floor_plan_images(self, property_id):
        image_list = []
        if property_id.floor_plan_image_ids:
            chunks = [image_list[i:i + 2] for i in range(0, len(property_id.floor_plan_image_ids), 2)]
            limit = 0
            chunk = 0
            for image in property_id.floor_plan_image_ids:
                if limit == 2:
                    limit = 0
                    chunk += 1
                chunks[chunk].append(image.datas)
                limit += 1
            image_list = chunks
        return image_list

    def _get_report_values(self, docids, data=None):
        docs = self.env['property.property'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'property.property',
            'get_property_images': self.get_property_images,
            'get_floor_plan_images': self.get_floor_plan_images,
            'docs': docs,
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: