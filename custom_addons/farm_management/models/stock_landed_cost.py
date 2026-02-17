# -*- coding: utf-8 -*-

from odoo import fields, models


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    farm_project_id = fields.Many2one(
        'farm.project',
        string='مشروع المزرعة',
        ondelete='set null',
        index=True,
    )
