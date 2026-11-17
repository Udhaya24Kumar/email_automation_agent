from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def today_ist():
    return datetime.now(IST).date()
