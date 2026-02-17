# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import date


class FarmProjectCost(models.Model):
    _name = 'farm.project.cost'
    _description = 'تكاليف مشروع المزرعة'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='المرجع',
        readonly=True,
        copy=False,
        default='جديد',
    )
    
    # State for workflow
    state = fields.Selection([
        ('draft', 'مسودة'),
        ('posted', 'مرحّل'),
        ('cancelled', 'ملغى'),
    ], string='الحالة', default='draft', required=True, tracking=True, copy=False)
    
    # Link to accounting entry
    move_id = fields.Many2one(
        'account.move',
        string='القيد المحاسبي',
        readonly=True,
        copy=False,
        ondelete='set null',
    )
    
    # Link to product order
    order_id = fields.Many2one(
        'farm.product.order',
        string='طلب المنتجات',
        readonly=True,
        copy=False,
        ondelete='set null',
    )
    
    # Order's accounting entries (computed from order.move_id)
    order_move_ids = fields.Many2many(
        'account.move',
        compute='_compute_order_move_ids',
        string='القيود المحاسبية',
    )
    
    project_id = fields.Many2one(
        'farm.project',
        string='المشروع',
        required=True,
        ondelete='restrict',
        tracking=True,
        domain="[('status', 'in', ['draft', 'in_progress', 'paused'])]",
    )
    farm_id = fields.Many2one(
        related='project_id.farm_id',
        string='المزرعة',
        store=True,
    )
    
    # Cost type
    cost_type = fields.Selection([
        ('direct', 'مباشر'),
        ('indirect', 'غير مباشر'),
    ], string='نوع التكلفة', required=True, default='direct', tracking=True)
    
    # Link to harvest entry (for harvest-created direct costs)
    harvest_entry_id = fields.Many2one(
        'farm.harvest.entry',
        string='سجل الحصاد',
        readonly=True,
        copy=False,
        ondelete='set null',
        help='سجل الحصاد المرتبط بهذه التكلفة (تكلفة مباشرة من حصاد)',
    )
    
    # Link to landed cost (for post-harvest costs that affect AVCO)
    landed_cost_id = fields.Many2one(
        'stock.landed.cost',
        string='تكلفة إضافية على المخزون',
        readonly=True,
        copy=False,
        ondelete='set null',
        help='سجل التكاليف الإضافية على المخزون (Landed Cost) المرتبط بهذه التكلفة',
    )
    
    # Display type (for showing harvest in views)
    display_cost_type = fields.Char(
        string='نوع العرض',
        compute='_compute_display_cost_type',
        store=True,
    )
    
    # Multi-select source fields for direct costs
    source_sector_ids = fields.Many2many(
        'farm.sector',
        'farm_cost_sector_rel',
        'cost_id',
        'sector_id',
        string='القطاعات',
        tracking=True,
    )
    source_unit_ids = fields.Many2many(
        'farm.unit',
        'farm_cost_unit_rel',
        'cost_id',
        'unit_id',
        string='الوحدات',
        tracking=True,
    )
    source_house_ids = fields.Many2many(
        'farm.house',
        'farm_cost_house_rel',
        'cost_id',
        'house_id',
        string='البيوت',
        tracking=True,
    )
    
    # Computed fields for available sources (based on project house assignments)
    available_house_ids = fields.Many2many(
        'farm.house',
        compute='_compute_available_sources',
        string='البيوت المتاحة',
    )
    available_unit_ids = fields.Many2many(
        'farm.unit',
        compute='_compute_available_sources',
        string='الوحدات المتاحة',
    )
    available_sector_ids = fields.Many2many(
        'farm.sector',
        compute='_compute_available_sources',
        string='القطاعات المتاحة',
    )
    
    # Payment account (FROM - e.g., bank, cash)
    # Not required when cost is from an order (order creates its own journal entry)
    payment_account_id = fields.Many2one(
        'account.account',
        string='حساب الدفع (من)',
        tracking=True,
        help='الحساب الذي تم الدفع منه (مثل: البنك، الصندوق). غير مطلوب للتكاليف المرتبطة بطلبات المنتجات.',
    )
    
    # Direct cost account (TO - marked with is_direct_cost boolean)
    direct_cost_account_id = fields.Many2one(
        'account.account',
        string='حساب التكلفة المباشرة (إلى)',
        tracking=True,
        domain="[('is_direct_cost', '=', True)]",
        help='الحساب المحاسبي للتكلفة المباشرة',
    )
    
    # Indirect cost account (TO - marked with is_indirect_cost boolean)
    indirect_cost_account_id = fields.Many2one(
        'account.account',
        string='حساب التكلفة غير المباشرة (إلى)',
        tracking=True,
        domain="[('is_indirect_cost', '=', True)]",
        help='الحساب المحاسبي للتكلفة غير المباشرة',
    )
    
    # Auto-generated ledger description
    ledger_description = fields.Char(
        string='وصف القيد',
        compute='_compute_ledger_description',
        store=True,
    )
    
    # Source display
    source_display = fields.Char(
        string='المصدر',
        compute='_compute_source_display',
    )
    
    # Amount and date
    amount = fields.Monetary(
        string='المبلغ',
        required=True,
        tracking=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='العملة',
        related='project_id.currency_id',
    )
    date = fields.Date(
        string='التاريخ',
        default=fields.Date.today,
        required=True,
        tracking=True,
    )
    description = fields.Text(
        string='الوصف',
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='الشركة',
        related='project_id.company_id',
        store=True,
    )
    
    # Allocation lines
    allocation_line_ids = fields.One2many(
        'farm.cost.allocation',
        'cost_id',
        string='خطوط التوزيع',
    )
    
    # Computed fields
    allocated_amount = fields.Monetary(
        string='المبلغ الموزع',
        compute='_compute_allocated_amount',
        currency_field='currency_id',
    )
    house_count = fields.Integer(
        string='عدد البيوت',
        compute='_compute_allocated_amount',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'جديد') == 'جديد':
                vals['name'] = self.env['ir.sequence'].next_by_code('farm.project.cost') or 'جديد'
        records = super().create(vals_list)
        for record in records:
            record._compute_allocations()
        return records

    def write(self, vals):
        result = super().write(vals)
        # Recompute allocations if relevant fields changed
        trigger_fields = ['amount', 'cost_type', 'source_sector_ids', 'source_unit_ids', 
                         'source_house_ids', 'project_id']
        if any(field in vals for field in trigger_fields):
            for record in self:
                if record.state == 'draft':
                    record._compute_allocations()
        return result

    def unlink(self):
        """Prevent deletion - only allow cancellation"""
        for record in self:
            raise UserError(_('لا يمكن حذف التكاليف. يمكنك فقط إلغاؤها.'))
        return super().unlink()

    # ==========================================
    # ACTION METHODS
    # ==========================================
    
    def action_post(self):
        """Post the cost and create journal entry (skip if from order)"""
        for cost in self:
            if cost.state != 'draft':
                raise UserError(_('يمكن ترحيل التكاليف في حالة المسودة فقط'))
            
            if not cost.order_id:
                # Skip journal creation if cost is from an order (order already has its own journal entry)
                cost._create_accounting_entry()
                cost.message_post(body=_('تم ترحيل التكلفة وإنشاء القيد المحاسبي'))
            else:
                cost.message_post(body=_('تم ترحيل التكلفة (القيد المحاسبي مرتبط بطلب المنتجات)'))
            
            # Update state
            cost.state = 'posted'
        
        return True

    def action_cancel(self):
        """Cancel the cost and reverse/cancel journal entry"""
        for cost in self:
            if cost.state == 'cancelled':
                raise UserError(_('التكلفة ملغاة بالفعل'))
            
            # Cancel landed cost if exists (post-harvest)
            if cost.landed_cost_id:
                if cost.landed_cost_id.state == 'done':
                    # Landed costs that are validated cannot be easily reversed
                    # We cancel the associated accounting entry instead
                    if cost.landed_cost_id.account_move_id:
                        if cost.landed_cost_id.account_move_id.state == 'posted':
                            cost.landed_cost_id.account_move_id.button_draft()
                        cost.landed_cost_id.account_move_id.button_cancel()
                    cost.landed_cost_id.button_cancel()
            
            # Cancel journal entry if exists
            if cost.move_id:
                if cost.move_id.state == 'posted':
                    cost.move_id.button_draft()
                cost.move_id.button_cancel()
            
            # Cancel analytic lines
            cost._cancel_analytic_lines()
            
            # Update state
            cost.state = 'cancelled'
            
            # Post message
            cost.message_post(body=_('تم إلغاء التكلفة والقيود المحاسبية المرتبطة'))
        
        return True

    def action_draft(self):
        """Reset to draft state"""
        for cost in self:
            if cost.state != 'cancelled':
                raise UserError(_('يمكن إعادة التكلفة للمسودة فقط إذا كانت ملغاة'))
            
            cost.state = 'draft'
            cost.message_post(body=_('تم إعادة التكلفة للمسودة'))
        
        return True

    # ==========================================
    # LANDED COST METHODS (Post-Harvest AVCO)
    # ==========================================
    
    # ==========================================
    # ACCOUNTING ENTRY METHODS
    # ==========================================
    
    def _get_default_journal(self):
        """Get default journal for cost entries"""
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_('لم يتم العثور على دفتر يومية عام. يرجى إنشاء واحد.'))
        return journal

    def _create_accounting_entry(self):
        """Create journal entry for the cost"""
        self.ensure_one()
        
        if not self.payment_account_id:
            raise UserError(_('يجب تحديد حساب الدفع'))
        
        journal = self._get_default_journal()
        
        # Prepare move lines
        move_lines = self._prepare_move_lines()
        
        if not move_lines:
            raise UserError(_('لا يمكن إنشاء قيد محاسبي - لا توجد خطوط'))
        
        # Create move
        move_vals = {
            'journal_id': journal.id,
            'date': self.date,
            'ref': self.name,
            'narration': self.ledger_description or self.description,
            'company_id': self.company_id.id,
            'line_ids': [(0, 0, line) for line in move_lines],
        }
        
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        
        self.move_id = move
        
        # Create analytic lines for allocations
        self._create_analytic_lines()
        
        return move

    def _prepare_move_lines(self):
        """Prepare journal entry lines"""
        self.ensure_one()
        lines = []
        
        if self.cost_type == 'indirect':
            # Indirect cost: Credit payment account, Debit indirect cost account
            if not self.indirect_cost_account_id:
                raise UserError(_('يجب تحديد حساب التكلفة للتكاليف غير المباشرة'))
            
            # Credit line (payment account - where money comes from)
            lines.append({
                'name': self.ledger_description or f'دفع - {self.name}',
                'account_id': self.payment_account_id.id,
                'credit': self.amount,
                'debit': 0,
                'partner_id': False,
            })
            
            # Debit line (indirect cost account - where expense goes)
            lines.append({
                'name': self.ledger_description or f'تكلفة غير مباشرة - {self.name}',
                'account_id': self.indirect_cost_account_id.id,
                'debit': self.amount,
                'credit': 0,
                'partner_id': False,
            })
        else:
            # Direct cost: Credit payment account, Debit direct cost account
            if not self.direct_cost_account_id:
                raise UserError(_('يجب تحديد حساب التكلفة للتكاليف المباشرة'))
            
            # Credit line (payment account - where money comes from)
            lines.append({
                'name': self.ledger_description or f'دفع - {self.name}',
                'account_id': self.payment_account_id.id,
                'credit': self.amount,
                'debit': 0,
                'partner_id': False,
            })
            
            # Debit line (direct cost account - where expense goes)
            lines.append({
                'name': self.ledger_description or f'تكلفة مباشرة - {self.name}',
                'account_id': self.direct_cost_account_id.id,
                'debit': self.amount,
                'credit': 0,
                'partner_id': False,
            })
        
        return lines

    def _create_analytic_lines(self):
        """Create analytic lines for each house allocation"""
        self.ensure_one()
        
        # Determine the expense account based on cost type
        if self.cost_type == 'indirect':
            general_account_id = self.indirect_cost_account_id.id
        else:
            general_account_id = self.direct_cost_account_id.id
        
        for allocation in self.allocation_line_ids:
            if allocation.house_id.analytic_account_id:
                self.env['account.analytic.line'].create({
                    'name': self.ledger_description or f'{self.name} - {allocation.house_id.name}',
                    'account_id': allocation.house_id.analytic_account_id.id,
                    'amount': -allocation.allocated_amount,  # Negative for cost
                    'date': self.date,
                    'ref': self.name,
                    'company_id': self.company_id.id,
                    'general_account_id': general_account_id,
                })

    def _cancel_analytic_lines(self):
        """Cancel/delete analytic lines related to this cost"""
        self.ensure_one()
        analytic_lines = self.env['account.analytic.line'].search([
            ('ref', '=', self.name),
            ('company_id', '=', self.company_id.id),
        ])
        analytic_lines.unlink()

    def action_view_move(self):
        """Open the related journal entry"""
        self.ensure_one()
        if self.move_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('القيد المحاسبي'),
                'res_model': 'account.move',
                'res_id': self.move_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    @api.depends('project_id', 'project_id.house_assignment_ids', 'project_id.house_assignment_ids.house_id')
    def _compute_available_sources(self):
        """Compute available sectors, units, and houses based on project assignments"""
        for cost in self:
            if cost.project_id:
                # Get houses assigned to the project
                houses = cost.project_id.house_assignment_ids.mapped('house_id')
                cost.available_house_ids = houses
                
                # Get unique units from those houses
                units = houses.mapped('unit_id')
                cost.available_unit_ids = units
                
                # Get unique sectors from those units
                sectors = units.mapped('sector_id')
                cost.available_sector_ids = sectors
            else:
                cost.available_house_ids = self.env['farm.house']
                cost.available_unit_ids = self.env['farm.unit']
                cost.available_sector_ids = self.env['farm.sector']

    @api.depends('order_id', 'order_id.move_id')
    def _compute_order_move_ids(self):
        """Compute the order's accounting entries for display"""
        for cost in self:
            if cost.order_id and cost.order_id.move_id:
                cost.order_move_ids = cost.order_id.move_id
            else:
                cost.order_move_ids = self.env['account.move']

    @api.depends('cost_type', 'harvest_entry_id')
    def _compute_display_cost_type(self):
        """Compute display type - shows 'حصاد' for harvest-created direct costs"""
        for cost in self:
            if cost.harvest_entry_id:
                cost.display_cost_type = 'حصاد'
            elif cost.cost_type == 'direct':
                cost.display_cost_type = 'مباشر'
            else:
                cost.display_cost_type = 'غير مباشر'

    @api.depends('cost_type', 'source_sector_ids', 'source_unit_ids', 'source_house_ids')
    def _compute_source_display(self):
        for cost in self:
            if cost.cost_type == 'indirect':
                cost.source_display = 'المشروع بالكامل'
            else:
                # Collect all source names
                sources = []
                if cost.source_sector_ids:
                    sources.extend(cost.source_sector_ids.mapped('name'))
                if cost.source_unit_ids:
                    sources.extend(cost.source_unit_ids.mapped('name'))
                if cost.source_house_ids:
                    sources.extend(cost.source_house_ids.mapped('name'))
                
                if sources:
                    cost.source_display = ', '.join(sources[:5])  # Show first 5
                    if len(sources) > 5:
                        cost.source_display += f' (+{len(sources) - 5})'
                else:
                    cost.source_display = '-'

    @api.depends('cost_type', 'project_id', 'payment_account_id', 'indirect_cost_account_id', 
                 'direct_cost_account_id', 'amount', 'date', 'source_display')
    def _compute_ledger_description(self):
        """Auto-generate ledger description for costs"""
        for cost in self:
            if cost.project_id:
                parts = []
                if cost.cost_type == 'indirect':
                    parts.append('تكلفة غير مباشرة')
                    if cost.indirect_cost_account_id:
                        parts.append(f'- {cost.indirect_cost_account_id.name}')
                else:
                    parts.append('تكلفة مباشرة')
                    if cost.direct_cost_account_id:
                        parts.append(f'- {cost.direct_cost_account_id.name}')
                    if cost.source_display and cost.source_display != '-':
                        parts.append(f'- {cost.source_display}')
                parts.append(f'- مشروع: {cost.project_id.name}')
                if cost.farm_id:
                    parts.append(f'- مزرعة: {cost.farm_id.name}')
                if cost.payment_account_id:
                    parts.append(f'- من: {cost.payment_account_id.name}')
                cost.ledger_description = ' '.join(parts)
            else:
                cost.ledger_description = ''

    @api.depends('allocation_line_ids', 'allocation_line_ids.allocated_amount')
    def _compute_allocated_amount(self):
        for cost in self:
            cost.allocated_amount = sum(cost.allocation_line_ids.mapped('allocated_amount'))
            cost.house_count = len(cost.allocation_line_ids)

    @api.onchange('cost_type')
    def _onchange_cost_type(self):
        """Clear source fields when switching cost types"""
        if self.cost_type == 'indirect':
            self.source_sector_ids = [(5, 0, 0)]  # Clear many2many
            self.source_unit_ids = [(5, 0, 0)]
            self.source_house_ids = [(5, 0, 0)]
            self.direct_cost_account_id = False
        else:
            self.indirect_cost_account_id = False
        # Recompute allocations preview
        self._onchange_recompute_allocations()

    @api.onchange('source_sector_ids', 'source_unit_ids', 'source_house_ids', 'amount', 'project_id')
    def _onchange_recompute_allocations(self):
        """Recompute allocations when sources or amount changes (preview in UI)"""
        if not self.project_id or not self.amount:
            return
        
        # Get target houses
        target_houses = self._get_target_houses_preview()
        
        if not target_houses:
            self.allocation_line_ids = [(5, 0, 0)]  # Clear
            return
        
        # Calculate total area
        total_area = sum(target_houses.mapped('area'))
        
        # Create allocation lines (preview)
        allocation_vals = []
        if total_area <= 0:
            house_count = len(target_houses)
            for house in target_houses:
                allocation_vals.append((0, 0, {
                    'house_id': house.id,
                    'allocated_amount': self.amount / house_count,
                    'percentage': 100.0 / house_count,
                }))
        else:
            for house in target_houses:
                percentage = (house.area / total_area) * 100
                allocated_amount = (house.area / total_area) * self.amount
                allocation_vals.append((0, 0, {
                    'house_id': house.id,
                    'allocated_amount': allocated_amount,
                    'percentage': percentage,
                }))
        
        self.allocation_line_ids = [(5, 0, 0)] + allocation_vals

    def _get_target_houses_preview(self):
        """Get target houses for preview (works with unsaved records)"""
        if not self.project_id:
            return self.env['farm.house']
        
        # Get all houses assigned to the project
        project_houses = self.project_id.house_assignment_ids.mapped('house_id')
        
        if self.cost_type == 'indirect':
            return project_houses
        
        # Direct cost: Collect houses from all selected sources
        target_houses = self.env['farm.house']
        
        # Add directly selected houses
        if self.source_house_ids:
            target_houses |= self.source_house_ids
        
        # Add houses from selected units
        if self.source_unit_ids:
            for unit in self.source_unit_ids:
                target_houses |= unit.house_ids
        
        # Add houses from selected sectors (get all houses from all units in sector)
        if self.source_sector_ids:
            for sector in self.source_sector_ids:
                for unit in sector.unit_ids:
                    target_houses |= unit.house_ids
        
        # Filter to only include houses that are assigned to the project
        target_houses = target_houses & project_houses
        
        return target_houses

    @api.constrains('cost_type', 'source_sector_ids', 'source_unit_ids', 'source_house_ids', 
                    'direct_cost_account_id', 'indirect_cost_account_id', 'payment_account_id', 'order_id', 'harvest_entry_id')
    def _check_cost_requirements(self):
        for cost in self:
            # Skip validation for harvest-created costs (auto-created from harvests)
            if cost.harvest_entry_id:
                continue
            
            # Payment account is required only for non-order and non-harvest costs
            if not cost.order_id and not cost.payment_account_id:
                raise ValidationError(_('يجب تحديد حساب الدفع (من) للتكاليف غير المرتبطة بطلبات المنتجات'))
            
            if cost.cost_type == 'direct':
                # For direct costs, at least one source must be selected
                if not cost.source_sector_ids and not cost.source_unit_ids and not cost.source_house_ids:
                    raise ValidationError(_('يجب تحديد مصدر واحد على الأقل للتكاليف المباشرة (قطاع، وحدة، أو بيت)'))
                if not cost.direct_cost_account_id:
                    raise ValidationError(_('يجب تحديد حساب التكلفة للتكاليف المباشرة'))
            elif cost.cost_type == 'indirect':
                if not cost.indirect_cost_account_id:
                    raise ValidationError(_('يجب تحديد حساب التكلفة للتكاليف غير المباشرة'))

    def _compute_allocations(self):
        """Compute cost allocation to houses based on area"""
        self.ensure_one()
        
        # Clear existing allocations
        self.allocation_line_ids.unlink()
        
        # Get target houses
        target_houses = self._get_target_houses()
        
        if not target_houses:
            return
        
        # Calculate total area
        total_area = sum(target_houses.mapped('area'))
        
        if total_area <= 0:
            # Equal distribution if no area
            house_count = len(target_houses)
            for house in target_houses:
                self.env['farm.cost.allocation'].create({
                    'cost_id': self.id,
                    'house_id': house.id,
                    'allocated_amount': self.amount / house_count,
                    'percentage': 100.0 / house_count,
                })
        else:
            # Distribution by area
            for house in target_houses:
                percentage = (house.area / total_area) * 100
                allocated_amount = (house.area / total_area) * self.amount
                self.env['farm.cost.allocation'].create({
                    'cost_id': self.id,
                    'house_id': house.id,
                    'allocated_amount': allocated_amount,
                    'percentage': percentage,
                })

    def _get_target_houses(self):
        """Get houses that should receive cost allocation based on source selection"""
        self.ensure_one()
        
        # Get all houses assigned to the project
        project_houses = self.project_id.house_assignment_ids.mapped('house_id')
        
        if self.cost_type == 'indirect':
            # Indirect cost: all houses in project
            return project_houses
        
        # Direct cost: Collect houses from all selected sources
        target_houses = self.env['farm.house']
        
        # Add directly selected houses
        if self.source_house_ids:
            target_houses |= self.source_house_ids
        
        # Add houses from selected units
        if self.source_unit_ids:
            for unit in self.source_unit_ids:
                target_houses |= unit.house_ids
        
        # Add houses from selected sectors
        if self.source_sector_ids:
            for sector in self.source_sector_ids:
                for unit in sector.unit_ids:
                    target_houses |= unit.house_ids
        
        # Filter to only include houses that are assigned to the project
        target_houses = target_houses & project_houses
        
        return target_houses

    def action_view_allocations(self):
        """View cost allocations"""
        self.ensure_one()
        return {
            'name': _('توزيع التكاليف'),
            'type': 'ir.actions.act_window',
            'res_model': 'farm.cost.allocation',
            'view_mode': 'tree,form',
            'domain': [('cost_id', '=', self.id)],
            'context': {'default_cost_id': self.id},
        }


class FarmCostAllocation(models.Model):
    _name = 'farm.cost.allocation'
    _description = 'توزيع تكاليف المشروع'
    _order = 'cost_id desc, house_id'

    cost_id = fields.Many2one(
        'farm.project.cost',
        string='التكلفة',
        required=True,
        ondelete='cascade',
    )
    project_id = fields.Many2one(
        related='cost_id.project_id',
        string='المشروع',
        store=True,
    )
    farm_id = fields.Many2one(
        related='cost_id.farm_id',
        string='المزرعة',
        store=True,
    )
    cost_type = fields.Selection(
        related='cost_id.cost_type',
        string='نوع التكلفة',
        store=True,
    )
    house_id = fields.Many2one(
        'farm.house',
        string='البيت',
        required=True,
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
    house_area = fields.Float(
        related='house_id.area',
        string='المساحة (م²)',
        store=True,
    )
    allocated_amount = fields.Monetary(
        string='المبلغ المخصص',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='cost_id.currency_id',
        string='العملة',
    )
    percentage = fields.Float(
        string='النسبة (%)',
        digits=(16, 2),
    )
    cost_date = fields.Date(
        related='cost_id.date',
        string='تاريخ التكلفة',
        store=True,
    )
    cost_state = fields.Selection(
        related='cost_id.state',
        string='حالة التكلفة',
        store=True,
    )
    
    # Computed field for cost per m²
    cost_per_sqm = fields.Float(
        string='التكلفة/م²',
        compute='_compute_cost_per_sqm',
        digits=(16, 2),
    )

    @api.depends('allocated_amount', 'house_area')
    def _compute_cost_per_sqm(self):
        for allocation in self:
            if allocation.house_area > 0:
                allocation.cost_per_sqm = allocation.allocated_amount / allocation.house_area
            else:
                allocation.cost_per_sqm = 0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Trigger recalculation of harvest costs when allocations are created
        records._trigger_harvest_recalculation()
        return records

    def write(self, vals):
        result = super().write(vals)
        # Trigger recalculation if amount changed
        if 'allocated_amount' in vals:
            self._trigger_harvest_recalculation()
        return result

    def _trigger_harvest_recalculation(self):
        """Trigger recalculation of harvest entries for affected project houses"""
        for allocation in self:
            if allocation.cost_state != 'posted':
                continue
            
            # Find project house assignments for this house in this project
            project_houses = self.env['farm.project.house'].search([
                ('project_id', '=', allocation.project_id.id),
                ('house_id', '=', allocation.house_id.id),
            ])
            
            # Recalculate all harvest entries for these project houses
            for ph in project_houses:
                entries = self.env['farm.harvest.entry'].search([
                    ('project_house_id', '=', ph.id),
                ], order='date, id')
                for entry in entries:
                    entry._calculate_cost_allocation()
