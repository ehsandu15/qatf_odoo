# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FarmProjectStatusWizard(models.TransientModel):
    _name = 'farm.project.status.wizard'
    _description = 'معالج تغيير حالة المشروع'

    project_id = fields.Many2one(
        'farm.project',
        string='المشروع',
        required=True,
    )
    action_type = fields.Selection([
        ('pause', 'إيقاف مؤقت'),
        ('resume', 'استئناف'),
        ('cancel', 'إلغاء'),
    ], string='نوع الإجراء', required=True)
    reason = fields.Text(
        string='السبب',
        required=True,
    )

    def action_confirm(self):
        """Execute the status change with reason"""
        self.ensure_one()
        
        if not self.reason:
            raise UserError(_('يجب إدخال السبب'))
        
        if self.action_type == 'pause':
            self.project_id._do_pause(self.reason)
        elif self.action_type == 'resume':
            self.project_id._do_resume(self.reason)
        elif self.action_type == 'cancel':
            self.project_id._do_cancel(self.reason)
        
        return {'type': 'ir.actions.act_window_close'}

