# FTMS local development driver schedules

The `Driver.work_shift` and `Driver.weekly_rest_days` fields are temporary FTMS
local development master data. They are not Workforce/HRMS-synchronized records
and must not be interpreted as attendance, clock-in/out, leave, overtime, or
other operational HR history.

`seed_professional_drivers` deterministically assigns Day Shift (06:00–18:00)
to `DRV-PH-0001` through `DRV-PH-0075`, Night Shift (18:00–06:00) to
`DRV-PH-0076` through `DRV-PH-0150`, and Day Shift to the preserved ALJOHN row.
It also assigns exactly two weekly rest days to all 151 managed active drivers.

Dispatch evaluates these schedules in `Asia/Manila` using the transport
request's scheduled pickup datetime. For a night shift after midnight, the
applicable rest day is the preceding shift-start day. Off-shift and rest-day
drivers are excluded from optimization and cannot be selected through manual
override.

When Workforce/HRMS integration becomes available, the external workforce
schedule becomes authoritative. This local source should then be superseded;
it must not be presented as Workforce-synchronized data.
