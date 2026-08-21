# Freshness Rule — Last Business Day

## Definition

A pipeline is considered **stale** when its last successful run ended *before* the **last business day** relative to a reference date ("as-of" date).

Formally:

```
stale(LastRunEnd, AsOf)  ≡  LastRunEnd < LastBusinessDay(AsOf)
```

Where `LastBusinessDay(AsOf)` is the most recent weekday (Monday–Friday) that is not a US federal holiday and falls on or before `AsOf`.

## Business Day Calculation

The function `last_business_day()` walks backward from the *as-of* date until it finds a day that satisfies both:

1. It is **not** Saturday or Sunday (`calendar.SATURDAY`, `calendar.SUNDAY`).
2. It is **not** in the US federal holiday set (`US_HOLIDAYS_2026`).

### Example: 2026-08-15 (Saturday)

```
Saturday Aug 15 → not a business day (weekend)
Friday Aug 14   → weekday, not a holiday → LAST BUSINESS DAY = Aug 14
```

### Example: 2026-08-17 (Monday) with holiday on Aug 14

If Aug 14 were a holiday:

```
Monday Aug 17 → weekday, but is last_biz? Check if Aug 17 itself is the target.
               If we're computing last_biz(Aug 17), we return Aug 17 directly (it's a Mon).
But for staleness of data synced on Aug 14 (a holiday):
  last_biz(Aug 17) = Aug 17 → data from Aug 14 < Aug 17? Yes, stale.
```

### Example: Independence Day observed (2026)

Independence Day is July 4 (Saturday in 2026). The observed holiday is Friday July 3. So:

```
Friday Jul 3 → holiday → skip
Thursday Jul 2 → weekday, not a holiday → return Jul 2
```

## US Federal Holidays for 2026

| Holiday                        | Date       | Day   | Observed     |
|-------------------------------|------------|-------|--------------|
| New Year's Day               | Jan 1      | Wed   | Jan 1 (Wed)  |
| Martin Luther King Jr. Day   | Jan 19     | Mon   | —            |
| Presidents' Day              | Feb 16     | Mon   | —            |
| Memorial Day                 | May 25     | Mon   | —            |
| Juneteenth                   | Jun 19     | Fri   | —            |
| Independence Day             | Jul 4      | Sat   | Jul 3 (Fri)  |
| Labor Day                    | Sep 7      | Mon   | —            |
| Columbus Day                 | Oct 12     | Mon   | —            |
| Veterans Day                 | Nov 11     | Wed   | —            |
| Thanksgiving                 | Nov 26     | Thu   | —            |
| Christmas Day                | Dec 25     | Fri   | —            |

These are encoded in `src/dope/core/freshness.py` as `US_HOLIDAYS_2026`.

## Edge Cases

| Scenario                          | Behavior                                         |
|-----------------------------------|--------------------------------------------------|
| `last_run_end = None`             | Always stale (pipeline never ran).               |
| `last_run_end` on a weekend       | Date comparison only — if date ≥ last_biz, fresh. |
| `last_run_end == last_biz`        | **Not** stale (boundary case).                   |
| Custom holiday set                | Pass `holidays=frozenset([...])` to override.    |
| `as_of` is a datetime             | Extracted to date via `.date()`.                 |
| `as_of` is on a holiday           | Walks back to the nearest business day.          |

## Production Deployment: Adding `holidays` Library

The current implementation uses a hardcoded list of US federal holidays for 2026. For production use, swap in the [`holidays`](https://github.com/vacanza/holidays) library:

```python
import holidays
from datetime import date

US_HOLIDAYS = frozenset(
    holidays.US(years=range(2024, 2031)).keys()
)

def last_business_day(today=None, holidays=None):
    if today is None:
        today = date.today()
    if holidays is None:
        holidays = US_HOLIDAYS
    # ... same logic as current implementation
```

Benefits of using the `holidays` library:
- Automatically handles holiday changes across years.
- Supports multiple countries and custom observation rules.
- No manual updates needed for future calendar years.

## Freshness Date Computation

The function `freshness_date()` returns the effective "data freshness date":

- If **not stale**: returns `last_run_end.date()` — the data is current for today.
- If **stale**: returns `last_business_day(as_of)` — the data reflects up to the last business day but needs refreshing.

This ensures that downstream consumers always see a meaningful date even when pipelines are behind schedule.

## Code Reference

- `src/dope/core/freshness.py` — `is_stale()`, `last_business_day()`, `freshness_date()`
- `tests/test_freshness.py` — comprehensive edge case tests
