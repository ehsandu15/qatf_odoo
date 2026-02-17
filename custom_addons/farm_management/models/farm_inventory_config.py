# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import re


class FarmProductColor(models.Model):
    """Product Color Configuration - Only colors need manual setup"""
    _name = 'farm.product.color'
    _description = 'لون المنتج'
    _order = 'code'

    name = fields.Char(
        string='اللون',
        required=True,
    )
    code = fields.Char(
        string='الرمز',
        required=True,
        size=2,
        help='رمز من رقمين (مثال: 10, 20, 30)',
    )
    html_color = fields.Char(
        string='كود اللون',
        help='HTML color code for display',
        default='#FFFFFF',
    )
    active = fields.Boolean(
        string='نشط',
        default=True,
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'رمز اللون يجب أن يكون فريداً!'),
    ]

    @api.constrains('code')
    def _check_code(self):
        for record in self:
            if not record.code.isdigit() or len(record.code) != 2:
                raise ValidationError(_('رمز اللون يجب أن يكون رقمين فقط!'))


class StockWarehouse(models.Model):
    """Extend Stock Warehouse to get inventory code"""
    _inherit = 'stock.warehouse'

    def get_inventory_code(self):
        """Extract numeric inventory code from warehouse code (WH10 → 10)"""
        self.ensure_one()
        if self.code:
            # Extract digits from warehouse code
            digits = re.sub(r'\D', '', self.code)
            if digits:
                return digits.zfill(2)[:2]  # Ensure 2 digits
        return '00'


class FarmProductCategory(models.Model):
    """Extend Product Category with farm category code"""
    _inherit = 'product.category'

    farm_category_code = fields.Char(
        string='رمز التصنيف',
        size=3,
        help='رمز من ثلاثة أرقام (مثال: 101, 201, 301)',
    )
    
    # Default farm accounts for products in this category
    default_order_account_source = fields.Many2one(
        'account.account',
        string='حساب مصدر الطلبات الافتراضي',
        domain="[('is_direct_cost', '=', True)]",
        company_dependent=True,
        help='حساب المصدر الافتراضي (مدين) لمنتجات هذا التصنيف في طلبات المزرعة',
    )
    default_order_account_destination = fields.Many2one(
        'account.account',
        string='حساب وجهة الطلبات الافتراضي',
        company_dependent=True,
        help='حساب الوجهة الافتراضي (دائن) لمنتجات هذا التصنيف في طلبات المزرعة',
    )

    @api.constrains('farm_category_code')
    def _check_farm_category_code(self):
        for record in self:
            if record.farm_category_code:
                if not record.farm_category_code.isdigit() or len(record.farm_category_code) != 3:
                    raise ValidationError(_('رمز التصنيف يجب أن يكون ثلاثة أرقام فقط!'))

    def get_category_code(self):
        """Get category code - from field or derive from name pattern"""
        self.ensure_one()
        if self.farm_category_code:
            return self.farm_category_code
        return '000'
