from datetime import datetime, timezone

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_isoformat(value: datetime) -> str:
    """Serialize stored timestamps as explicit UTC so browsers can localize them."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
