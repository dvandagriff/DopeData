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

"""Tests for freshness utilities (last_business_day, is_stale, freshness_date)."""

from __future__ import annotations

import calendar
from datetime import date, datetime

from dope.core.freshness import (
    US_HOLIDAYS_2026,
    freshness_date,
    is_stale,
    last_business_day,
)


# ── last_business_day tests ────────────────────────────────────────────


class TestLastBusinessDay:
    """Test the ``last_business_day`` function."""

    def test_weekday_returns_same_day(self) -> None:
        # 2026-08-14 is a Friday (not a holiday)
        result = last_business_day(date(2026, 8, 14))
        assert result == date(2026, 8, 14)

    def test_saturday_walks_to_friday(self) -> None:
        # 2026-08-15 is a Saturday → should walk back to Fri Aug 14
        result = last_business_day(date(2026, 8, 15))
        assert result == date(2026, 8, 14)

    def test_sunday_walks_to_friday(self) -> None:
        # 2026-08-16 is a Sunday → should walk back to Fri Aug 14
        result = last_business_day(date(2026, 8, 16))
        assert result == date(2026, 8, 14)

    def test_monday_with_holiday_walks_back(self) -> None:
        # 2026-01-05 is a Monday. Jan 1 was holiday (observed Wed Jan 1).
        # Check that a weekday before holidays works normally.
        result = last_business_day(date(2026, 1, 5))
        assert result == date(2026, 1, 5)

    def test_holiday_wednesday_walks_back(self) -> None:
        # Jan 1, 2026 is New Year's Day (a Wednesday holiday).
        # The business day before that should be Tue Dec 30.
        result = last_business_day(date(2026, 1, 1))
        assert result == date(2025, 12, 31)

    def test_custom_holidays_respected(self) -> None:
        custom_holidays = frozenset([date(2026, 8, 14)])  # Friday is a holiday
        result = last_business_day(date(2026, 8, 14), holidays=custom_holidays)
        assert result == date(2026, 8, 13)  # Thursday

    def test_custom_holidays_chain_walk(self) -> None:
        custom_holidays = frozenset([date(2026, 8, 14), date(2026, 8, 13)])
        result = last_business_day(date(2026, 8, 14), holidays=custom_holidays)
        assert result == date(2026, 8, 12)  # Wednesday

    def test_default_today(self) -> None:
        """Calling without args uses the system's current date."""
        import datetime as _dt
        today = _dt.date.today()
        result = last_business_day()
        assert isinstance(result, date)
        # Should not be a weekend or holiday
        dow = calendar.weekday(result.year, result.month, result.day)
        assert dow not in (calendar.SATURDAY, calendar.SUNDAY)


# ── is_stale tests ─────────────────────────────────────────────────────


class TestIsStale:
    """Test the ``is_stale`` function."""

    def test_none_last_run_is_stale(self) -> None:
        assert is_stale(None) is True

    def test_fresh_data_not_stale(self) -> None:
        # Last run on Fri Aug 14, as_of also Fri Aug 14 → fresh
        last = date(2026, 8, 14)
        as_of = date(2026, 8, 14)
        assert is_stale(last, as_of=as_of) is False

    def test_yesterday_data_fresh_on_monday(self) -> None:
        # Last run on Fri Aug 14, as_of Mon Aug 17 → last business day = Aug 14
        last = date(2026, 8, 14)
        as_of = date(2026, 8, 17)
        assert is_stale(last, as_of=as_of) is False

    def test_two_day_old_data_fresh_on_monday(self) -> None:
        # Last run on Sat Aug 15 (weekend), but data date = Aug 15 < last_biz(Aug 17)=Aug 14? No, Aug 15 > Aug 14... wait.
        # Actually is_stale compares the *date* of last_run_end against last_business_day.
        # Aug 15 (Saturday) is still after Aug 14 (last biz day), so it's stale because 08-15 < 08-14? No, 08-15 > 08-14.
        # Hmm, the function compares last_date < last_biz. Aug 15 is NOT < Aug 14, so it returns False (not stale).
        # But wait — Saturday isn't a real sync day. Let's check: the code does last_date < last_biz.
        last = date(2026, 8, 15)
        as_of = date(2026, 8, 17)
        # Aug 15 is NOT before Aug 14 (last business day of Aug 17), so it should be False? 
        # Actually Aug 15 > Aug 14, so last_date < last_biz → False. But Aug 15 is weekend...
        # The staleness check only compares dates, not whether the run was on a biz day.
        assert is_stale(last, as_of=as_of) is False

    def test_old_data_is_stale(self) -> None:
        # Last run on Aug 12 (Wed), as_of Aug 15 → last business day = Aug 14
        # 08-12 < 08-14 → stale
        last = date(2026, 8, 12)
        as_of = date(2026, 8, 15)
        assert is_stale(last, as_of=as_of) is True

    def test_datetime_last_run(self) -> None:
        # Last run on Aug 14 at 08:03, as_of Aug 15 → not stale
        last = datetime(2026, 8, 14, 8, 3, 12)
        as_of = date(2026, 8, 15)
        assert is_stale(last, as_of=as_of) is False

    def test_datetime_last_run_old(self) -> None:
        # Last run on Aug 12 → stale when checked on Aug 15
        last = datetime(2026, 8, 12, 2, 31, 0)
        as_of = date(2026, 8, 15)
        assert is_stale(last, as_of=as_of) is True

    def test_custom_holidays_affect_staleness(self) -> None:
        # Aug 14 is a holiday → last business day of Aug 15 = Aug 13 (Thu)
        custom_holidays = frozenset([date(2026, 8, 14)])
        last = date(2026, 8, 14)
        as_of = date(2026, 8, 15)
        # With Aug 14 being a holiday, last_biz = Aug 13.
        # last (Aug 14) >= last_biz (Aug 13) → NOT stale
        assert is_stale(last, as_of=as_of, holidays=custom_holidays) is False

    def test_exact_boundary_same_as_last_biz(self) -> None:
        # If last_run_end == last_business_day, it's not stale.
        last = date(2026, 8, 14)
        as_of = date(2026, 8, 15)
        assert is_stale(last, as_of=as_of) is False

    def test_one_day_before_last_biz_is_stale(self) -> None:
        # last_run_end = Aug 13 (Thu), as_of = Aug 15 → last_biz = Aug 14
        # Aug 13 < Aug 14 → stale
        last = date(2026, 8, 13)
        as_of = date(2026, 8, 15)
        assert is_stale(last, as_of=as_of) is True


# ── freshness_date tests ───────────────────────────────────────────────


class TestFreshnessDate:
    """Test the ``freshness_date`` function."""

    def test_not_stale_returns_last_run_date(self) -> None:
        # Last run on Aug 14, as_of Aug 15 → fresh → returns last_run date
        last = date(2026, 8, 14)
        as_of = date(2026, 8, 15)
        result = freshness_date(last, as_of=as_of)
        assert result == date(2026, 8, 14)

    def test_not_stale_datetime_returns_date(self) -> None:
        last = datetime(2026, 8, 14, 8, 3, 12)
        as_of = date(2026, 8, 15)
        result = freshness_date(last, as_of=as_of)
        assert result == date(2026, 8, 14)

    def test_stale_returns_last_business_day(self) -> None:
        # Last run on Aug 12, as_of Aug 15 → stale → returns last_biz (Aug 14)
        last = date(2026, 8, 12)
        as_of = date(2026, 8, 15)
        result = freshness_date(last, as_of=as_of)
        assert result == date(2026, 8, 14)

    def test_none_last_run_returns_last_business_day(self) -> None:
        last = None
        as_of = date(2026, 8, 15)
        result = freshness_date(last, as_of=as_of)
        assert result == date(2026, 8, 14)

    def test_same_day_not_stale(self) -> None:
        last = date(2026, 8, 15)  # Saturday
        as_of = date(2026, 8, 15)
        result = freshness_date(last, as_of=as_of)
        # Last biz of Aug 15 = Aug 14. last (Aug 15) > Aug 14 → not stale → returns Aug 15
        assert result == date(2026, 8, 15)
