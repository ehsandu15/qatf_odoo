# -*- coding: utf-8 -*-

import re
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    can_be_ordered = fields.Boolean(
        string='قابل للطلب',
        default=False,
        help='حدد إذا كان يمكن طلب هذا المنتج في طلبات منتجات المزرعة',
    )
    order_account_source = fields.Many2one(
        'account.account',
        string='حساب مصدر الطلبات',
        help='الحساب الذي سيتم القيد منه عند إنشاء قيد الطلب (مدين)',
        company_dependent=True,
    )
    order_account_destination = fields.Many2one(
        'account.account',
        string='حساب وجهة الطلبات',
        help='الحساب الذي سيتم القيد إليه عند إنشاء قيد الطلب (دائن)',
        company_dependent=True,
    )


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_farm_produce = fields.Boolean(
        string='منتج زراعي',
        compute='_compute_is_farm_produce',
        store=True,
        help='يتم تحديده تلقائياً بناءً على رمز المنتج',
    )
    
    can_be_ordered = fields.Boolean(
        related='product_tmpl_id.can_be_ordered',
        store=True,
        string='قابل للطلب',
    )

    @api.depends('default_code')
    def _compute_is_farm_produce(self):
        """Compute if product is a farm produce based on regex pattern"""
        pattern = self.env['ir.config_parameter'].sudo().get_param(
            'farm_management.produce_code_regex', default='^70'
        )
        
        regex = None
        if pattern:
            try:
                regex = re.compile(pattern)
            except re.error:
                regex = None
        
        for product in self:
            if regex and product.default_code:
                product.is_farm_produce = bool(regex.match(product.default_code))
            else:
                product.is_farm_produce = False

    @api.model
    def recompute_farm_produce_flag(self):
        """Recompute is_farm_produce for all products - called when regex config changes"""
        products = self.search([])
        products._compute_is_farm_produce()
        return True

