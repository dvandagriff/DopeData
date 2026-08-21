# Copyright 2026 Drew Vandagriff
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without
# limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial
# portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
# LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. IN NO
# EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN
# AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
# OR OTHER DEALINGS IN THE SOFTWARE.

"""Business-day awareness for pipeline freshness checks.

All dates are treated as **naive UTC** — no timezone conversion is performed.
Callers are responsible for converting aware datetimes before passing them in.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime


# ── US Federal holidays (observed) for 2026 ─────────────────────────
# Source: https://www.opm.gov/policy-data-hr-tools/leave/holidays/observe-calendar
US_HOLIDAYS_2026: frozenset[date] = frozenset(
    [
        date(2026, 1, 1),   # New Year's Day (observed Wed)
        date(2026, 1, 19),  # Martin Luther King Jr. Day (Mon)
        date(2026, 2, 16),  # Presidents' Day (Mon)
        date(2026, 5, 25),  # Memorial Day (Mon)
        date(2026, 6, 19),  # Juneteenth (Fri)
        date(2026, 7, 3),   # Independence Day observed (Fri; actual Sat Jul 4)
        date(2026, 9, 7),   # Labor Day (Mon)
        date(2026, 10, 12), # Columbus Day (Mon)
        date(2026, 11, 11), # Veterans Day (Wed)
        date(2026, 11, 26), # Thanksgiving (Thu)
        date(2026, 12, 25), # Christmas Day (Fri)
    ]
)

WEEKEND_DAYS = {calendar.SATURDAY, calendar.SUNDAY}


def last_business_day(today: date | None = None, holidays: frozenset[date] | None = None) -> date:
    """Walk backward from *today* until a weekday not in *holidays* is found.

    Parameters
    ----------
    today :
        The reference date.  Defaults to ``date.today()`` (system local).
        If ``None`` is passed explicitly, the current UTC date is used.
    holidays :
        A ``frozenset[date]`` of holiday dates to skip. Defaults to
        :data:`US_HOLIDAYS_2026`.

    Returns
    -------
    date
        The most recent business day on or before *today*.
    """
    if today is None:
        today = date.today()

    if holidays is None:
        holidays = US_HOLIDAYS_2026

    current = today
    while True:
        dow = calendar.weekday(current.year, current.month, current.day)
        if dow not in WEEKEND_DAYS and current not in holidays:
            return current
        current -= _ONE_DAY


def is_stale(
    last_run_end: date | datetime | None,
    as_of: date | datetime | None = None,
    holidays: frozenset[date] | None = None,
) -> bool:
    """Determine whether a pipeline is considered stale.

    A pipeline is **stale** when its ``last_run_end`` occurs before the last
    business day of *as_of* (i.e. the data is not up to date for today's
    business operations).

    Parameters
    ----------
    last_run_end :
        The end timestamp of the last successful pipeline run.  May be a
        ``date``, ``datetime``, or ``None``.
    as_of :
        The reference "now" for staleness checks.  Defaults to today.
    holidays :
        Holiday set; defaults to :data:`US_HOLIDAYS_2026`.

    Returns
    -------
    bool
        ``True`` if the pipeline should be considered stale.
    """
    if last_run_end is None:
        return True  # never run → always stale

    if isinstance(last_run_end, datetime):
        last_date = last_run_end.date()
    else:
        last_date = last_run_end

    as_of_date = _to_date(as_of)
    last_biz = last_business_day(as_of_date, holidays)

    return last_date < last_biz


def freshness_date(
    last_run_end: date | datetime | None,
    as_of: date | datetime | None = None,
    holidays: frozenset[date] | None = None,
) -> date:
    """Return the effective "fresh" date for a pipeline run.

    Returns the ``last_run_end`` date if it is **not** stale (i.e. today's
    business day), otherwise returns the last business day — meaning the data
    reflects up to that point but needs refreshing.

    Parameters
    ----------
    last_run_end :
        See :func:`is_stale`.
    as_of :
        See :func:`is_stale`.
    holidays :
        See :func:`is_stale`.

    Returns
    -------
    date
        The freshness date.
    """
    stale = is_stale(last_run_end, as_of, holidays)
    if stale:
        return last_business_day(_to_date(as_of), holidays)
    # Not stale — the data is current for today.
    if isinstance(last_run_end, datetime):
        return last_run_end.date()
    assert isinstance(last_run_end, date)
    return last_run_end


# ── internal helpers ─────────────────────────────────────────────────

_ONE_DAY = date(2026, 1, 2) - date(2026, 1, 1)


def _to_date(value: date | datetime | None) -> date:
    """Convert an optional date/datetime to a plain ``date``."""
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    return value


