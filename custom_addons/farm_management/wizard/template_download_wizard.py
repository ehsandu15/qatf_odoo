# -*- coding: utf-8 -*-

from odoo import models, fields, api


class TemplateDownloadWizard(models.TransientModel):
    _name = 'template.download.wizard'
    _description = 'تحميل قوالب الاستيراد'

    template_type = fields.Selection([
        ('farm_complete', 'قالب المزارع الموحد (Farm + Sectors + Units + Houses)'),
        ('project_complete', 'قالب المشاريع الموحد (Project + House Assignments)'),
    ], string='نوع القالب', default='farm_complete', required=True)

    def action_download(self):
        """Download the selected template as XLSX"""
        template_map = {
            'farm_complete': 'farm_complete_import.xlsx',
            'project_complete': 'project_complete_import.xlsx',
        }
        
        filename = template_map.get(self.template_type)
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/farm_management/download_template/{filename}',
            'target': 'new',
        }

