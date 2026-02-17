# -*- coding: utf-8 -*-
{
    'name': 'إدارة المزارع',
    'name_en': 'Farm Management',
    'version': '17.0.1.0.0',
    'category': 'Agriculture/Farm Management',
    'summary': 'إدارة المزارع ومشاريع الإنتاج وتوزيع التكاليف',
    'description': """
        نظام شامل لإدارة المزارع يتضمن:
        - هيكل هرمي: مزرعة ← قطاع ← وحدة ← بيت
        - مشاريع الإنتاج مع تتبع الحالة
        - توزيع التكاليف المباشرة وغير المباشرة حسب المساحة
        - إدارة الحصاد وتتبع تكلفة الإنتاج
        - توزيع التكاليف التدريجي على المحصول
        - تقارير ومؤشرات أداء الإنتاج
    """,
    'author': 'Farm Management Team',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'account',
        'analytic',
        'stock',
        'stock_landed_costs',
        'product',
        'sale',
    ],
    'data': [
        # Security
        'security/farm_security.xml',
        'security/ir.model.access.csv',
        # Data (load before views)
        'data/farm_warehouses.xml',
        'data/farm_categories.xml',
        'data/farm_inventory_config_data.xml',
        'data/farm_products.xml',
        'data/farm_config_data.xml',
        'data/farm_landed_cost_data.xml',
        # Views
        'views/farm_views.xml',
        'views/farm_project_views.xml',
        'views/farm_cost_views.xml',
        'views/farm_harvest_views.xml',
        'views/farm_product_order_views.xml',
        'views/account_account_views.xml',
        'views/farm_inventory_config_views.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_pallet_views.xml',
        'views/res_partner_views.xml',
        # Reports (must load before menus)
        'report/farm_cost_report.xml',
        'report/farm_harvest_report.xml',
        'report/pallet_label_report.xml',
        # Wizards
        'wizard/project_status_wizard_views.xml',
        'wizard/product_quick_add_wizard_views.xml',
        'wizard/farm_import_wizard_views.xml',
        'wizard/template_download_wizard_views.xml',
        # Menus (must load last)
        'views/menu_views.xml',
    ],
    'demo': [
        'data/farm_demo_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'farm_management/static/src/css/farm_timeline.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': '_post_init_hook',
}

