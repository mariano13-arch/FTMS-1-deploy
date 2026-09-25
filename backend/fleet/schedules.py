from dataclasses import dataclass
from datetime import time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import Driver

MANILA = ZoneInfo("Asia/Manila")
WEEKDAYS = (
    "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"
)


@dataclass(frozen=True)
class DriverScheduleEvaluation:
    status: str
    reason_code: str = ""
    reason: str = ""


def compact_driver_name(driver):
    middle = f"{driver.middle_name[0].upper()}." if driver.middle_name else ""
    return " ".join(filter(None, (driver.first_name, middle, driver.last_name)))


def evaluate_driver_schedule(driver, at):
    """Evaluate an FTMS local schedule using the shift-start day in Manila."""
    local = timezone.localtime(at, MANILA) if timezone.is_aware(at) else at.replace(tzinfo=MANILA)
    local_time = local.time().replace(tzinfo=None)
    if driver.work_shift == Driver.WorkShift.NIGHT:
        shift_day = local.date() - timedelta(days=1) if local_time < time(6) else local.date()
        on_shift = local_time >= time(18) or local_time < time(6)
    else:
        shift_day = local.date()
        on_shift = time(6) <= local_time < time(18)
    if WEEKDAYS[shift_day.weekday()] in set(driver.weekly_rest_days or []):
        return DriverScheduleEvaluation(
            "REST_DAY", "DRIVER_REST_DAY",
            "Driver is on a scheduled weekly rest day for the pickup date.",
        )
    if not on_shift:
        return DriverScheduleEvaluation(
            "OFF_SHIFT", "DRIVER_OFF_SHIFT",
            "Driver is outside the assigned work shift for the scheduled pickup time.",
        )
    return DriverScheduleEvaluation("ON_SHIFT")
