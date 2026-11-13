from datetime import datetime, time

import pytz
from pytz import AmbiguousTimeError, NonExistentTimeError

from odoo.exceptions import ValidationError


def timezone_for(company, user=None, context_tz=None):
    tz_name = (user.tz if user else False) or context_tz or company.partner_id.tz or "UTC"
    try:
        return pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError as error:
        raise ValidationError(f"Unknown time zone: {tz_name}") from error


def utc_to_local(value, timezone):
    value = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = pytz.UTC.localize(value)
    return value.astimezone(timezone)


def local_to_utc(value, timezone):
    if value.tzinfo is None:
        try:
            value = timezone.localize(value, is_dst=None)
        except (AmbiguousTimeError, NonExistentTimeError) as error:
            raise ValidationError("This local time is ambiguous or does not exist because of a time-zone change.") from error
    return value.astimezone(pytz.UTC).replace(tzinfo=None)


def float_to_time(value):
    hours = int(value)
    minutes = round((value - hours) * 60)
    if minutes == 60:
        hours += 1
        minutes = 0
    if hours == 24:
        return time(23, 59, 59, 999999)
    return time(hours, minutes)
