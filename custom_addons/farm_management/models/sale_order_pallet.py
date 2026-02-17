# -*- coding: utf-8 -*-

import base64
from io import BytesIO

from odoo import api, fields, models, _

try:
    from barcode import Code128
    from barcode.writer import ImageWriter
    BARCODE_AVAILABLE = True
except ImportError:
    BARCODE_AVAILABLE = False


class SaleOrderPallet(models.Model):
    _name = 'sale.order.pallet'
    _description = 'باليت طلب المبيعات'
    _order = 'sequence, id'

    name = fields.Char(
        string='رقم الباليت',
        required=True,
        default='جديد',
    )
    
    order_id = fields.Many2one(
        'sale.order',
        string='طلب المبيعات',
        required=True,
        ondelete='cascade',
        index=True,
    )
    
    sequence = fields.Integer(
        string='الترتيب',
        default=10,
    )
    
    line_ids = fields.One2many(
        'sale.order.pallet.line',
        'pallet_id',
        string='محتويات الباليت',
    )
    
    total_kg = fields.Float(
        string='إجمالي الوزن (كجم)',
        compute='_compute_totals',
        store=True,
    )
    
    total_boxes = fields.Integer(
        string='إجمالي الصناديق',
        compute='_compute_totals',
        store=True,
    )
    
    company_id = fields.Many2one(
        related='order_id.company_id',
        store=True,
    )
    
    partner_id = fields.Many2one(
        related='order_id.partner_id',
        string='العميل',
        store=True,
    )
    
    # Available products from SO lines
    available_product_ids = fields.Many2many(
        'product.product',
        compute='_compute_available_products',
        string='المنتجات المتاحة',
    )

    @api.depends('line_ids.subtotal_kg', 'line_ids.box_quantity')
    def _compute_totals(self):
        for pallet in self:
            pallet.total_kg = sum(pallet.line_ids.mapped('subtotal_kg'))
            pallet.total_boxes = sum(pallet.line_ids.mapped('box_quantity'))

    @api.depends('order_id.order_line.product_id')
    def _compute_available_products(self):
        for pallet in self:
            if pallet.order_id:
                pallet.available_product_ids = pallet.order_id.order_line.mapped('product_id')
            else:
                pallet.available_product_ids = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'جديد') == 'جديد' and vals.get('order_id'):
                order = self.env['sale.order'].browse(vals['order_id'])
                pallet_count = len(order.pallet_ids) + 1
                vals['name'] = _('باليت %s') % pallet_count
        return super().create(vals_list)

    def action_print_label(self):
        """Print shipping label for this pallet using image-based PDF for exact roll sizing"""
        self.ensure_one()
        # Use custom image-based PDF endpoint
        return {
            'type': 'ir.actions.act_url',
            'url': f'/report/pallet_label/{self.id}',
            'target': 'new',
        }
    
    def action_print_label_standard(self):
        """Fallback: Print using standard QWeb PDF"""
        self.ensure_one()
        return self.env.ref('farm_management.action_report_pallet_label').report_action(self)


class SaleOrderPalletLine(models.Model):
    _name = 'sale.order.pallet.line'
    _description = 'بند باليت طلب المبيعات'
    _order = 'pallet_id, id'

    pallet_id = fields.Many2one(
        'sale.order.pallet',
        string='الباليت',
        required=True,
        ondelete='cascade',
        index=True,
    )
    
    order_id = fields.Many2one(
        related='pallet_id.order_id',
        store=True,
        string='طلب المبيعات',
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='المنتج',
        required=True,
        domain="[('id', 'in', parent.available_product_ids)]",
    )
    
    product_name = fields.Char(
        related='product_id.name',
        string='اسم المنتج',
    )
    
    box_weight_kg = fields.Float(
        string='وزن الصندوق (كجم)',
        required=True,
        default=0.0,
        help='وزن الصندوق الواحد بالكيلوجرام',
    )
    
    box_quantity = fields.Integer(
        string='عدد الصناديق',
        required=True,
        default=1,
    )
    
    subtotal_kg = fields.Float(
        string='إجمالي الوزن (كجم)',
        compute='_compute_subtotal',
        store=True,
    )
    
    # Tracking fields for order fulfillment
    ordered_qty = fields.Float(
        string='الكمية المطلوبة',
        compute='_compute_order_progress',
        help='الكمية المطلوبة في أمر البيع',
    )
    
    ordered_uom = fields.Char(
        string='وحدة القياس',
        compute='_compute_order_progress',
    )
    
    palletized_qty = fields.Float(
        string='الكمية المعبأة',
        compute='_compute_order_progress',
        help='إجمالي الكمية المعبأة في جميع الباليتات',
    )
    
    remaining_qty = fields.Float(
        string='الكمية المتبقية',
        compute='_compute_order_progress',
        help='الكمية المتبقية للتعبئة',
    )
    
    progress_percent = fields.Float(
        string='نسبة الإنجاز',
        compute='_compute_order_progress',
        help='نسبة التعبئة من الكمية المطلوبة',
    )
    
    is_complete = fields.Boolean(
        string='مكتمل',
        compute='_compute_order_progress',
        help='تم تعبئة الكمية المطلوبة بالكامل',
    )
    
    is_over = fields.Boolean(
        string='تجاوز',
        compute='_compute_order_progress',
        help='تم تجاوز الكمية المطلوبة',
    )

    @api.depends('box_weight_kg', 'box_quantity')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal_kg = line.box_weight_kg * line.box_quantity

    @api.depends('product_id', 'box_weight_kg', 'box_quantity')
    def _compute_order_progress(self):
        for line in self:
            line._update_order_progress()

    def _update_order_progress(self):
        """Calculate order progress - used by both compute and onchange"""
        self.ensure_one()
        ordered_qty = 0.0
        ordered_uom = ''
        palletized_qty = 0.0
        
        if self.product_id and self.pallet_id and self.pallet_id.order_id:
            order = self.pallet_id.order_id
            product = self.product_id
            
            # Get ordered quantity from SO lines
            so_lines = order.order_line.filtered(
                lambda l: l.product_id == product
            )
            ordered_qty = sum(so_lines.mapped('product_uom_qty'))
            if so_lines:
                ordered_uom = so_lines[0].product_uom.name or ''
            
            # Collect IDs of all unsaved lines in current pallet for this product
            current_pallet_line_ids = set()
            current_pallet_subtotal = 0.0
            
            if self.pallet_id.line_ids:
                for line in self.pallet_id.line_ids:
                    if line.product_id == product:
                        # Calculate from current form values (might be unsaved)
                        current_pallet_subtotal += line.box_weight_kg * line.box_quantity
                        # Track the origin IDs to exclude from DB query
                        if line._origin and line._origin.id:
                            current_pallet_line_ids.add(line._origin.id)
            
            # Get palletized qty from OTHER pallets (saved in DB) for this product
            domain = [
                ('order_id', '=', order.id),
                ('product_id', '=', product.id),
            ]
            # Exclude lines that are in our current pallet (we already counted them)
            if current_pallet_line_ids:
                domain.append(('id', 'not in', list(current_pallet_line_ids)))
            
            other_pallets_lines = self.env['sale.order.pallet.line'].search(domain)
            other_pallets_subtotal = sum(other_pallets_lines.mapped('subtotal_kg'))
            
            # Total palletized = current pallet (from form) + other pallets (from DB)
            palletized_qty = current_pallet_subtotal + other_pallets_subtotal
        
        self.ordered_qty = ordered_qty
        self.ordered_uom = ordered_uom
        self.palletized_qty = palletized_qty
        self.remaining_qty = max(0, ordered_qty - palletized_qty)
        self.progress_percent = (palletized_qty / ordered_qty * 100) if ordered_qty > 0 else 0
        self.is_complete = palletized_qty >= ordered_qty if ordered_qty > 0 else False
        self.is_over = palletized_qty > ordered_qty if ordered_qty > 0 else False

    @api.onchange('product_id', 'box_weight_kg', 'box_quantity')
    def _onchange_update_progress(self):
        """Update progress indicators in real-time as user types"""
        # Update all lines in the pallet (same product might appear multiple times)
        if self.pallet_id and self.pallet_id.line_ids:
            for line in self.pallet_id.line_ids:
                line._update_order_progress()
        else:
            self._update_order_progress()

    def get_barcode(self):
        """Get barcode: customer code if exists, else product default_code"""
        self.ensure_one()
        partner = self.pallet_id.partner_id
        if partner:
            return partner.get_product_barcode(self.product_id)
        return self.product_id.default_code or ''

    def get_barcode_image(self):
        """Generate barcode as base64 data URI for PDF reports"""
        self.ensure_one()
        barcode_value = self.get_barcode()
        if not barcode_value:
            return ''
        
        if BARCODE_AVAILABLE:
            try:
                # Generate barcode using python-barcode library
                buffer = BytesIO()
                code = Code128(str(barcode_value), writer=ImageWriter())
                code.write(buffer, options={
                    'module_width': 0.3,
                    'module_height': 8,
                    'font_size': 8,
                    'text_distance': 3,
                    'quiet_zone': 2,
                })
                buffer.seek(0)
                img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                return f'data:image/png;base64,{img_base64}'
            except Exception:
                pass
        
        # Fallback: return empty (template will show code as text)
        return ''