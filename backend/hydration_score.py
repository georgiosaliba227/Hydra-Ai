"""Unvalidated product rubric from recorded goal alignment and manual support.

This score does not estimate hydration status, physiological adequacy, or intake
requirements. Valid empty records differ from unavailable/malformed inputs.
"""
from datetime import date, datetime, timedelta, timezone as utc
from math import floor, isfinite
from zoneinfo import ZoneInfo

VERSION = "hydration-research-score-v1"
MAX_VOLUME_ML = 1_000_000_000
FACT_FIELDS = {"version", "local_date", "timezone", "goal_ml", "today_ml", "previous_days",
               "measurement_count", "components", "score", "research_only"}


class GoalRequired(ValueError):
    """A chosen goal is required; none is invented."""


def _number(value, lower=0, upper=MAX_VOLUME_ML):
    if type(value) not in (int, float) or not isfinite(value) or not lower <= value <= upper:
        raise ValueError("Score number outside supported bounds")
    return value


def _integer(value, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError("Score integer outside supported bounds")
    return value


def _derived(today_ml, previous_days, goal_ml, measurement_count):
    today_points = 50 * min(today_ml / goal_ml, 1)
    consistency_points = 30 * (sum(min(day["total_ml"] / goal_ml, 1) for day in previous_days) / 7)
    measurement_points = 20 * (min(measurement_count, 6) / 6)
    return {"components": {"today_points": today_points, "consistency_points": consistency_points,
                           "measurement_points": measurement_points},
            "score": floor(today_points + consistency_points + measurement_points + 0.5)}


def validate_facts(facts: dict) -> dict:
    """Exact aggregate shape; all dates, flags and derivations are recomputed."""
    try:
        if type(facts) is not dict or set(facts) != FACT_FIELDS:
            raise ValueError
        if facts["version"] != VERSION or facts["research_only"] is not True:
            raise ValueError
        if type(facts["timezone"]) is not str or not 1 <= len(facts["timezone"]) <= 128:
            raise ValueError
        ZoneInfo(facts["timezone"])
        if type(facts["local_date"]) is not str:
            raise ValueError
        through = date.fromisoformat(facts["local_date"])
        if through.isoformat() != facts["local_date"]:
            raise ValueError
        _integer(facts["goal_ml"], 100, 10_000)
        _integer(facts["measurement_count"], 0, 32)
        _number(facts["today_ml"])
        days = facts["previous_days"]
        if type(days) is not list or len(days) != 7:
            raise ValueError
        for offset, day in enumerate(days):
            if type(day) is not dict or set(day) != {"local_date", "total_ml", "logged"}:
                raise ValueError
            if day["local_date"] != (through - timedelta(days=7 - offset)).isoformat():
                raise ValueError
            _number(day["total_ml"])
            if type(day["logged"]) is not bool or day["logged"] != (day["total_ml"] > 0):
                raise ValueError
        components = facts["components"]
        if type(components) is not dict or set(components) != {"today_points", "consistency_points", "measurement_points"}:
            raise ValueError
        for key, maximum in (("today_points", 50), ("consistency_points", 30), ("measurement_points", 20)):
            _number(components[key], upper=maximum)
        _integer(facts["score"], 0, 100)
        expected = _derived(facts["today_ml"], days, facts["goal_ml"], facts["measurement_count"])
        if expected["components"] != components or expected["score"] != facts["score"]:
            raise ValueError
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ValueError("Hydration score facts failed validation") from None
    return facts


def build_facts(records: list[dict], goal_ml: int | None, timezone: str, measurement_count: int,
                *, now: datetime | None = None) -> dict:
    """Confirmed server logs only; future timestamps never contribute."""
    if goal_ml is None:
        raise GoalRequired("goal_required")
    _integer(goal_ml, 100, 10_000)
    _integer(measurement_count, 0, 32)
    if type(records) is not list or type(timezone) is not str or not 1 <= len(timezone) <= 128:
        raise ValueError("Complete records and timezone required")
    zone = ZoneInfo(timezone)
    now = now if now is not None else datetime.now(utc.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Aware clock required")
    through = now.astimezone(zone).date()
    totals = {through - timedelta(days=offset): 0 for offset in range(8)}
    for record in records:
        try:
            stamp = datetime.fromisoformat(record["consumed_at"])
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError
            volume = _number(record["consumed_ml"], lower=1, upper=5000)
        except (KeyError, TypeError, ValueError):
            raise ValueError("Unreadable confirmed beverage record") from None
        day = stamp.astimezone(zone).date()
        if stamp <= now and day in totals:
            totals[day] += volume
            _number(totals[day])
    days = [{"local_date": day.isoformat(), "total_ml": total, "logged": total > 0}
            for day, total in sorted(totals.items()) if day < through]
    facts = {"version": VERSION, "local_date": through.isoformat(), "timezone": timezone,
             "goal_ml": goal_ml, "today_ml": totals[through], "previous_days": days,
             "measurement_count": measurement_count, "research_only": True}
    facts.update(_derived(totals[through], days, goal_ml, measurement_count))
    return validate_facts(facts)
