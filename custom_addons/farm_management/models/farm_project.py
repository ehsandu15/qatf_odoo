# -*- coding: utf-8 -*-

import re
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import date


class FarmProject(models.Model):
    _name = 'farm.project'
    _description = 'مشروع المزرعة'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='اسم المشروع',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='رمز المشروع',
        readonly=True,
        copy=False,
        default='جديد',
    )
    farm_id = fields.Many2one(
        'farm.farm',
        string='المزرعة',
        required=True,
        tracking=True,
        ondelete='cascade',
    )
    
    # Dates
    planned_start_date = fields.Date(
        string='تاريخ البدء المخطط',
        tracking=True,
    )
    actual_start_date = fields.Date(
        string='تاريخ البدء الفعلي',
        readonly=True,
        tracking=True,
    )
    expected_finish_date = fields.Date(
        string='تاريخ الانتهاء المتوقع',
        tracking=True,
    )
    actual_finish_date = fields.Date(
        string='تاريخ الانتهاء الفعلي',
        readonly=True,
        tracking=True,
    )
    paused_date = fields.Date(
        string='تاريخ الإيقاف المؤقت',
        readonly=True,
    )
    total_paused_days = fields.Integer(
        string='إجمالي أيام الإيقاف',
        default=0,
        readonly=True,
    )
    
    # Status
    status = fields.Selection([
        ('draft', 'مسودة'),
        ('in_progress', 'قيد التنفيذ'),
        ('paused', 'متوقف مؤقتاً'),
        ('completed', 'مكتمل'),
        ('cancelled', 'ملغي'),
    ], string='الحالة', default='draft', tracking=True, required=True)
    
    notes = fields.Text(
        string='ملاحظات',
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='الشركة',
        related='farm_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='العملة',
        related='company_id.currency_id',
    )
    
    # House assignments
    house_assignment_ids = fields.One2many(
        'farm.project.house',
        'project_id',
        string='البيوت المخصصة',
    )
    
    # Cost entries
    cost_ids = fields.One2many(
        'farm.project.cost',
        'project_id',
        string='التكاليف',
    )
    
    # Status history
    status_history_ids = fields.One2many(
        'farm.project.status.history',
        'project_id',
        string='سجل الحالات',
    )
    
    # Landed costs (AVCO update)
    landed_cost_ids = fields.One2many(
        'stock.landed.cost',
        'farm_project_id',
        string='تكاليف المخزون الإضافية',
    )
    avco_updated = fields.Boolean(
        string='تم تحديث AVCO',
        default=False,
        tracking=True,
    )
    landed_cost_count = fields.Integer(
        string='عدد تكاليف المخزون',
        compute='_compute_landed_cost_count',
    )
    
    # Computed fields
    house_count = fields.Integer(
        string='عدد البيوت',
        compute='_compute_house_count',
    )
    total_area = fields.Float(
        string='إجمالي المساحة (م²)',
        compute='_compute_total_area',
        store=True,
    )
    total_direct_cost = fields.Monetary(
        string='إجمالي التكاليف المباشرة',
        compute='_compute_costs',
        currency_field='currency_id',
    )
    total_indirect_cost = fields.Monetary(
        string='إجمالي التكاليف غير المباشرة',
        compute='_compute_costs',
        currency_field='currency_id',
    )
    total_cost = fields.Monetary(
        string='إجمالي التكاليف',
        compute='_compute_costs',
        currency_field='currency_id',
    )
    cost_per_sqm = fields.Monetary(
        string='التكلفة لكل م²',
        compute='_compute_costs',
        currency_field='currency_id',
    )
    progress_days = fields.Integer(
        string='أيام التقدم',
        compute='_compute_progress',
    )
    remaining_days = fields.Integer(
        string='الأيام المتبقية',
        compute='_compute_progress',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'جديد') == 'جديد':
                vals['code'] = self.env['ir.sequence'].next_by_code('farm.project') or 'جديد'
        return super().create(vals_list)

    @api.depends('house_assignment_ids')
    def _compute_house_count(self):
        for project in self:
            houses = project.house_assignment_ids.mapped('house_id')
            project.house_count = len(houses)

    @api.depends('house_assignment_ids', 'house_assignment_ids.house_id.area')
    def _compute_total_area(self):
        for project in self:
            houses = project.house_assignment_ids.mapped('house_id')
            project.total_area = sum(houses.mapped('area'))

    @api.depends('cost_ids', 'cost_ids.amount', 'cost_ids.cost_type', 'cost_ids.state', 'total_area')
    def _compute_costs(self):
        for project in self:
            # Only count posted costs (harvest costs are direct costs and included in calculations)
            posted_costs = project.cost_ids.filtered(lambda c: c.state == 'posted')
            direct_costs = posted_costs.filtered(lambda c: c.cost_type == 'direct')
            indirect_costs = posted_costs.filtered(lambda c: c.cost_type == 'indirect')
            project.total_direct_cost = sum(direct_costs.mapped('amount'))
            project.total_indirect_cost = sum(indirect_costs.mapped('amount'))
            project.total_cost = project.total_direct_cost + project.total_indirect_cost
            project.cost_per_sqm = project.total_cost / project.total_area if project.total_area else 0

    @api.depends('actual_start_date', 'expected_finish_date', 'status')
    def _compute_progress(self):
        today = date.today()
        for project in self:
            if project.actual_start_date:
                project.progress_days = (today - project.actual_start_date).days - project.total_paused_days
            else:
                project.progress_days = 0
            
            if project.expected_finish_date and project.status in ('draft', 'in_progress', 'paused'):
                project.remaining_days = (project.expected_finish_date - today).days
            else:
                project.remaining_days = 0

    @api.depends('landed_cost_ids')
    def _compute_landed_cost_count(self):
        for project in self:
            project.landed_cost_count = len(project.landed_cost_ids)

    # ========== Status Actions ==========
    
    def action_start(self):
        """Start the project"""
        self.ensure_one()
        if self.status != 'draft':
            raise UserError(_('يمكن بدء المشاريع المسودة فقط'))
        
        self._log_status_change('draft', 'in_progress', _('تم بدء المشروع'))
        self.write({
            'status': 'in_progress',
            'actual_start_date': date.today(),
        })

    def action_pause(self):
        """Pause the project - opens wizard for reason"""
        self.ensure_one()
        if self.status != 'in_progress':
            raise UserError(_('يمكن إيقاف المشاريع قيد التنفيذ فقط'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'إيقاف المشروع مؤقتاً',
            'res_model': 'farm.project.status.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_project_id': self.id,
                'default_action_type': 'pause',
            },
        }

    def action_resume(self):
        """Resume the project - opens wizard for reason"""
        self.ensure_one()
        if self.status != 'paused':
            raise UserError(_('يمكن استئناف المشاريع المتوقفة فقط'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'استئناف المشروع',
            'res_model': 'farm.project.status.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_project_id': self.id,
                'default_action_type': 'resume',
            },
        }

    def action_complete(self):
        """Complete the project"""
        self.ensure_one()
        if self.status != 'in_progress':
            raise UserError(_('يمكن إكمال المشاريع قيد التنفيذ فقط'))
        
        self._log_status_change('in_progress', 'completed', _('تم إكمال المشروع'))
        self.write({
            'status': 'completed',
            'actual_finish_date': date.today(),
        })
        # Auto-update product AVCO on completion
        self._update_product_avco()

    def action_cancel(self):
        """Cancel the project - opens wizard for reason"""
        self.ensure_one()
        if self.status in ('completed', 'cancelled'):
            raise UserError(_('لا يمكن إلغاء المشاريع المكتملة أو الملغية'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'إلغاء المشروع',
            'res_model': 'farm.project.status.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_project_id': self.id,
                'default_action_type': 'cancel',
            },
        }

    def action_reset_to_draft(self):
        """Reset project to draft status"""
        self.ensure_one()
        if self.status == 'completed':
            raise UserError(_('لا يمكن إعادة المشاريع المكتملة للمسودة'))
        
        self._log_status_change(self.status, 'draft', _('تم إعادة المشروع للمسودة'))
        self.write({
            'status': 'draft',
            'actual_start_date': False,
            'paused_date': False,
        })

    def _log_status_change(self, old_status, new_status, reason=False):
        """Log status change to history"""
        self.ensure_one()
        self.env['farm.project.status.history'].create({
            'project_id': self.id,
            'old_status': old_status,
            'new_status': new_status,
            'reason': reason,
            'user_id': self.env.user.id,
        })

    def _do_pause(self, reason):
        """Execute pause action with reason"""
        self.ensure_one()
        self._log_status_change('in_progress', 'paused', reason)
        self.write({
            'status': 'paused',
            'paused_date': date.today(),
        })

    def _do_resume(self, reason):
        """Execute resume action with reason"""
        self.ensure_one()
        paused_days = 0
        if self.paused_date:
            paused_days = (date.today() - self.paused_date).days
        
        self._log_status_change('paused', 'in_progress', reason)
        self.write({
            'status': 'in_progress',
            'paused_date': False,
            'total_paused_days': self.total_paused_days + paused_days,
        })

    def _do_cancel(self, reason):
        """Execute cancel action with reason"""
        self.ensure_one()
        self._log_status_change(self.status, 'cancelled', reason)
        self.write({
            'status': 'cancelled',
        })

    # ========== AVCO Update Methods ==========

    def action_update_avco(self):
        """Manual button: redo AVCO update (revert old, recalculate)."""
        self.ensure_one()
        if self.status not in ('in_progress', 'completed'):
            raise UserError(_('يمكن تحديث AVCO فقط للمشاريع قيد التنفيذ أو المكتملة'))
        self._revert_avco()
        self._update_product_avco()

    def _revert_avco(self):
        """Cancel and remove all landed costs created by this project, then reset product AVCO."""
        # Collect products to reset
        products_to_reset = self.env['product.product']
        
        for lc in self.landed_cost_ids:
            products_to_reset |= lc.picking_ids.mapped('move_ids.product_id')
            
            if lc.state == 'done':
                # Reverse the journal entry
                if lc.account_move_id and lc.account_move_id.state == 'posted':
                    lc.account_move_id.button_draft()
                    lc.account_move_id.button_cancel()
                # Remove SVLs created by this landed cost
                self.env['stock.valuation.layer'].sudo().search([
                    ('stock_landed_cost_id', '=', lc.id),
                ]).unlink()
                try:
                    lc.button_cancel()
                except Exception:
                    lc.sudo().write({'state': 'cancel'})
            lc.unlink()
        
        # Reset product AVCO based on remaining SVLs (without landed cost distortions)
        for product in products_to_reset:
            layers = self.env['stock.valuation.layer'].sudo().search([
                ('product_id', '=', product.id),
                ('remaining_qty', '>', 0),
            ])
            total_qty = sum(layers.mapped('remaining_qty'))
            total_value = sum(layers.mapped('remaining_value'))
            if total_qty > 0:
                product.sudo().with_context(disable_auto_svl=True).standard_price = total_value / total_qty
            else:
                product.sudo().with_context(disable_auto_svl=True).standard_price = 0
        
        self.avco_updated = False

    def _update_product_avco(self):
        """Compute AVCO for each house's product: total_real_costs / total_harvested_qty.
        
        Simple approach: directly set the product's standard_price and create
        a landed cost record for audit trail only.
        """
        self.ensure_one()

        # Get the cost service product for landed cost lines
        cost_product = self.env.ref('farm_management.product_post_harvest_cost', raise_if_not_found=False)
        if not cost_product:
            self.message_post(body=_('لم يتم العثور على منتج خدمة التكلفة. يرجى تحديث الوحدة.'))
            return

        # Get a general journal
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_('لم يتم العثور على دفتر يومية عام.'))

        created_count = 0
        for house_assign in self.house_assignment_ids:
            house = house_assign.house_id

            # Sum REAL allocated costs (exclude harvest-created costs to avoid double counting)
            allocations = self.env['farm.cost.allocation'].search([
                ('cost_id.project_id', '=', self.id),
                ('house_id', '=', house.id),
                ('cost_id.state', '=', 'posted'),
                ('cost_id.harvest_entry_id', '=', False),
            ])
            total_allocated = sum(allocations.mapped('allocated_amount'))
            if total_allocated <= 0:
                continue

            # Find harvest entries for this house
            harvest_entries = self.env['farm.harvest.entry'].search([
                ('project_house_id.project_id', '=', self.id),
                ('project_house_id.house_id', '=', house.id),
                ('state', '=', 'done'),
                ('picking_id', '!=', False),
            ])
            if not harvest_entries:
                continue

            picking_ids = harvest_entries.mapped('picking_id')
            product = house_assign.product_id
            if not product:
                continue

            # Get total harvested quantity
            total_qty = sum(harvest_entries.mapped('quantity'))
            if total_qty <= 0:
                continue

            # Compute the target AVCO: total real costs / total harvested qty
            target_avco = total_allocated / total_qty

            # Determine cost account
            cost_account = False
            for alloc in allocations:
                if alloc.cost_id.direct_cost_account_id:
                    cost_account = alloc.cost_id.direct_cost_account_id
                    break
                if alloc.cost_id.indirect_cost_account_id:
                    cost_account = alloc.cost_id.indirect_cost_account_id
                    break
            if not cost_account:
                cost_account = cost_product.property_account_expense_id or \
                               cost_product.categ_id.property_account_expense_categ_id
            if not cost_account:
                continue

            # Directly set the product's standard_price (AVCO)
            product.sudo().with_context(disable_auto_svl=True).standard_price = target_avco

            # Update the SVL remaining_value to match the new AVCO
            # so that Odoo's internal valuation stays consistent
            layers = self.env['stock.valuation.layer'].sudo().search([
                ('product_id', '=', product.id),
                ('remaining_qty', '>', 0),
            ])
            for layer in layers:
                layer.remaining_value = layer.remaining_qty * target_avco

            # Create a landed cost record for audit trail
            landed_cost = self.env['stock.landed.cost'].create({
                'date': fields.Date.today(),
                'account_journal_id': journal.id,
                'picking_ids': [(6, 0, picking_ids.ids)],
                'farm_project_id': self.id,
                'cost_lines': [(0, 0, {
                    'name': _('تكاليف المشروع - %s - بيت %s (AVCO: %s)') % (
                        self.name, house.name, round(target_avco, 2)),
                    'product_id': cost_product.id,
                    'price_unit': total_allocated,
                    'split_method': 'by_quantity',
                    'account_id': cost_account.id,
                })],
            })
            # Mark as done for audit (don't validate via Odoo - we set AVCO directly)
            landed_cost.sudo().write({'state': 'done'})
            created_count += 1

            self.message_post(body=_(
                'بيت %s: AVCO = %s (%s تكاليف حقيقية / %s كمية محصودة)'
            ) % (house.name, round(target_avco, 2), round(total_allocated, 2), round(total_qty, 2)))

        self.avco_updated = True
        if created_count:
            self.message_post(body=_('تم تحديث تكلفة المنتجات (AVCO) لـ %s بيت/بيوت') % created_count)
        else:
            self.message_post(body=_('لم يتم العثور على بيوت بها تكاليف موزعة وسجلات حصاد لتحديث AVCO'))

    def action_view_landed_costs(self):
        """Open landed costs created by this project."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('تكاليف المخزون الإضافية'),
            'res_model': 'stock.landed.cost',
            'view_mode': 'tree,form',
            'domain': [('farm_project_id', '=', self.id)],
            'context': {'default_farm_project_id': self.id},
        }

    # ========== Smart Button Actions ==========
    
    def action_view_costs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'التكاليف',
            'res_model': 'farm.project.cost',
            'view_mode': 'tree,form,pivot,graph',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_view_houses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'البيوت المخصصة',
            'res_model': 'farm.project.house',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }


class FarmProjectHouse(models.Model):
    _name = 'farm.project.house'
    _description = 'تخصيص البيت للمشروع'
    _order = 'project_id, house_id'
    _rec_name = 'display_name'

    project_id = fields.Many2one(
        'farm.project',
        string='المشروع',
        required=True,
        ondelete='cascade',
    )
    house_id = fields.Many2one(
        'farm.house',
        string='البيت',
        required=True,
        ondelete='cascade',
    )
    
    display_name = fields.Char(
        string='الاسم',
        compute='_compute_display_name',
        store=True,
    )

    @api.depends('project_id', 'house_id', 'house_id.code', 'house_id.name', 'product_id')
    def _compute_display_name(self):
        for record in self:
            parts = []
            if record.house_id:
                if record.house_id.code:
                    parts.append(f"[{record.house_id.code}]")
                parts.append(record.house_id.name or '')
            if record.product_id:
                parts.append(f"- {record.product_id.name}")
            record.display_name = ' '.join(parts) if parts else 'جديد'

    def name_get(self):
        result = []
        for record in self:
            parts = []
            if record.house_id:
                if record.house_id.code:
                    parts.append(f"[{record.house_id.code}]")
                parts.append(record.house_id.name or '')
            if record.product_id:
                parts.append(f"- {record.product_id.name}")
            name = ' '.join(parts) if parts else 'جديد'
            result.append((record.id, name))
        return result
    
    # Harvest Planning Fields
    product_id = fields.Many2one(
        'product.product',
        string='المنتج',
        help='المنتج المتوقع حصاده من هذا البيت',
    )
    expected_qty = fields.Float(
        string='الكمية المتوقعة',
        help='كمية الإنتاج المتوقعة للحصاد',
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='وحدة القياس',
        help='وحدة قياس كمية الحصاد',
    )
    season = fields.Char(
        string='الموسم / الدفعة',
        help='موسم أو دفعة الإنتاج (اختياري)',
    )
    activity_description = fields.Char(
        string='وصف النشاط',
    )
    notes = fields.Text(
        string='ملاحظات',
    )
    
    # Related fields
    house_area = fields.Float(
        related='house_id.area',
        string='المساحة (م²)',
        store=True,
    )
    sector_id = fields.Many2one(
        related='house_id.sector_id',
        string='القطاع',
        store=True,
    )
    unit_id = fields.Many2one(
        related='house_id.unit_id',
        string='الوحدة',
        store=True,
    )
    farm_id = fields.Many2one(
        related='project_id.farm_id',
        string='المزرعة',
        store=True,
    )
    company_id = fields.Many2one(
        related='project_id.company_id',
        string='الشركة',
        store=True,
    )
    currency_id = fields.Many2one(
        related='project_id.currency_id',
        string='العملة',
    )
    
    # Harvest Entries
    harvest_entry_ids = fields.One2many(
        'farm.harvest.entry',
        'project_house_id',
        string='سجلات الحصاد',
    )
    
    # ========== Computed Harvest & Cost Fields ==========
    
    total_harvested = fields.Float(
        string='إجمالي المحصود',
        compute='_compute_harvest_stats',
        store=True,
    )
    progress_percent = fields.Float(
        string='نسبة التقدم (%)',
        compute='_compute_harvest_stats',
        store=True,
    )
    harvest_count = fields.Integer(
        string='عدد الحصادات',
        compute='_compute_harvest_stats',
        store=True,
    )
    
    # Cost fields (from cost allocations)
    total_house_cost = fields.Monetary(
        string='إجمالي تكلفة البيت',
        compute='_compute_cost_stats',
        store=True,
        currency_field='currency_id',
    )
    total_allocated_cost = fields.Monetary(
        string='التكلفة المخصصة للحصاد',
        compute='_compute_cost_stats',
        store=True,
        currency_field='currency_id',
    )
    remaining_cost = fields.Monetary(
        string='التكلفة المتبقية',
        compute='_compute_cost_stats',
        store=True,
        currency_field='currency_id',
    )
    avg_unit_cost = fields.Monetary(
        string='متوسط تكلفة الوحدة',
        compute='_compute_cost_stats',
        store=True,
        currency_field='currency_id',
    )

    _sql_constraints = [
        ('unique_project_house', 'UNIQUE(project_id, house_id)', 
         'البيت مخصص بالفعل لهذا المشروع!')
    ]

    @api.model
    def _get_produce_product_domain(self):
        """Get domain to filter produce products based on configured regex pattern"""
        pattern = self.env['ir.config_parameter'].sudo().get_param(
            'farm_management.produce_code_regex', default='^70'
        )
        
        if not pattern:
            return []
        
        # Get all products with default_code
        all_products = self.env['product.product'].search([
            ('default_code', '!=', False),
            ('default_code', '!=', ''),
        ])
        
        # Filter by regex
        produce_product_ids = []
        try:
            regex = re.compile(pattern)
            for product in all_products:
                if product.default_code and regex.match(product.default_code):
                    produce_product_ids.append(product.id)
        except re.error:
            # If regex is invalid, return empty domain (show all)
            return []
        
        return [('id', 'in', produce_product_ids)]

    @api.constrains('house_id', 'project_id')
    def _check_house_farm(self):
        for record in self:
            if record.house_id.farm_id != record.project_id.farm_id:
                raise ValidationError(_('يجب أن يكون البيت من نفس مزرعة المشروع'))

    @api.depends('harvest_entry_ids', 'harvest_entry_ids.quantity', 'expected_qty')
    def _compute_harvest_stats(self):
        for record in self:
            record.total_harvested = sum(record.harvest_entry_ids.mapped('quantity'))
            record.harvest_count = len(record.harvest_entry_ids)
            if record.expected_qty:
                record.progress_percent = (record.total_harvested / record.expected_qty) * 100
            else:
                record.progress_percent = 0

    @api.depends('house_id', 'project_id', 'harvest_entry_ids', 'harvest_entry_ids.allocated_cost')
    def _compute_cost_stats(self):
        for record in self:
            # Get total house cost from cost allocations
            allocations = self.env['farm.cost.allocation'].search([
                ('project_id', '=', record.project_id.id),
                ('house_id', '=', record.house_id.id),
                ('cost_state', '=', 'posted'),
            ])
            record.total_house_cost = sum(allocations.mapped('allocated_amount'))
            
            # Get total allocated to harvest
            record.total_allocated_cost = sum(record.harvest_entry_ids.mapped('allocated_cost'))
            
            # Remaining cost
            record.remaining_cost = record.total_house_cost - record.total_allocated_cost
            
            # Average unit cost
            if record.total_harvested:
                record.avg_unit_cost = record.total_allocated_cost / record.total_harvested
            else:
                record.avg_unit_cost = 0

    def action_view_harvests(self):
        """View harvest entries for this house assignment"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('سجلات الحصاد'),
            'res_model': 'farm.harvest.entry',
            'view_mode': 'tree,form',
            'domain': [('project_house_id', '=', self.id)],
            'context': {'default_project_house_id': self.id},
        }

    def action_view_costs(self):
        """View cost allocations for this house"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('تكاليف البيت'),
            'res_model': 'farm.cost.allocation',
            'view_mode': 'tree,pivot,graph',
            'domain': [
                ('project_id', '=', self.project_id.id),
                ('house_id', '=', self.house_id.id),
            ],
        }


class FarmProjectStatusHistory(models.Model):
    _name = 'farm.project.status.history'
    _description = 'سجل حالات المشروع'
    _order = 'change_date desc, id desc'

    project_id = fields.Many2one(
        'farm.project',
        string='المشروع',
        required=True,
        ondelete='cascade',
    )
    old_status = fields.Selection([
        ('draft', 'مسودة'),
        ('in_progress', 'قيد التنفيذ'),
        ('paused', 'متوقف مؤقتاً'),
        ('completed', 'مكتمل'),
        ('cancelled', 'ملغي'),
    ], string='الحالة السابقة')
    new_status = fields.Selection([
        ('draft', 'مسودة'),
        ('in_progress', 'قيد التنفيذ'),
        ('paused', 'متوقف مؤقتاً'),
        ('completed', 'مكتمل'),
        ('cancelled', 'ملغي'),
    ], string='الحالة الجديدة', required=True)
    change_date = fields.Datetime(
        string='تاريخ التغيير',
        default=fields.Datetime.now,
        readonly=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='المستخدم',
        default=lambda self: self.env.user,
        readonly=True,
    )
    reason = fields.Text(
        string='السبب',
    )
    duration_days = fields.Integer(
        string='المدة (أيام)',
        compute='_compute_duration',
        store=True,
    )
    
    # Computed display fields
    action_display = fields.Char(
        string='الإجراء',
        compute='_compute_action_display',
    )

    @api.depends('old_status', 'new_status')
    def _compute_action_display(self):
        action_map = {
            ('draft', 'in_progress'): 'بدء المشروع',
            ('in_progress', 'paused'): 'إيقاف مؤقت',
            ('paused', 'in_progress'): 'استئناف',
            ('in_progress', 'completed'): 'إكمال',
            ('draft', 'cancelled'): 'إلغاء',
            ('in_progress', 'cancelled'): 'إلغاء',
            ('paused', 'cancelled'): 'إلغاء',
        }
        for record in self:
            key = (record.old_status, record.new_status)
            record.action_display = action_map.get(key, 'تغيير الحالة')

    @api.depends('change_date', 'project_id.status_history_ids')
    def _compute_duration(self):
        for record in self:
            # Find the next status change to calculate duration
            next_record = self.search([
                ('project_id', '=', record.project_id.id),
                ('change_date', '>', record.change_date),
            ], order='change_date asc', limit=1)
            
            if next_record:
                delta = next_record.change_date - record.change_date
                record.duration_days = delta.days
            else:
                # Still in this status
                delta = fields.Datetime.now() - record.change_date
                record.duration_days = delta.days

