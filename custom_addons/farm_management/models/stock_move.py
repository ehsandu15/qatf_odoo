# -*- coding: utf-8 -*-

from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    farm_order_id = fields.Many2one(
        'farm.product.order',
        string='طلب منتجات المزرعة',
        ondelete='set null',
        index=True,
    )


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    farm_order_id = fields.Many2one(
        'farm.product.order',
        string='طلب منتجات المزرعة',
        ondelete='set null',
        index=True,
    )

