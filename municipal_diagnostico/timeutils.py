from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from flask import current_app


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def app_timezone() -> ZoneInfo:
    timezone_name = "America/Hermosillo"
    try:
        timezone_name = current_app.config.get("APP_TIMEZONE", timezone_name)
    except RuntimeError:
        timezone_name = timezone_name
    return ZoneInfo(timezone_name)


def assume_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_localtime(value: datetime | None) -> datetime | None:
    utc_value = assume_utc(value)
    if utc_value is None:
        return None
    return utc_value.astimezone(app_timezone())


def to_utc_naive(value: datetime | None, *, assume_local: bool = False) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        timezone = app_timezone() if assume_local else UTC
        value = value.replace(tzinfo=timezone)
    return value.astimezone(UTC).replace(tzinfo=None)
