# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import re


class ProductQuickAddWizard(models.TransientModel):
    """Wizard to quickly add products with auto-generated codes"""
    _name = 'product.quick.add.wizard'
    _description = 'معالج إضافة منتج سريع'

    name = fields.Char(
        string='اسم المنتج',
        required=True,
    )
    name_en = fields.Char(
        string='الاسم بالإنجليزية',
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='المستودع',
        required=True,
        help='اختر المستودع (رمز المخزون)',
    )
    category_id = fields.Many2one(
        'product.category',
        string='التصنيف',
        required=True,
        domain="[('farm_category_code', '!=', False)]",
        help='اختر التصنيف (يجب أن يحتوي على رمز تصنيف)',
    )
    color_id = fields.Many2one(
        'farm.product.color',
        string='اللون',
        required=True,
        help='اختر اللون',
    )
    
    # Code components (computed)
    inventory_code = fields.Char(
        string='رمز المخزون',
        compute='_compute_codes',
        store=False,
    )
    category_code = fields.Char(
        string='رمز التصنيف',
        compute='_compute_codes',
        store=False,
    )
    color_code = fields.Char(
        string='رمز اللون',
        compute='_compute_codes',
        store=False,
    )
    
    # Generated code preview
    generated_code = fields.Char(
        string='الرمز المولد',
        compute='_compute_generated_code',
        store=False,
        readonly=True,
    )
    next_sequence = fields.Integer(
        string='الرقم التسلسلي التالي',
        compute='_compute_generated_code',
        store=False,
        readonly=True,
    )
    
    # Additional product fields
    list_price = fields.Float(
        string='سعر البيع',
        default=0.0,
    )
    standard_price = fields.Float(
        string='التكلفة',
        default=0.0,
    )
    description = fields.Text(
        string='الوصف',
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='وحدة القياس',
        default=lambda self: self.env.ref('uom.product_uom_unit', raise_if_not_found=False),
    )

    @api.depends('warehouse_id', 'category_id', 'color_id')
    def _compute_codes(self):
        for wizard in self:
            # Get inventory code from warehouse
            if wizard.warehouse_id:
                wizard.inventory_code = wizard.warehouse_id.get_inventory_code()
            else:
                wizard.inventory_code = '00'
            
            # Get category code
            if wizard.category_id:
                wizard.category_code = wizard.category_id.get_category_code()
            else:
                wizard.category_code = '000'
            
            # Get color code
            if wizard.color_id:
                wizard.color_code = wizard.color_id.code or '00'
            else:
                wizard.color_code = '00'

    @api.depends('inventory_code', 'category_code', 'color_code')
    def _compute_generated_code(self):
        for wizard in self:
            if wizard.inventory_code and wizard.category_code and wizard.color_code:
                prefix = f"{wizard.inventory_code}{wizard.category_code}{wizard.color_code}"
                next_seq = wizard._get_next_sequence(prefix)
                
                wizard.next_sequence = next_seq
                wizard.generated_code = f"{prefix}{str(next_seq).zfill(4)}"
            else:
                wizard.generated_code = False
                wizard.next_sequence = 0

    def _get_next_sequence(self, prefix):
        """Get the next sequence number for products with the given prefix"""
        self.ensure_one()
        
        # Search for existing products with this prefix
        products = self.env['product.template'].search([
            ('default_code', '=like', f'{prefix}%')
        ])
        
        if not products:
            return 1001  # Start from 1001
        
        # Extract sequence numbers and find max
        max_seq = 1000
        for product in products:
            code = product.default_code
            if code and len(code) >= len(prefix) + 4:
                try:
                    seq = int(code[len(prefix):len(prefix)+4])
                    if seq > max_seq:
                        max_seq = seq
                except ValueError:
                    continue
        
        return max_seq + 1

    @api.onchange('warehouse_id')
    def _onchange_warehouse(self):
        """Filter categories based on warehouse inventory code"""
        if self.warehouse_id:
            inv_code = self.warehouse_id.get_inventory_code()
            # Filter categories that start with the inventory code first digit
            # e.g., warehouse 10 → categories 1xx
            if inv_code and len(inv_code) >= 1:
                first_digit = inv_code[0]
                return {
                    'domain': {
                        'category_id': [
                            ('farm_category_code', '!=', False),
                            ('farm_category_code', '=like', f'{first_digit}%'),
                        ]
                    }
                }
        return {'domain': {'category_id': [('farm_category_code', '!=', False)]}}

    def action_create_product(self):
        """Create the product with generated code"""
        self.ensure_one()
        
        if not self.generated_code:
            raise UserError(_('لا يمكن توليد الرمز. تأكد من اختيار جميع الحقول المطلوبة.'))
        
        # Check if code already exists
        existing = self.env['product.template'].search([
            ('default_code', '=', self.generated_code)
        ], limit=1)
        
        if existing:
            raise UserError(_('الرمز %s موجود بالفعل!') % self.generated_code)
        
        # Create product
        product_vals = {
            'name': self.name,
            'default_code': self.generated_code,
            'categ_id': self.category_id.id,
            'detailed_type': 'product',
            'list_price': self.list_price,
            'standard_price': self.standard_price,
            'uom_id': self.uom_id.id if self.uom_id else False,
            'uom_po_id': self.uom_id.id if self.uom_id else False,
        }
        
        if self.name_en:
            product_vals['description'] = self.name_en
        if self.description:
            product_vals['description_sale'] = self.description
        
        product = self.env['product.template'].create(product_vals)
        
        # Return action to view created product
        return {
            'type': 'ir.actions.act_window',
            'name': 'المنتج الجديد',
            'res_model': 'product.template',
            'res_id': product.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_and_new(self):
        """Create product and open new wizard"""
        self.action_create_product()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'إضافة منتج جديد',
            'res_model': 'product.quick.add.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_warehouse_id': self.warehouse_id.id,
                'default_category_id': self.category_id.id,
                'default_color_id': self.color_id.id,
            },
        }
