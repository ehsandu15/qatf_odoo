# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class Farm(models.Model):
    _name = 'farm.farm'
    _description = 'المزرعة'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(
        string='اسم المزرعة',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='الرمز',
        tracking=True,
    )
    manager_id = fields.Many2one(
        'res.users',
        string='المدير',
        tracking=True,
    )
    location = fields.Char(
        string='الموقع',
    )
    description = fields.Text(
        string='الوصف',
    )
    active = fields.Boolean(
        string='نشط',
        default=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='الشركة',
        default=lambda self: self.env.company,
    )
    
    # Hierarchy relations
    sector_ids = fields.One2many(
        'farm.sector',
        'farm_id',
        string='القطاعات',
    )
    
    # Computed fields
    sector_count = fields.Integer(
        string='عدد القطاعات',
        compute='_compute_counts',
    )
    unit_count = fields.Integer(
        string='عدد الوحدات',
        compute='_compute_counts',
    )
    house_count = fields.Integer(
        string='عدد البيوت',
        compute='_compute_counts',
    )
    total_area = fields.Float(
        string='إجمالي المساحة (م²)',
        compute='_compute_counts',
    )
    project_count = fields.Integer(
        string='عدد المشاريع',
        compute='_compute_project_count',
    )

    @api.depends('sector_ids', 'sector_ids.unit_ids', 'sector_ids.unit_ids.house_ids')
    def _compute_counts(self):
        for farm in self:
            sectors = farm.sector_ids
            units = sectors.mapped('unit_ids')
            houses = units.mapped('house_ids')
            farm.sector_count = len(sectors)
            farm.unit_count = len(units)
            farm.house_count = len(houses)
            farm.total_area = sum(houses.mapped('area'))

    def _compute_project_count(self):
        for farm in self:
            farm.project_count = self.env['farm.project'].search_count([
                ('farm_id', '=', farm.id)
            ])

    def action_view_sectors(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'القطاعات',
            'res_model': 'farm.sector',
            'view_mode': 'tree,kanban,form',
            'domain': [('farm_id', '=', self.id)],
            'context': {'default_farm_id': self.id},
        }

    def action_view_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'الوحدات',
            'res_model': 'farm.unit',
            'view_mode': 'tree,kanban,form',
            'domain': [('sector_id.farm_id', '=', self.id)],
        }

    def action_view_houses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'البيوت',
            'res_model': 'farm.house',
            'view_mode': 'tree,kanban,form',
            'domain': [('unit_id.sector_id.farm_id', '=', self.id)],
        }

    def action_view_projects(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'المشاريع',
            'res_model': 'farm.project',
            'view_mode': 'tree,kanban,form',
            'domain': [('farm_id', '=', self.id)],
            'context': {'default_farm_id': self.id},
        }


class Sector(models.Model):
    _name = 'farm.sector'
    _description = 'القطاع'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'farm_id, name'

    name = fields.Char(
        string='اسم القطاع',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='الرمز',
    )
    farm_id = fields.Many2one(
        'farm.farm',
        string='المزرعة',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    description = fields.Text(
        string='الوصف',
    )
    active = fields.Boolean(
        string='نشط',
        default=True,
    )
    
    # Hierarchy relations
    unit_ids = fields.One2many(
        'farm.unit',
        'sector_id',
        string='الوحدات',
    )
    
    # Computed fields
    full_name = fields.Char(
        string='الاسم الكامل',
        compute='_compute_full_name',
        store=True,
    )
    unit_count = fields.Integer(
        string='عدد الوحدات',
        compute='_compute_counts',
    )
    house_count = fields.Integer(
        string='عدد البيوت',
        compute='_compute_counts',
    )
    total_area = fields.Float(
        string='إجمالي المساحة (م²)',
        compute='_compute_counts',
    )

    @api.depends('name', 'farm_id.name')
    def _compute_full_name(self):
        for sector in self:
            if sector.farm_id:
                sector.full_name = f"{sector.farm_id.name} / {sector.name}"
            else:
                sector.full_name = sector.name

    @api.depends('unit_ids', 'unit_ids.house_ids')
    def _compute_counts(self):
        for sector in self:
            units = sector.unit_ids
            houses = units.mapped('house_ids')
            sector.unit_count = len(units)
            sector.house_count = len(houses)
            sector.total_area = sum(houses.mapped('area'))

    def action_view_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'الوحدات',
            'res_model': 'farm.unit',
            'view_mode': 'tree,kanban,form',
            'domain': [('sector_id', '=', self.id)],
            'context': {'default_sector_id': self.id},
        }

    def action_view_houses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'البيوت',
            'res_model': 'farm.house',
            'view_mode': 'tree,kanban,form',
            'domain': [('unit_id.sector_id', '=', self.id)],
        }


class Unit(models.Model):
    _name = 'farm.unit'
    _description = 'الوحدة'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sector_id, name'

    name = fields.Char(
        string='اسم الوحدة',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='الرمز',
    )
    sector_id = fields.Many2one(
        'farm.sector',
        string='القطاع',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    description = fields.Text(
        string='الوصف',
    )
    active = fields.Boolean(
        string='نشط',
        default=True,
    )
    
    # Related fields for hierarchy access
    farm_id = fields.Many2one(
        related='sector_id.farm_id',
        string='المزرعة',
        store=True,
        readonly=True,
    )
    
    # Hierarchy relations
    house_ids = fields.One2many(
        'farm.house',
        'unit_id',
        string='البيوت',
    )
    
    # Computed fields
    full_name = fields.Char(
        string='الاسم الكامل',
        compute='_compute_full_name',
        store=True,
    )
    house_count = fields.Integer(
        string='عدد البيوت',
        compute='_compute_counts',
    )
    total_area = fields.Float(
        string='إجمالي المساحة (م²)',
        compute='_compute_counts',
    )

    @api.depends('name', 'sector_id.full_name')
    def _compute_full_name(self):
        for unit in self:
            if unit.sector_id:
                unit.full_name = f"{unit.sector_id.full_name} / {unit.name}"
            else:
                unit.full_name = unit.name

    @api.depends('house_ids', 'house_ids.area')
    def _compute_counts(self):
        for unit in self:
            houses = unit.house_ids
            unit.house_count = len(houses)
            unit.total_area = sum(houses.mapped('area'))

    def action_view_houses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'البيوت',
            'res_model': 'farm.house',
            'view_mode': 'tree,kanban,form',
            'domain': [('unit_id', '=', self.id)],
            'context': {'default_unit_id': self.id},
        }


class House(models.Model):
    _name = 'farm.house'
    _description = 'البيت'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'unit_id, name'

    name = fields.Char(
        string='اسم البيت',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='الرمز',
    )
    unit_id = fields.Many2one(
        'farm.unit',
        string='الوحدة',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    area = fields.Float(
        string='المساحة (م²)',
        required=True,
        tracking=True,
        help='مساحة البيت بالمتر المربع',
    )
    house_type = fields.Selection([
        ('glass', 'زجاجي'),
        ('plastic', 'بلاستيكي'),
        ('polycarbonate', 'بوليكربونيت'),
    ], string='نوع البيت', default='plastic', tracking=True)
    description = fields.Text(
        string='الوصف',
    )
    active = fields.Boolean(
        string='نشط',
        default=True,
    )
    
    # Related fields for hierarchy access
    sector_id = fields.Many2one(
        related='unit_id.sector_id',
        string='القطاع',
        store=True,
        readonly=True,
    )
    farm_id = fields.Many2one(
        related='unit_id.farm_id',
        string='المزرعة',
        store=True,
        readonly=True,
    )
    
    # Analytic account
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='الحساب التحليلي',
        readonly=True,
        copy=False,
    )
    
    # Computed fields
    full_name = fields.Char(
        string='الاسم الكامل',
        compute='_compute_full_name',
        store=True,
    )

    @api.depends('name', 'unit_id.full_name')
    def _compute_full_name(self):
        for house in self:
            if house.unit_id:
                house.full_name = f"{house.unit_id.full_name} / {house.name}"
            else:
                house.full_name = house.name

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._create_analytic_account()
        return records

    def _create_analytic_account(self):
        """Create analytic account for the house automatically"""
        self.ensure_one()
        if not self.analytic_account_id:
            # Find or create the farm analytic plan
            plan = self.env['account.analytic.plan'].search([
                ('name', '=', 'مشاريع المزارع')
            ], limit=1)
            if not plan:
                plan = self.env['account.analytic.plan'].create({
                    'name': 'مشاريع المزارع',
                    'description': 'خطة تحليلية لمشاريع المزارع',
                })
            
            analytic_account = self.env['account.analytic.account'].create({
                'name': self.full_name,
                'code': f"HOUSE-{self.id}",
                'plan_id': plan.id,
                'company_id': self.farm_id.company_id.id if self.farm_id else self.env.company.id,
            })
            self.analytic_account_id = analytic_account.id

    @api.constrains('area')
    def _check_area(self):
        for house in self:
            if house.area <= 0:
                raise ValidationError(_('مساحة البيت يجب أن تكون أكبر من صفر'))

    def _compute_display_name(self):
        for house in self:
            house.display_name = house.name

