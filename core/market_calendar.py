import zoneinfo
from datetime import datetime, date, time as dt_time, timedelta
import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    Holiday,
    nearest_workday,
    USMartinLutherKingJr,
    USPresidentsDay,
    USMemorialDay,
    USLaborDay,
    USThanksgivingDay,
    GoodFriday,
)

# ─── NYSE HOLIDAY CALENDAR SPECIFICATION ───
class NYSEHolidayCalendar(AbstractHolidayCalendar):
    rules = [
        Holiday("New Years Day", month=1, day=1, observance=nearest_workday),
        USMartinLutherKingJr,
        USPresidentsDay,
        GoodFriday,
        USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]

_nyse_calendar = NYSEHolidayCalendar()

def get_eastern_timezone():
    """
    Returns ZoneInfo for America/New_York (handles EST/EDT transitions).
    """
    return zoneinfo.ZoneInfo("America/New_York")

def get_now_eastern():
    """
    Returns current datetime in US Eastern timezone.
    """
    return datetime.now(get_eastern_timezone())

def is_nyse_holiday(check_date: date) -> bool:
    """
    Returns True if check_date is an official NYSE market holiday.
    """
    year = check_date.year
    holidays = _nyse_calendar.holidays(start=f"{year}-01-01", end=f"{year}-12-31")
    return pd.Timestamp(check_date) in holidays

def is_early_close_day(check_date: date) -> bool:
    """
    Returns True if check_date is a scheduled 1:00 PM ET NYSE early-close day:
    - Day before Independence Day (July 3 if weekday)
    - Black Friday (Day after Thanksgiving - 4th Friday in Nov)
    - Christmas Eve (Dec 24 if weekday)
    """
    if check_date.weekday() >= 5 or is_nyse_holiday(check_date):
        return False

    year = check_date.year
    month = check_date.month
    day = check_date.day

    # July 3 (Day before Independence Day)
    if month == 7 and day == 3:
        return True

    # Christmas Eve (Dec 24)
    if month == 12 and day == 24:
        return True

    # Black Friday (Day after Thanksgiving: Thanksgiving is 4th Thursday of Nov)
    if month == 11 and check_date.weekday() == 4: # Friday
        # Check if Thursday prior was Thanksgiving
        thanksgiving = _nyse_calendar.holidays(start=f"{year}-11-01", end=f"{year}-11-30")
        for h in thanksgiving:
            if h.month == 11 and h.day == day - 1:
                return True

    return False

def is_trading_day(check_date: date = None) -> bool:
    """
    Returns True if check_date is a valid trading day (Mon-Fri and not a NYSE holiday).
    """
    if check_date is None:
        check_date = get_now_eastern().date()
    if check_date.weekday() >= 5:
        return False
    return not is_nyse_holiday(check_date)

def get_market_schedule(check_date: date = None) -> dict:
    """
    Returns schedule dict for check_date:
    {
      "is_trading_day": bool,
      "is_early_close": bool,
      "market_open": time(9, 30),
      "market_close": time(16, 0) or time(13, 0),
      "post_close_scan_start": time(16, 15) or time(13, 15),
      "pm_digest_time": time(16, 30) or time(13, 30),
      "am_digest_time": time(9, 0)
    }
    """
    if check_date is None:
        check_date = get_now_eastern().date()

    trading = is_trading_day(check_date)
    early = is_early_close_day(check_date) if trading else False

    if early:
        m_close = dt_time(13, 0)
        pc_scan = dt_time(13, 15)
        pm_digest = dt_time(13, 30)
    else:
        m_close = dt_time(16, 0)
        pc_scan = dt_time(16, 15)
        pm_digest = dt_time(16, 30)

    return {
        "date": check_date,
        "is_trading_day": trading,
        "is_early_close": early,
        "am_digest_time": dt_time(9, 0),
        "market_open": dt_time(9, 30),
        "market_close": m_close,
        "post_close_scan_start": pc_scan,
        "pm_digest_time": pm_digest
    }

def get_market_status(now_et: datetime = None) -> dict:
    """
    Evaluates current time against NYSE schedule.
    Returns status flags:
    {
      "datetime_et": datetime,
      "trading_date_str": "YYYY-MM-DD",
      "is_trading_day": bool,
      "is_market_hours": bool,
      "is_post_close": bool,
      "is_am_digest_window": bool,
      "is_pm_digest_window": bool
    }
    """
    if now_et is None:
        now_et = get_now_eastern()

    c_date = now_et.date()
    c_time = now_et.time()
    schedule = get_market_schedule(c_date)

    trading = schedule["is_trading_day"]
    market_hours = False
    post_close = False
    am_window = False
    pm_window = False

    if trading:
        # Market Hours: 9:30 AM to Close (1:00 PM or 4:00 PM)
        market_hours = (schedule["market_open"] <= c_time <= schedule["market_close"])
        
        # Post-Close Scan Window: 15-minute window following post_close_scan_start
        pc_start = schedule["post_close_scan_start"]
        pc_end = dt_time(pc_start.hour, pc_start.minute + 45) if pc_start.minute + 45 < 60 else dt_time(pc_start.hour + 1, (pc_start.minute + 45) % 60)
        post_close = (pc_start <= c_time <= pc_end)

        # 9:00 AM AM Digest Window (9:00 AM - 9:29 AM ET)
        am_window = (dt_time(9, 0) <= c_time < dt_time(9, 30))

        # PM Digest Window (e.g. 4:30 PM - 5:59 PM ET or 1:30 PM - 2:59 PM ET on early close)
        pm_start = schedule["pm_digest_time"]
        pm_window = (c_time >= pm_start)

    return {
        "datetime_et": now_et,
        "trading_date_str": c_date.strftime("%Y-%m-%d"),
        "is_trading_day": trading,
        "is_early_close": schedule["is_early_close"],
        "is_market_hours": market_hours,
        "is_post_close": post_close,
        "is_am_digest_window": am_window,
        "is_pm_digest_window": pm_window,
        "schedule": schedule
    }
