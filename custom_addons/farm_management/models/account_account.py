# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    is_direct_cost = fields.Boolean(
        string='تكلفة مباشرة للمزرعة',
        default=False,
        help='حدد هذا الخيار إذا كان هذا الحساب يستخدم للتكاليف المباشرة في مشاريع المزارع',
    )
    
    is_indirect_cost = fields.Boolean(
        string='تكلفة غير مباشرة للمزرعة',
        default=False,
        help='حدد هذا الخيار إذا كان هذا الحساب يستخدم للتكاليف غير المباشرة في مشاريع المزارع',
    )

