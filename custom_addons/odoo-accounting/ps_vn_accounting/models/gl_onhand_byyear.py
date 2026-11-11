# -*- coding: utf-8 -*-
"""Model rỗng lưu số dư đầu kỳ theo năm tài chính."""

from odoo import models


class GlOnhandByYear(models.Model):
    _name = "gl.onhand.byyear"
    _description = "GL Onhand By Year"
