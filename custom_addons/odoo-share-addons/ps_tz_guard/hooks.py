import logging

from .models.tz_utils import resolve_tz

_logger = logging.getLogger(__name__)

_TZ_FIELD_NAMES = {"tz", "event_tz", "date_tz", "mail_tz", "user_tz"}


def post_init_hook(env):
    for model_name in sorted(env):
        model = env[model_name]
        for fname, field in list(model._fields.items()):
            if fname not in _TZ_FIELD_NAMES or field.type != "selection":
                continue
            if not field.store or field.related or (field.compute and not field.inverse):
                continue
            _sanitize_field(env, model_name, fname, field)


def _sanitize_field(env, model_name, fname, field):
    model = env[model_name]
    env.cr.execute(
        f'SELECT DISTINCT "{fname}" FROM "{model._table}" WHERE "{fname}" IS NOT NULL'
    )
    values = [row[0] for row in env.cr.fetchall()]
    for value in values:
        new_value = resolve_tz(value)
        if new_value == value:
            continue
        if not new_value and field.required:
            new_value = "UTC"
            env.flush_all()
            env.cr.execute(
                f'UPDATE "{model._table}" SET "{fname}" = %s WHERE "{fname}" = %s',
                [new_value, value],
            )
        else:
            model.with_context(active_test=False).sudo().search(
                [(fname, "=", value)]
            ).write({fname: new_value or False})
        _logger.warning("ps_tz_guard: %s.%s %r -> %r", model_name, fname, value, new_value)
