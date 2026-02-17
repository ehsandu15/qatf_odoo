# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FarmProductOrder(models.Model):
    _name = 'farm.product.order'
    _description = 'طلب منتجات المزرعة'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='رقم الطلب',
        readonly=True,
        copy=False,
        default='جديد',
    )
    
    state = fields.Selection([
        ('draft', 'مسودة'),
        ('owner_approval', 'موافقة مالك المزرعة'),
        ('inventory_approval', 'موافقة المخزون'),
        ('accounting_approval', 'موافقة المحاسبة'),
        ('done', 'منتهي'),
        ('cancelled', 'ملغي'),
    ], string='الحالة', default='draft', required=True, tracking=True, copy=False)
    
    is_direct_order = fields.Boolean(
        string='طلب مباشر',
        default=False,
        tracking=True,
        help='الطلبات المباشرة تتخطى موافقة مالك المزرعة وتتطلب إنشاء قيد محاسبي يدوي',
    )
    
    project_id = fields.Many2one(
        'farm.project',
        string='المشروع',
        required=True,
        tracking=True,
        ondelete='restrict',
        domain="[('status', '=', 'in_progress')]",
        help='اختر مشروعاً قيد التنفيذ',
    )
    
    farm_id = fields.Many2one(
        'farm.farm',
        string='المزرعة',
        related='project_id.farm_id',
        store=True,
        readonly=True,
    )
    
    requester_id = fields.Many2one(
        'res.users',
        string='مقدم الطلب',
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
        readonly=True,
    )
    
    request_date = fields.Date(
        string='تاريخ الطلب',
        default=fields.Date.today,
        required=True,
        tracking=True,
    )
    
    notes = fields.Text(
        string='ملاحظات',
    )
    
    # Target locations (sectors/units/houses)
    target_sector_ids = fields.Many2many(
        'farm.sector',
        'farm_order_sector_rel',
        'order_id',
        'sector_id',
        string='القطاعات المستهدفة',
        tracking=True,
    )
    target_unit_ids = fields.Many2many(
        'farm.unit',
        'farm_order_unit_rel',
        'order_id',
        'unit_id',
        string='الوحدات المستهدفة',
        tracking=True,
    )
    target_house_ids = fields.Many2many(
        'farm.house',
        'farm_order_house_rel',
        'order_id',
        'house_id',
        string='البيوت المستهدفة',
        tracking=True,
    )
    
    # Computed fields for available sources (based on farm)
    available_sector_ids = fields.Many2many(
        'farm.sector',
        compute='_compute_available_sources',
        string='القطاعات المتاحة',
    )
    available_unit_ids = fields.Many2many(
        'farm.unit',
        compute='_compute_available_sources',
        string='الوحدات المتاحة',
    )
    available_house_ids = fields.Many2many(
        'farm.house',
        compute='_compute_available_sources',
        string='البيوت المتاحة',
    )
    
    # Order lines
    line_ids = fields.One2many(
        'farm.product.order.line',
        'order_id',
        string='بنود الطلب',
    )
    
    # Related records
    picking_ids = fields.One2many(
        'stock.picking',
        'farm_order_id',
        string='عمليات النقل',
        readonly=True,
    )
    stock_move_ids = fields.One2many(
        'stock.move',
        'farm_order_id',
        string='حركات المخزون',
        readonly=True,
    )
    move_id = fields.Many2one(
        'account.move',
        string='القيد المحاسبي',
        readonly=True,
        copy=False,
    )
    cost_ids = fields.One2many(
        'farm.project.cost',
        'order_id',
        string='التكاليف',
        readonly=True,
    )
    
    # Computed totals
    company_id = fields.Many2one(
        'res.company',
        string='الشركة',
        related='project_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='العملة',
        related='company_id.currency_id',
    )
    total_amount = fields.Monetary(
        string='إجمالي المبلغ',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    line_count = fields.Integer(
        string='عدد البنود',
        compute='_compute_totals',
        store=True,
    )
    stock_move_count = fields.Integer(
        string='عدد حركات المخزون',
        compute='_compute_move_counts',
    )
    picking_count = fields.Integer(
        string='عدد عمليات النقل',
        compute='_compute_move_counts',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'جديد') == 'جديد':
                vals['name'] = self.env['ir.sequence'].next_by_code('farm.product.order') or 'جديد'
        return super().create(vals_list)

    @api.depends('project_id', 'project_id.house_assignment_ids')
    def _compute_available_sources(self):
        """Compute available sectors, units, and houses based on project's assigned houses"""
        for order in self:
            if order.project_id:
                # Get houses assigned to this project
                project_houses = order.project_id.house_assignment_ids.mapped('house_id')
                order.available_house_ids = project_houses
                
                # Get units and sectors from these houses
                units = project_houses.mapped('unit_id')
                order.available_unit_ids = units
                
                sectors = units.mapped('sector_id')
                order.available_sector_ids = sectors
            else:
                order.available_sector_ids = self.env['farm.sector']
                order.available_unit_ids = self.env['farm.unit']
                order.available_house_ids = self.env['farm.house']

    @api.depends('line_ids', 'line_ids.subtotal')
    def _compute_totals(self):
        for order in self:
            order.total_amount = sum(order.line_ids.mapped('subtotal'))
            order.line_count = len(order.line_ids)

    @api.depends('stock_move_ids')
    def _compute_move_counts(self):
        for order in self:
            order.stock_move_count = len(order.stock_move_ids)
            order.picking_count = len(order.picking_ids)

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """Clear target selections when project changes"""
        self.target_sector_ids = [(5, 0, 0)]
        self.target_unit_ids = [(5, 0, 0)]
        self.target_house_ids = [(5, 0, 0)]

    def _get_target_houses(self):
        """Get all target houses from sector/unit/house selections"""
        self.ensure_one()
        target_houses = self.env['farm.house']
        
        # Add directly selected houses
        if self.target_house_ids:
            target_houses |= self.target_house_ids
        
        # Add houses from selected units
        if self.target_unit_ids:
            for unit in self.target_unit_ids:
                target_houses |= unit.house_ids
        
        # Add houses from selected sectors
        if self.target_sector_ids:
            for sector in self.target_sector_ids:
                for unit in sector.unit_ids:
                    target_houses |= unit.house_ids
        
        return target_houses

    # ========== WORKFLOW ACTIONS ==========
    
    def action_submit(self):
        """Submit order for approval (direct orders skip owner approval)"""
        for order in self:
            if order.state != 'draft':
                raise UserError(_('يمكن إرسال الطلبات في حالة المسودة فقط'))
            if not order.line_ids:
                raise UserError(_('يجب إضافة بند واحد على الأقل للطلب'))
            if not order.target_sector_ids and not order.target_unit_ids and not order.target_house_ids:
                raise UserError(_('يجب تحديد قطاع أو وحدة أو بيت واحد على الأقل'))
            
            # Direct orders skip owner approval and go directly to inventory
            if order.is_direct_order:
                order.state = 'inventory_approval'
                order.message_post(body=_('طلب مباشر - تم إرساله مباشرة لموافقة المخزون'))
            else:
                order.state = 'owner_approval'
                order.message_post(body=_('تم إرسال الطلب لموافقة مالك المزرعة'))
        return True

    def action_owner_approve(self):
        """Farm owner approves - move to inventory approval"""
        for order in self:
            if order.state != 'owner_approval':
                raise UserError(_('الطلب ليس في حالة انتظار موافقة المالك'))
            
            order.state = 'inventory_approval'
            order.message_post(body=_('وافق مالك المزرعة على الطلب - في انتظار موافقة المخزون'))
        return True

    def action_inventory_approve(self):
        """Inventory approves - create stock moves and move to accounting"""
        for order in self:
            if order.state != 'inventory_approval':
                raise UserError(_('الطلب ليس في حالة انتظار موافقة المخزون'))
            
            # Check availability
            for line in order.line_ids:
                if not line.is_available:
                    raise UserError(_('المنتج "%s" غير متوفر بالكمية المطلوبة (%s). الكمية المتاحة: %s') % (
                        line.product_id.display_name, line.quantity, line.available_qty
                    ))
            
            # Create stock moves
            order._create_stock_moves()
            
            order.state = 'accounting_approval'
            order.message_post(body=_('وافق المخزون على الطلب وتم إنشاء حركات المخزون - في انتظار موافقة المحاسبة'))
        return True

    def action_accounting_approve(self):
        """Accounting approves - create journal entry and costs, then done"""
        for order in self:
            if order.state != 'accounting_approval':
                raise UserError(_('الطلب ليس في حالة انتظار موافقة المحاسبة'))
            
            # For direct orders, require manual journal entry
            if order.is_direct_order:
                if not order.move_id:
                    raise UserError(_('يجب إنشاء قيد محاسبي قبل الموافقة على الطلب المباشر'))
                # Skip auto journal creation, use the manually linked one
                order.message_post(body=_('طلب مباشر - تم استخدام القيد المحاسبي المرتبط يدوياً'))
            else:
                # Normal order: Create accounting entry automatically
                order._create_accounting_entry()
            
            # Create farm costs
            order._create_farm_costs()
            
            order.state = 'done'
            order.message_post(body=_('وافقت المحاسبة على الطلب وتم إكمال الطلب'))
        return True

    def action_cancel(self):
        """Cancel the order"""
        for order in self:
            if order.state == 'done':
                raise UserError(_('لا يمكن إلغاء الطلبات المكتملة'))
            
            # Cancel stock moves if any
            if order.stock_move_ids:
                for move in order.stock_move_ids:
                    if move.state == 'done':
                        move._action_cancel()
                    elif move.state != 'cancel':
                        move._action_cancel()
            
            order.state = 'cancelled'
            order.message_post(body=_('تم إلغاء الطلب'))
        return True

    def action_reset_to_draft(self):
        """Reset cancelled order to draft"""
        for order in self:
            if order.state != 'cancelled':
                raise UserError(_('يمكن إعادة الطلبات الملغاة للمسودة فقط'))
            
            order.state = 'draft'
            order.message_post(body=_('تم إعادة الطلب للمسودة'))
        return True

    # ========== STOCK MOVE CREATION ==========
    
    def _create_stock_moves(self):
        """Create stock transfer (picking) with stock moves for order lines"""
        self.ensure_one()
        
        # Get destination location from settings
        dest_location_id = self.env['ir.config_parameter'].sudo().get_param(
            'farm_management.order_dest_location_id'
        )
        if dest_location_id:
            dest_location = self.env['stock.location'].browse(int(dest_location_id))
            if not dest_location.exists():
                dest_location = False
        else:
            dest_location = False
        
        if not dest_location:
            # Default: Company's main stock location
            warehouse = self.env['stock.warehouse'].search([
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if warehouse:
                dest_location = warehouse.lot_stock_id
        
        if not dest_location:
            raise UserError(_('لم يتم تكوين موقع وجهة الطلبات. يرجى تكوينه في الإعدادات.'))
        
        # Get default source location (main stock)
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        default_source_location = warehouse.lot_stock_id if warehouse else False
        
        if not default_source_location:
            raise UserError(_('لم يتم العثور على موقع المخزون الرئيسي'))
        
        # Find appropriate picking type (internal transfer or outgoing)
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        
        if not picking_type:
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'outgoing'),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
        
        if not picking_type:
            raise UserError(_('لم يتم العثور على نوع عملية نقل مناسب'))
        
        # Create picking (transfer)
        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': default_source_location.id,
            'location_dest_id': dest_location.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'farm_order_id': self.id,
        }
        picking = self.env['stock.picking'].create(picking_vals)
        
        # Create stock moves for each line inside picking
        for line in self.line_ids:
            # Get source location (product's default or main stock)
            source_location = line.product_id.property_stock_inventory
            if not source_location:
                source_location = default_source_location
            
            move_vals = {
                'name': _('طلب منتج: %s - %s') % (self.name, line.product_id.display_name),
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'product_uom': line.uom_id.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
                'picking_id': picking.id,
                'origin': self.name,
                'company_id': self.company_id.id,
                'farm_order_id': self.id,
            }
            self.env['stock.move'].create(move_vals)
        
        # Confirm and assign the picking
        picking.action_confirm()
        
        try:
            picking.action_assign()
        except Exception:
            pass  # Assignment may fail for some locations
        
        # Set quantities on move lines
        for move in picking.move_ids:
            line = self.line_ids.filtered(lambda l: l.product_id == move.product_id)
            qty = line[0].quantity if line else move.product_uom_qty
            
            if move.move_line_ids:
                move.move_line_ids.write({'quantity': qty})
            else:
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'quantity': qty,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'company_id': self.company_id.id,
                })
        
        # Validate the picking
        picking.button_validate()
        
        self.message_post(body=_('تم إنشاء عملية نقل: %s') % picking.name)

    # ========== ACCOUNTING ENTRY CREATION ==========
    
    def _create_accounting_entry(self):
        """Create journal entry for the order"""
        self.ensure_one()
        
        # Get general journal
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        
        if not journal:
            raise UserError(_('لم يتم العثور على دفتر يومية عام'))
        
        move_lines = []
        
        for line in self.line_ids:
            # Get accounts from product, fall back to category defaults
            source_account = line.product_id.product_tmpl_id.order_account_source or line.product_id.categ_id.default_order_account_source
            dest_account = line.product_id.product_tmpl_id.order_account_destination or line.product_id.categ_id.default_order_account_destination
            
            if not source_account or not dest_account:
                raise UserError(_('يجب تحديد حسابات الطلب للمنتج %s (أو تحديد حسابات افتراضية لتصنيف المنتج)') % line.product_id.display_name)
            
            # Debit line (source account)
            move_lines.append((0, 0, {
                'name': _('%s - %s') % (self.name, line.product_id.display_name),
                'account_id': source_account.id,
                'debit': line.subtotal,
                'credit': 0,
            }))
            
            # Credit line (destination account)
            move_lines.append((0, 0, {
                'name': _('%s - %s') % (self.name, line.product_id.display_name),
                'account_id': dest_account.id,
                'debit': 0,
                'credit': line.subtotal,
            }))
        
        if move_lines:
            move_vals = {
                'journal_id': journal.id,
                'date': fields.Date.today(),
                'ref': self.name,
                'narration': _('طلب منتجات - %s') % self.name,
                'company_id': self.company_id.id,
                'line_ids': move_lines,
            }
            
            move = self.env['account.move'].create(move_vals)
            move.action_post()
            self.move_id = move

    # ========== FARM COST CREATION ==========
    
    def _create_farm_costs(self):
        """Create farm costs for the order, grouped by order_account_source"""
        self.ensure_one()
        
        target_houses = self._get_target_houses()
        if not target_houses:
            return
        
        # Use the order's project directly (since we now select project, not farm)
        project = self.project_id
        
        if not project or project.status != 'in_progress':
            self.message_post(body=_('المشروع غير قيد التنفيذ. لم يتم إنشاء تكاليف.'))
            return
        
        # Group order lines by order_account_source (fall back to category default)
        account_groups = {}
        for line in self.line_ids:
            source_account = line.product_id.product_tmpl_id.order_account_source or line.product_id.categ_id.default_order_account_source
            if source_account:
                if source_account.id not in account_groups:
                    account_groups[source_account.id] = {
                        'account': source_account,
                        'amount': 0,
                    }
                account_groups[source_account.id]['amount'] += line.subtotal
        
        if not account_groups:
            self.message_post(body=_('لم يتم العثور على حسابات مصدر للمنتجات. لم يتم إنشاء تكاليف.'))
            return
        
        # Create one cost per unique source account
        created_costs = []
        for account_data in account_groups.values():
            cost_vals = {
                'project_id': project.id,
                'cost_type': 'direct',
                'amount': account_data['amount'],
                'date': fields.Date.today(),
                'description': _('طلب منتجات: %s - حساب: %s') % (self.name, account_data['account'].name),
                'direct_cost_account_id': account_data['account'].id,
                'source_house_ids': [(6, 0, target_houses.ids)],
                'order_id': self.id,
            }
            
            cost = self.env['farm.project.cost'].create(cost_vals)
            cost.action_post()
            created_costs.append(cost)
        
        if created_costs:
            self.message_post(body=_('تم إنشاء %s تكلفة/تكاليف مباشرة') % len(created_costs))

    # ========== SMART BUTTON ACTIONS ==========
    
    def action_view_stock_moves(self):
        """View related stock moves"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('حركات المخزون'),
            'res_model': 'stock.move',
            'view_mode': 'tree,form',
            'domain': [('farm_order_id', '=', self.id)],
        }

    def action_view_pickings(self):
        """View related pickings/transfers"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('عمليات النقل'),
            'res_model': 'stock.picking',
            'view_mode': 'tree,form',
            'domain': [('farm_order_id', '=', self.id)],
        }

    def action_view_accounting_entry(self):
        """View related accounting entry"""
        self.ensure_one()
        if self.move_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('القيد المحاسبي'),
                'res_model': 'account.move',
                'res_id': self.move_id.id,
                'view_mode': 'form',
            }

    def action_view_costs(self):
        """View related costs"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('التكاليف'),
            'res_model': 'farm.project.cost',
            'view_mode': 'tree,form',
            'domain': [('order_id', '=', self.id)],
        }


class FarmProductOrderLine(models.Model):
    _name = 'farm.product.order.line'
    _description = 'بند طلب منتجات المزرعة'
    _order = 'order_id, id'

    order_id = fields.Many2one(
        'farm.product.order',
        string='الطلب',
        required=True,
        ondelete='cascade',
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='المنتج',
        required=True,
        domain="[('can_be_ordered', '=', True)]",
    )
    
    quantity = fields.Float(
        string='الكمية',
        required=True,
        default=1.0,
    )
    
    uom_id = fields.Many2one(
        'uom.uom',
        string='وحدة القياس',
        related='product_id.uom_id',
        readonly=True,
    )
    
    available_qty = fields.Float(
        string='الكمية المتاحة',
        compute='_compute_availability',
        store=False,
    )
    
    is_available = fields.Boolean(
        string='متاح',
        compute='_compute_availability',
        store=False,
    )
    
    justification = fields.Text(
        string='المبرر',
        required=True,
        help='يجب إدخال مبرر للطلب (10 حروف على الأقل)',
    )
    
    unit_price = fields.Float(
        string='سعر الوحدة',
        related='product_id.standard_price',
        readonly=True,
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        related='order_id.currency_id',
    )
    
    subtotal = fields.Monetary(
        string='المجموع الفرعي',
        compute='_compute_subtotal',
        store=True,
        currency_field='currency_id',
    )
    
    order_state = fields.Selection(
        related='order_id.state',
        string='حالة الطلب',
    )

    @api.depends('product_id')
    def _compute_availability(self):
        """Compute available quantity for product"""
        for line in self:
            if line.product_id:
                # Get available quantity from stock
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id.usage', '=', 'internal'),
                ])
                line.available_qty = sum(quants.mapped('quantity'))
                line.is_available = line.available_qty >= line.quantity
            else:
                line.available_qty = 0
                line.is_available = False

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price

    @api.constrains('justification')
    def _check_justification(self):
        for line in self:
            if line.justification and len(line.justification.strip()) < 10:
                raise ValidationError(_('يجب أن يكون المبرر 10 حروف على الأقل للبند: %s') % line.product_id.display_name)

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_('يجب أن تكون الكمية أكبر من صفر'))

