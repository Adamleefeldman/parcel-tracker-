"""Unit tests for the P1.5 demurrage day-math helper."""

from datetime import date

from app.services.demurrage_service import days_left


def test_days_left_within_free_time():
    # Arrived 2 days ago, 5 free days → 3 left.
    assert days_left(date(2026, 5, 1), 5, date(2026, 5, 3)) == 3


def test_days_left_arrival_today():
    assert days_left(date(2026, 5, 10), 5, date(2026, 5, 10)) == 5


def test_days_left_exactly_expired():
    assert days_left(date(2026, 5, 1), 5, date(2026, 5, 6)) == 0


def test_days_left_overdue_is_negative():
    # Arrived 9 days ago, 5 free days → 4 days overdue.
    assert days_left(date(2026, 5, 1), 5, date(2026, 5, 10)) == -4
