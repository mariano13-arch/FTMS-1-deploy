from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from fleet.models import Driver
from fleet.schedules import evaluate_driver_schedule

MANILA = ZoneInfo("Asia/Manila")


class DriverScheduleTests(SimpleTestCase):
    def driver(self, shift, rest_days=()):
        return Driver(work_shift=shift, weekly_rest_days=list(rest_days))

    def at(self, weekday_day, hour, minute=0):
        return datetime(2026, 9, weekday_day, hour, minute, tzinfo=MANILA)

    def test_day_shift_boundaries(self):
        driver = self.driver(Driver.WorkShift.DAY)
        self.assertEqual(evaluate_driver_schedule(driver, self.at(21, 6)).status, "ON_SHIFT")
        self.assertEqual(evaluate_driver_schedule(driver, self.at(21, 10)).status, "ON_SHIFT")
        self.assertEqual(evaluate_driver_schedule(driver, self.at(21, 18)).status, "OFF_SHIFT")
        self.assertEqual(evaluate_driver_schedule(driver, self.at(21, 20)).status, "OFF_SHIFT")

    def test_night_shift_boundaries_and_shift_start_day(self):
        driver = self.driver(Driver.WorkShift.NIGHT)
        self.assertEqual(evaluate_driver_schedule(driver, self.at(21, 18)).status, "ON_SHIFT")
        self.assertEqual(evaluate_driver_schedule(driver, self.at(21, 20)).status, "ON_SHIFT")
        self.assertEqual(evaluate_driver_schedule(driver, self.at(22, 2)).status, "ON_SHIFT")
        self.assertEqual(evaluate_driver_schedule(driver, self.at(22, 6)).status, "OFF_SHIFT")
        self.assertEqual(evaluate_driver_schedule(driver, self.at(22, 7)).status, "OFF_SHIFT")

    def test_night_rest_day_continues_after_midnight(self):
        driver = self.driver(Driver.WorkShift.NIGHT, ("MONDAY", "THURSDAY"))
        self.assertEqual(evaluate_driver_schedule(driver, self.at(21, 23)).status, "REST_DAY")
        self.assertEqual(evaluate_driver_schedule(driver, self.at(22, 2)).status, "REST_DAY")
        self.assertEqual(evaluate_driver_schedule(driver, self.at(22, 18)).status, "ON_SHIFT")
