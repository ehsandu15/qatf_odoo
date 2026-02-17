# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    pallet_ids = fields.One2many(
        'sale.order.pallet',
        'order_id',
        string='الباليتات',
    )
    
    pallet_count = fields.Integer(
        string='عدد الباليتات',
        compute='_compute_pallet_count',
    )
    
    total_pallet_kg = fields.Float(
        string='إجمالي وزن الباليتات (كجم)',
        compute='_compute_pallet_totals',
    )
    
    total_pallet_boxes = fields.Integer(
        string='إجمالي صناديق الباليتات',
        compute='_compute_pallet_totals',
    )

    @api.depends('pallet_ids')
    def _compute_pallet_count(self):
        for order in self:
            order.pallet_count = len(order.pallet_ids)

    @api.depends('pallet_ids.total_kg', 'pallet_ids.total_boxes')
    def _compute_pallet_totals(self):
        for order in self:
            order.total_pallet_kg = sum(order.pallet_ids.mapped('total_kg'))
            order.total_pallet_boxes = sum(order.pallet_ids.mapped('total_boxes'))

    def get_pallet_progress_summary(self):
        """Get palletizing progress for each product in the order"""
        self.ensure_one()
        summary = []
        
        for line in self.order_line:
            product = line.product_id
            ordered_qty = line.product_uom_qty
            uom = line.product_uom.name
            
            # Get palletized qty for this product
            pallet_lines = self.pallet_ids.mapped('line_ids').filtered(
                lambda l: l.product_id == product
            )
            palletized_qty = sum(pallet_lines.mapped('subtotal_kg'))
            
            remaining = max(0, ordered_qty - palletized_qty)
            progress = (palletized_qty / ordered_qty * 100) if ordered_qty > 0 else 0
            
            summary.append({
                'product_id': product.id,
                'product_name': product.display_name,
                'ordered_qty': ordered_qty,
                'uom': uom,
                'palletized_qty': palletized_qty,
                'remaining_qty': remaining,
                'progress_percent': progress,
                'is_complete': palletized_qty >= ordered_qty,
                'is_over': palletized_qty > ordered_qty,
            })
        
        return summary

    def action_view_pallets(self):
        """Open pallet management view"""
        self.ensure_one()
        return {
            'name': _('باليتات الطلب'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.pallet',
            'view_mode': 'tree,form',
            'domain': [('order_id', '=', self.id)],
            'context': {
                'default_order_id': self.id,
            },
        }

    def action_add_pallet(self):
        """Quick action to add a new pallet"""
        self.ensure_one()
        pallet = self.env['sale.order.pallet'].create({
            'order_id': self.id,
        })
        return {
            'name': _('باليت جديد'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.pallet',
            'res_id': pallet.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_order_id': self.id,
            },
        }

    def action_print_all_pallet_labels(self):
        """Print labels for all pallets using image-based PDF for exact roll sizing"""
        self.ensure_one()
        if not self.pallet_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('تنبيه'),
                    'message': _('لا توجد باليتات لطباعة ملصقاتها'),
                    'type': 'warning',
                }
            }
        # Use custom image-based PDF endpoint with comma-separated IDs
        pallet_ids = ','.join(str(p.id) for p in self.pallet_ids)
        return {
            'type': 'ir.actions.act_url',
            'url': f'/report/pallet_label/{pallet_ids}',
            'target': 'new',
        }

