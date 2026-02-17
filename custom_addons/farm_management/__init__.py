# -*- coding: utf-8 -*-

from . import models
from . import wizard
from . import controllers


def _post_init_hook(env):
    """Recompute is_farm_produce flag for all products after module installation"""
    env['product.product'].search([])._compute_is_farm_produce()

