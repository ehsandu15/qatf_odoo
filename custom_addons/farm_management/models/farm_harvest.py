# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FarmHarvestEntry(models.Model):
    _name = 'farm.harvest.entry'
    _description = 'سجل الحصاد'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='المرجع',
        readonly=True,
        copy=False,
        default='جديد',
    )
    
    project_house_id = fields.Many2one(
        'farm.project.house',
        string='تخصيص البيت',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    
    # Stock transfer/picking link
    picking_id = fields.Many2one(
        'stock.picking',
        string='عملية النقل',
        readonly=True,
        copy=False,
    )
    
    # Stock move link (derived from picking)
    stock_move_id = fields.Many2one(
        'stock.move',
        string='حركة المخزون',
        readonly=True,
        copy=False,
    )
    stock_move_line_ids = fields.One2many(
        related='stock_move_id.move_line_ids',
        string='تفاصيل الحركة',
        readonly=True,
    )
    
    # Related fields for easy access
    project_id = fields.Many2one(
        related='project_house_id.project_id',
        string='المشروع',
        store=True,
    )
    house_id = fields.Many2one(
        related='project_house_id.house_id',
        string='البيت',
        store=True,
    )
    product_id = fields.Many2one(
        related='project_house_id.product_id',
        string='المنتج',
        store=True,
    )
    farm_id = fields.Many2one(
        related='project_house_id.farm_id',
        string='المزرعة',
        store=True,
    )
    sector_id = fields.Many2one(
        related='project_house_id.sector_id',
        string='القطاع',
        store=True,
    )
    unit_id = fields.Many2one(
        related='project_house_id.unit_id',
        string='الوحدة',
        store=True,
    )
    expected_qty = fields.Float(
        related='project_house_id.expected_qty',
        string='الكمية المتوقعة',
    )
    uom_id = fields.Many2one(
        related='project_house_id.uom_id',
        string='وحدة القياس',
    )
    company_id = fields.Many2one(
        related='project_house_id.company_id',
        string='الشركة',
        store=True,
    )
    currency_id = fields.Many2one(
        related='project_house_id.currency_id',
        string='العملة',
    )
    
    # Harvest data
    date = fields.Date(
        string='تاريخ الحصاد',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    quantity = fields.Float(
        string='الكمية المحصودة',
        required=True,
        tracking=True,
    )
    notes = fields.Text(
        string='ملاحظات',
    )
    
    state = fields.Selection([
        ('done', 'منتهي'),
        ('cancelled', 'ملغي'),
    ], string='الحالة', default='done', required=True, tracking=True, copy=False)
    
    # Cost allocation fields
    remaining_cost_before = fields.Monetary(
        string='التكلفة المتبقية قبل الحصاد',
        currency_field='currency_id',
        readonly=True,
        help='التكلفة المتبقية في البيت قبل هذا الحصاد',
    )
    allocated_cost = fields.Monetary(
        string='التكلفة المخصصة',
        currency_field='currency_id',
        readonly=True,
        help='التكلفة المخصصة لهذا الحصاد',
    )
    unit_cost = fields.Monetary(
        string='تكلفة الوحدة',
        currency_field='currency_id',
        compute='_compute_unit_cost',
        store=True,
        help='تكلفة الوحدة الواحدة من المحصول',
    )
    
    # Progress tracking
    entry_progress = fields.Float(
        string='نسبة هذا الحصاد (%)',
        compute='_compute_progress',
        store=True,
        help='نسبة هذا الحصاد من الكمية المتوقعة',
    )
    cumulative_harvested = fields.Float(
        string='إجمالي المحصود التراكمي',
        compute='_compute_cumulative',
        store=True,
    )
    cumulative_progress = fields.Float(
        string='التقدم التراكمي (%)',
        compute='_compute_cumulative',
        store=True,
    )
    cumulative_allocated = fields.Monetary(
        string='التكلفة المخصصة التراكمية',
        compute='_compute_cumulative',
        store=True,
        currency_field='currency_id',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'جديد') == 'جديد':
                vals['name'] = self.env['ir.sequence'].next_by_code('farm.harvest.entry') or 'جديد'
        
        records = super().create(vals_list)
        
        # Calculate cost allocation, create stock move and harvest cost for each new entry
        for record in records:
            record._calculate_cost_allocation()
            record._create_stock_move()
            record._create_harvest_cost()
        
        return records

    def write(self, vals):
        result = super().write(vals)
        
        # Recalculate if quantity changed
        if 'quantity' in vals:
            for record in self:
                record._calculate_cost_allocation()
                # Recalculate subsequent entries
                record._recalculate_subsequent_entries()
                # Update stock move quantity
                record._update_stock_move()
        
        return result

    def unlink(self):
        # Cancel pickings first
        pickings = self.mapped('picking_id')
        if pickings:
            for picking in pickings:
                if picking.state == 'done':
                    # Force cancel done pickings
                    for move in picking.move_ids:
                        move.write({'state': 'cancel'})
                    picking.write({'state': 'cancel'})
                elif picking.state != 'cancel':
                    picking.action_cancel()
        
        # Store project_house_ids before deletion to recalculate
        project_houses = self.mapped('project_house_id')
        result = super().unlink()
        
        # Recalculate remaining entries for affected project houses
        for ph in project_houses:
            entries = self.search([('project_house_id', '=', ph.id)], order='date, id')
            for entry in entries:
                entry._calculate_cost_allocation()
        
        return result

    @api.depends('allocated_cost', 'quantity')
    def _compute_unit_cost(self):
        for entry in self:
            if entry.quantity:
                entry.unit_cost = entry.allocated_cost / entry.quantity
            else:
                entry.unit_cost = 0

    @api.depends('quantity', 'expected_qty')
    def _compute_progress(self):
        for entry in self:
            if entry.expected_qty:
                entry.entry_progress = (entry.quantity / entry.expected_qty) * 100
            else:
                entry.entry_progress = 0

    @api.depends('project_house_id', 'date', 'quantity', 'allocated_cost')
    def _compute_cumulative(self):
        for entry in self:
            # Skip if record is not saved yet (NewId)
            if not entry.id or isinstance(entry.id, models.NewId):
                entry.cumulative_harvested = entry.quantity or 0
                entry.cumulative_allocated = entry.allocated_cost or 0
                if entry.expected_qty:
                    entry.cumulative_progress = (entry.cumulative_harvested / entry.expected_qty) * 100
                else:
                    entry.cumulative_progress = 0
                continue
            
            # Get all entries up to and including this one
            previous_entries = self.search([
                ('project_house_id', '=', entry.project_house_id.id),
                '|',
                ('date', '<', entry.date),
                '&',
                ('date', '=', entry.date),
                ('id', '<=', entry.id),
            ])
            
            entry.cumulative_harvested = sum(previous_entries.mapped('quantity'))
            entry.cumulative_allocated = sum(previous_entries.mapped('allocated_cost'))
            
            if entry.expected_qty:
                entry.cumulative_progress = (entry.cumulative_harvested / entry.expected_qty) * 100
            else:
                entry.cumulative_progress = 0

    def _calculate_cost_allocation(self):
        """
        Calculate cost allocation for this harvest entry.
        Formula: allocated_cost = remaining_cost * (quantity / expected_qty)
        """
        self.ensure_one()
        
        if not self.expected_qty:
            self.remaining_cost_before = 0
            self.allocated_cost = 0
            return
        
        # Get total house cost from cost allocations
        allocations = self.env['farm.cost.allocation'].search([
            ('project_id', '=', self.project_id.id),
            ('house_id', '=', self.house_id.id),
            ('cost_state', '=', 'posted'),
        ])
        total_house_cost = sum(allocations.mapped('allocated_amount'))
        
        # Get previously allocated cost (entries before this one)
        previous_entries = self.search([
            ('project_house_id', '=', self.project_house_id.id),
            ('id', '!=', self.id),
            '|',
            ('date', '<', self.date),
            '&',
            ('date', '=', self.date),
            ('id', '<', self.id),
        ])
        previous_allocated = sum(previous_entries.mapped('allocated_cost'))
        
        # Calculate remaining cost before this entry
        remaining_cost = total_house_cost - previous_allocated
        self.remaining_cost_before = remaining_cost
        
        # Calculate allocation for this entry
        # allocated_cost = remaining_cost * (quantity / expected_qty)
        entry_ratio = self.quantity / self.expected_qty
        self.allocated_cost = remaining_cost * entry_ratio

    def _recalculate_subsequent_entries(self):
        """Recalculate all entries after this one"""
        self.ensure_one()
        
        subsequent_entries = self.search([
            ('project_house_id', '=', self.project_house_id.id),
            '|',
            ('date', '>', self.date),
            '&',
            ('date', '=', self.date),
            ('id', '>', self.id),
        ], order='date, id')
        
        for entry in subsequent_entries:
            entry._calculate_cost_allocation()

    @api.constrains('quantity')
    def _check_quantity(self):
        for entry in self:
            if entry.quantity <= 0:
                raise ValidationError(_('يجب أن تكون الكمية المحصودة أكبر من صفر'))

    @api.constrains('project_house_id')
    def _check_product_defined(self):
        for entry in self:
            if not entry.project_house_id.product_id:
                raise ValidationError(_('يجب تحديد المنتج في تخصيص البيت قبل تسجيل الحصاد'))
            if not entry.project_house_id.expected_qty:
                raise ValidationError(_('يجب تحديد الكمية المتوقعة في تخصيص البيت قبل تسجيل الحصاد'))

    def _get_harvest_locations(self):
        """Get source and destination locations for harvest stock moves"""
        self.ensure_one()
        
        ICP = self.env['ir.config_parameter'].sudo()
        company = self.company_id or self.env.company
        
        # Get configured source location or default to Production
        source_location_id = ICP.get_param('farm_management.harvest_source_location_id')
        if source_location_id:
            source_location = self.env['stock.location'].browse(int(source_location_id))
            if not source_location.exists():
                source_location = False
        else:
            source_location = False
        
        if not source_location:
            # Default: Virtual Production location
            source_location = self.env.ref('stock.location_production', raise_if_not_found=False)
            if not source_location:
                source_location = self.env['stock.location'].search([
                    ('usage', '=', 'production')
                ], limit=1)
        
        # Get configured destination location or default to main warehouse
        dest_location_id = ICP.get_param('farm_management.harvest_dest_location_id')
        if dest_location_id:
            dest_location = self.env['stock.location'].browse(int(dest_location_id))
            if not dest_location.exists():
                dest_location = False
        else:
            dest_location = False
        
        if not dest_location:
            # Default: Company's main stock location
            warehouse = self.env['stock.warehouse'].search([
                ('company_id', '=', company.id)
            ], limit=1)
            if warehouse:
                dest_location = warehouse.lot_stock_id
        
        return source_location, dest_location

    def _create_harvest_cost(self):
        """Create a harvest cost entry in the project costs (for history only, no calculations)"""
        self.ensure_one()
        
        if not self.project_house_id or not self.project_house_id.project_id:
            return
        
        project = self.project_house_id.project_id
        
        # Calculate harvest value (quantity * unit cost)
        harvest_value = self.quantity * (self.unit_cost or 0)
        
        if harvest_value <= 0:
            return
        
        # Create harvest cost entry (as direct cost, linked to harvest)
        cost_vals = {
            'project_id': project.id,
            'cost_type': 'direct',  # Harvest costs are direct costs
            'amount': harvest_value,
            'date': self.date or fields.Date.today(),
            'description': _('حصاد: %s - %s (%s %s)') % (
                self.name,
                self.product_id.display_name if self.product_id else '',
                self.quantity,
                self.uom_id.name if self.uom_id else ''
            ),
            'source_house_ids': [(6, 0, [self.project_house_id.house_id.id])] if self.project_house_id.house_id else False,
            'harvest_entry_id': self.id,  # Link to harvest for display purposes
            'state': 'posted',  # Auto-post harvest costs
        }
        
        try:
            self.env['farm.project.cost'].create(cost_vals)
            self.message_post(body=_('تم إنشاء تكلفة حصاد: %s') % harvest_value)
        except Exception as e:
            self.message_post(body=_('فشل إنشاء تكلفة الحصاد: %s') % str(e))

    def _create_stock_move(self):
        """Create stock transfer (picking) with stock move to increase inventory quantity"""
        self.ensure_one()
        
        if not self.product_id:
            self.message_post(body=_('لم يتم إنشاء حركة مخزون: لم يتم تحديد المنتج'))
            return
        
        # Check if product is storable
        if self.product_id.detailed_type != 'product':
            self.message_post(body=_('لم يتم إنشاء حركة مخزون: المنتج ليس قابل للتخزين (نوع المنتج: %s)') % self.product_id.detailed_type)
            return
        
        # Get locations from settings
        source_location, dest_location = self._get_harvest_locations()
        
        if not source_location:
            self.message_post(body=_('لم يتم إنشاء حركة مخزون: لم يتم العثور على موقع المصدر. يرجى تكوين موقع مصدر الحصاد في الإعدادات.'))
            return
        
        if not dest_location:
            self.message_post(body=_('لم يتم إنشاء حركة مخزون: لم يتم العثور على موقع الوجهة. يرجى تكوين موقع وجهة الحصاد في الإعدادات.'))
            return
        
        company = self.company_id or self.env.company
        
        # Get UoM - always use the product's UOM for stock moves to avoid category mismatch
        uom = self.product_id.uom_id
        
        try:
            # Find appropriate picking type (receipt/incoming)
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
                ('company_id', '=', company.id),
                ('warehouse_id.company_id', '=', company.id),
            ], limit=1)
            
            if not picking_type:
                # Fallback: try internal transfer
                picking_type = self.env['stock.picking.type'].search([
                    ('code', '=', 'internal'),
                    ('company_id', '=', company.id),
                ], limit=1)
            
            if not picking_type:
                raise UserError(_('لم يتم العثور على نوع عملية نقل مناسب'))
            
            # Create picking (transfer)
            picking_vals = {
                'picking_type_id': picking_type.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
                'origin': self.name,
                'company_id': company.id,
            }
            picking = self.env['stock.picking'].create(picking_vals)
            
            # Create stock move inside picking
            move_vals = {
                'name': _('حصاد: %s - %s') % (self.name, self.product_id.display_name),
                'product_id': self.product_id.id,
                'product_uom_qty': self.quantity,
                'product_uom': uom.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
                'picking_id': picking.id,
                'origin': self.name,
                'company_id': company.id,
            }
            stock_move = self.env['stock.move'].create(move_vals)
            
            # Confirm the picking
            picking.action_confirm()
            
            # For moves from production/virtual locations, assign may not work
            # Try to assign, but don't fail if it doesn't work
            try:
                picking.action_assign()
            except Exception:
                pass
            
            # Set quantities on move lines
            if stock_move.move_line_ids:
                stock_move.move_line_ids.write({'quantity': self.quantity})
            else:
                # Create move line manually if needed
                self.env['stock.move.line'].create({
                    'move_id': stock_move.id,
                    'picking_id': picking.id,
                    'product_id': self.product_id.id,
                    'product_uom_id': uom.id,
                    'quantity': self.quantity,
                    'location_id': source_location.id,
                    'location_dest_id': dest_location.id,
                    'company_id': company.id,
                })
            
            # Validate the picking
            picking.button_validate()
            
            # Link picking and move to harvest entry
            self.picking_id = picking.id
            self.stock_move_id = stock_move.id
            
            # Get current stock quantity for verification
            quant = self.env['stock.quant'].search([
                ('product_id', '=', self.product_id.id),
                ('location_id', '=', dest_location.id),
            ], limit=1)
            current_qty = quant.quantity if quant else 0
            
            # Log success with picking and stock move info
            self.message_post(body=_('تم إنشاء عملية نقل: %s<br/>حركة المخزون: %s<br/>الكمية: %s %s<br/>الحالة: %s<br/>المخزون الحالي: %s') % (
                picking.name, stock_move.name, self.quantity, uom.name, picking.state, current_qty
            ))
            
        except Exception as e:
            self.message_post(body=_('فشل إنشاء حركة المخزون: %s') % str(e))
            import logging
            _logger = logging.getLogger(__name__)
            _logger.exception("Failed to create stock move for harvest %s", self.name)

    def _update_stock_move(self):
        """Update stock transfer when quantity changes - cancel old and create new"""
        self.ensure_one()
        
        if not self.picking_id:
            # Create new picking if doesn't exist
            self._create_stock_move()
            return
        
        # Cancel old picking and create new one with updated quantity
        old_picking = self.picking_id
        if old_picking.state == 'done':
            for move in old_picking.move_ids:
                move.write({'state': 'cancel'})
            old_picking.write({'state': 'cancel'})
        elif old_picking.state != 'cancel':
            old_picking.action_cancel()
        
        # Clear references and create new
        self.picking_id = False
        self.stock_move_id = False
        self._create_stock_move()

    def action_recalculate_cost(self):
        """Manual action to recalculate cost allocation"""
        for entry in self:
            entry._calculate_cost_allocation()
        return True

    def action_create_stock_move(self):
        """Manual action to create stock transfer if missing"""
        for entry in self:
            if not entry.picking_id:
                entry._create_stock_move()
            else:
                entry.message_post(body=_('عملية النقل موجودة بالفعل: %s') % entry.picking_id.name)
        return True

    def action_validate_stock_move(self):
        """Force validate stuck stock transfers"""
        for entry in self:
            if not entry.picking_id:
                entry.message_post(body='لا توجد عملية نقل للتحقق منها')
                continue
            
            picking = entry.picking_id
            
            if picking.state == 'done':
                entry.message_post(body='عملية النقل منتهية بالفعل')
                continue
            
            try:
                # Set quantities on move lines
                for move in picking.move_ids:
                    if move.move_line_ids:
                        move.move_line_ids.write({'quantity': entry.quantity})
                    else:
                        uom = entry.product_id.uom_id
                        self.env['stock.move.line'].create({
                            'move_id': move.id,
                            'picking_id': picking.id,
                            'product_id': entry.product_id.id,
                            'product_uom_id': uom.id,
                            'quantity': entry.quantity,
                            'location_id': move.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                            'company_id': move.company_id.id,
                        })
                
                # Validate the picking
                picking.button_validate()
                
                entry.message_post(body=_('تم تأكيد عملية النقل يدوياً: %s') % picking.name)
                
            except Exception as e:
                entry.message_post(body=_('فشل تأكيد عملية النقل: %s') % str(e))

    def action_cancel(self):
        """Cancel the harvest entry and its picking"""
        for entry in self:
            if entry.state == 'cancelled':
                continue

            try:
                source_location, dest_location = entry._get_harvest_locations()

                # Cancel the picking
                if entry.picking_id:
                    picking = entry.picking_id

                    if picking.state == 'done':
                        # Reverse stock quants
                        self.env['stock.quant']._update_available_quantity(
                            entry.product_id,
                            dest_location,
                            -entry.quantity,
                        )

                        if source_location and source_location.usage == 'internal':
                            self.env['stock.quant']._update_available_quantity(
                                entry.product_id,
                                source_location,
                                entry.quantity,
                            )

                        # Force cancel the picking and its moves
                        for move in picking.move_ids:
                            move.write({'state': 'cancel'})
                        picking.write({'state': 'cancel'})

                        entry.message_post(
                            body=_('تم إلغاء عملية النقل وعكس الكميات: %s') % picking.name
                        )

                    elif picking.state == 'cancel':
                        entry.message_post(
                            body=_('عملية النقل ملغية مسبقاً: %s') % picking.name
                        )

                    else:
                        # For non-done pickings
                        picking.action_cancel()
                        entry.message_post(
                            body=_('تم إلغاء عملية النقل: %s') % picking.name
                        )

            except Exception as e:
                entry.message_post(body=_('فشل إلغاء عملية النقل: %s') % str(e))
                raise UserError(_('فشل إلغاء عملية النقل: %s') % str(e))

            # Update state to cancelled
            entry.state = 'cancelled'
            entry.message_post(body=_('تم إلغاء سجل الحصاد'))

        return True

    def action_set_to_done(self):
        """Reset cancelled harvest back to done (recreates stock transfer)"""
        for entry in self:
            if entry.state != 'cancelled':
                continue
            
            try:
                # Clear old references and create new picking/transfer
                entry.picking_id = False
                entry.stock_move_id = False
                
                # Create new picking with stock move
                entry._create_stock_move()
                
                # Update state
                entry.state = 'done'
                entry.message_post(body=_('تم إعادة سجل الحصاد للحالة المنتهية'))
                
            except Exception as e:
                entry.message_post(body=_('فشل إعادة سجل الحصاد: %s') % str(e))
                raise UserError(_('فشل إعادة سجل الحصاد: %s') % str(e))
        
        return True

