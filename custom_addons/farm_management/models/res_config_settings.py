# -*- coding: utf-8 -*-

import re
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    farm_produce_code_regex = fields.Char(
        string='رمز المنتجات الزراعية',
        help='نمط Regex لتحديد المنتجات الزراعية حسب رمز المنتج. مثال: ^70 يعني المنتجات التي تبدأ بـ 70',
        config_parameter='farm_management.produce_code_regex',
        default='^70',
    )
    
    farm_harvest_source_location_id = fields.Many2one(
        'stock.location',
        string='موقع مصدر الحصاد',
        help='الموقع المصدر لحركات الحصاد (عادة موقع الإنتاج)',
        config_parameter='farm_management.harvest_source_location_id',
        domain="[('usage', 'in', ['production', 'inventory', 'transit'])]",
    )
    
    farm_harvest_dest_location_id = fields.Many2one(
        'stock.location',
        string='موقع وجهة الحصاد',
        help='موقع المخزون الذي يستلم المحصول',
        config_parameter='farm_management.harvest_dest_location_id',
        domain="[('usage', '=', 'internal')]",
    )

    # Order destination location
    farm_order_dest_location_id = fields.Many2one(
        'stock.location',
        string='موقع وجهة الطلبات',
        help='الموقع الذي سيتم نقل المنتجات إليه عند الموافقة على الطلب',
        config_parameter='farm_management.order_dest_location_id',
        domain="[('usage', '=', 'internal')]",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        res['farm_produce_code_regex'] = self.env['ir.config_parameter'].sudo().get_param(
            'farm_management.produce_code_regex', default='^70'
        )
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'farm_management.produce_code_regex',
            self.farm_produce_code_regex or '^70'
        )
        # Recompute is_farm_produce for all products when regex changes
        self.env['product.product'].recompute_farm_produce_flag()

    @api.model
    def get_produce_code_regex(self):
        """Get the configured produce code regex pattern"""
        return self.env['ir.config_parameter'].sudo().get_param(
            'farm_management.produce_code_regex', default='^70'
        )

    @api.model
    def is_produce_product(self, product):
        """Check if a product is a produce item based on its default_code"""
        if not product or not product.default_code:
            return False
        pattern = self.get_produce_code_regex()
        try:
            return bool(re.match(pattern, product.default_code))
        except re.error:
            return False

    @api.model
    def get_produce_products(self):
        """Get all products that match the produce code regex"""
        pattern = self.get_produce_code_regex()
        if not pattern:
            return self.env['product.product'].browse()
        
        # Get all products with default_code
        products = self.env['product.product'].search([
            ('default_code', '!=', False),
            ('default_code', '!=', ''),
        ])
        
        # Filter by regex
        produce_products = self.env['product.product']
        try:
            regex = re.compile(pattern)
            for product in products:
                if product.default_code and regex.match(product.default_code):
                    produce_products |= product
        except re.error:
            pass
        
        return produce_products

