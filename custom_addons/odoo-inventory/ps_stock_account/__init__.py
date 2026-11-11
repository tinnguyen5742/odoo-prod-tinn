from . import models


def post_init_hook(env):
    env['res.company']._ps_set_average_cost_method_defaults()
