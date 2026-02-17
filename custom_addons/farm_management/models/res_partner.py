# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ResPartnerProductCode(models.Model):
    _name = 'res.partner.product.code'
    _description = 'رمز منتج العميل'
    _order = 'product_id'
    _rec_name = 'product_id'

    partner_id = fields.Many2one(
        'res.partner',
        string='العميل',
        required=True,
        ondelete='cascade',
        index=True,
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='المنتج',
        required=True,
        domain="[('default_code', '=like', '70%')]",
        help='منتجات جاهزة (تبدأ بـ 70)',
    )
    
    product_default_code = fields.Char(
        related='product_id.default_code',
        string='رمز المنتج الأصلي',
        readonly=True,
    )
    
    custom_code = fields.Char(
        string='الرمز المخصص',
        required=True,
        help='رمز الباركود المخصص لهذا العميل',
    )
    
    company_id = fields.Many2one(
        related='partner_id.company_id',
        store=True,
    )

    _sql_constraints = [
        ('partner_product_unique', 
         'UNIQUE(partner_id, product_id)', 
         'لا يمكن تكرار نفس المنتج لنفس العميل!'),
    ]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    product_code_ids = fields.One2many(
        'res.partner.product.code',
        'partner_id',
        string='رموز المنتجات المخصصة',
    )
    
    product_code_count = fields.Integer(
        string='عدد رموز المنتجات',
        compute='_compute_product_code_count',
    )

    @api.depends('product_code_ids')
    def _compute_product_code_count(self):
        for partner in self:
            partner.product_code_count = len(partner.product_code_ids)

    def action_view_product_codes(self):
        """Open product codes for this partner"""
        self.ensure_one()
        return {
            'name': _('رموز المنتجات المخصصة'),
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner.product.code',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

    def get_product_barcode(self, product):
        """Get the barcode for a product: custom code if exists, else default_code"""
        self.ensure_one()
        custom = self.product_code_ids.filtered(lambda c: c.product_id == product)
        if custom:
            return custom[0].custom_code
        return product.default_code or ''


