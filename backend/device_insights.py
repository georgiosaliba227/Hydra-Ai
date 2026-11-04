"""Ephemeral phone aggregates and reviewed rules; no saved-state or provider access."""
from datetime import date, datetime, timedelta
import hashlib
import json
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from ai.assistant import VERSION as ASSISTANT_VERSION, answers_for, match_topics, suggested_topics
from .assistant_routes import AssistantRequest, LIMITATIONS
from .wonder_trends import (Day, DayTotal, INSIGHTS, Ml, Strict, TimeOfDay, WINDOW_DAYS,
                            build_aggregate_facts)

VERSION = "device-insights-v1"
Category = Literal["beer", "coffee", "energy", "juice", "milk", "other", "plant_milk",
                   "soda", "sports", "tea", "water", "wine"]


def valid_zone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("Invalid timezone") from None


class DeviceRequest(Strict):
    version: Literal["device-insights-v1"]
    source: Literal["on_device_summary"]
    consent_to_process: StrictBool

    @field_validator("consent_to_process")
    @classmethod
    def explicit_consent(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Explicit processing consent required")
        return value


class DeviceDay(DayTotal):
    @model_validator(mode="after")
    def count_matches_volume(self) -> Self:
        if (self.total_ml == 0) != (self.drinks == 0):
            raise ValueError("Drink count and volume must agree")
        return self


class DeviceCategory(Strict):
    category: Category
    total_ml: Annotated[int, Field(strict=True, gt=0, le=1_000_000_000)]


class DeviceTrendRequest(DeviceRequest):
    timezone: str = Field(min_length=1, max_length=128)
    through_date: Day
    days: list[DeviceDay] = Field(min_length=WINDOW_DAYS, max_length=WINDOW_DAYS)
    goal_ml: StrictInt | None = Field(default=None, ge=100, le=10_000)
    categories: list[DeviceCategory] = Field(max_length=12)
    time_of_day_ml: TimeOfDay

    @model_validator(mode="after")
    def consistent_window(self) -> Self:
        zone = valid_zone(self.timezone)
        try:
            through = date.fromisoformat(self.through_date)
            expected = [(through - timedelta(days=WINDOW_DAYS - 1 - i)).isoformat() for i in range(WINDOW_DAYS)]
        except (ValueError, OverflowError):
            raise ValueError("Invalid date window") from None
        if through > datetime.now(zone).date() or sorted(day.date for day in self.days) != expected:
            raise ValueError("Expected 14 consecutive local days ending on a nonfuture date")
        if len({item.category for item in self.categories}) != len(self.categories):
            raise ValueError("Categories must be unique")
        total = sum(day.total_ml for day in self.days)
        if (total > 1_000_000_000 or total != sum(item.total_ml for item in self.categories)
                or total != sum(self.time_of_day_ml.model_dump().values())):
            raise ValueError("Window totals must agree")
        return self


class DeviceAssistantRequest(DeviceRequest):
    request: AssistantRequest
    today_logged_total_ml: Ml | None = None

    @model_validator(mode="after")
    def phone_context_only(self) -> Self:
        request = self.request
        if request.source != "local_rules":
            raise ValueError("Only reviewed local rules are available")
        if request.context_scope == "today_logged_total":
            if self.today_logged_total_ml is None:
                raise ValueError("The phone total is required with intake context")
            try:
                date.fromisoformat(request.date)
                valid_zone(request.timezone)
            except (ValueError, TypeError):
                raise ValueError("Invalid intake context date or timezone") from None
        elif self.today_logged_total_ml is not None:
            raise ValueError("An intake total requires explicit context")
        return self


def deterministic_trends(facts: dict) -> dict:
    """Only factual text derived from the supplied, validated log summary."""
    total = sum(day["total_ml"] for day in facts["days"])
    logged_days = sum(day["drinks"] > 0 for day in facts["days"])
    texts = {
        "week_over_week": (f"Last 7 days: {facts['last_7_days']['total_ml']} mL logged; "
                           f"previous 7 days: {facts['previous_7_days']['total_ml']} mL."),
        "goal_progress": (f"Logged totals reached your {facts['goal_ml']} mL goal on "
                          f"{facts['goal_met_days_last_7']} of the last 7 days."),
        "logging_consistency": (f"Drinks were recorded on {logged_days} of these 14 days. "
                                "Days without logs are unknown intake."),
    }
    if facts["categories"]:
        top = facts["categories"][0]
        texts["beverage_mix"] = f"{top['category']}: {top['total_ml']} mL ({top['share_pct']}% of logged volume)."
    if total:
        period, volume = max(facts["time_of_day_ml"].items(), key=lambda item: item[1])
        texts["timing"] = f"The {period.removesuffix('_ml')} bucket contains {volume} mL of logged drinks."
    canonical = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return {"version": VERSION, "source": "on_device_summary", "facts": facts,
            "payload_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            "summary": (f"You logged {total} mL over {logged_days} recorded days in this 14-day window."
                        if total else "No drinks were recorded in this 14-day window."),
            "insights": [{"id": name, "title": INSIGHTS[name], "text": texts[name]}
                         for name in facts["applicable_insights"][:3]],
            "provenance": {"mode": "deterministic", "provider": None, "model": None,
                           "history_source": "on_device_summary", "storage": "ephemeral"}}


def install_device_insights_routes(app) -> None:
    @app.get("/v1/device-insights/capabilities")
    def capabilities():
        return {"version": VERSION, "history_source": "on_device_summary", "max_days": WINDOW_DAYS,
                "provider_dispatch": False}

    @app.post("/v1/device-insights/trends")
    def trends(payload: DeviceTrendRequest):
        facts = build_aggregate_facts([day.model_dump() for day in payload.days], payload.goal_ml,
            payload.timezone, date.fromisoformat(payload.through_date),
            categories=[item.model_dump() for item in payload.categories], time_of_day_ml=payload.time_of_day_ml.model_dump())
        return deterministic_trends(facts)

    @app.post("/v1/device-insights/assistant")
    def assistant(payload: DeviceAssistantRequest):
        question = payload.request
        topics = suggested_topics(question.question_id) if question.question_id else match_topics(question.question)
        intake = None
        if question.context_scope == "today_logged_total":
            intake = {"local_date": question.date, "timezone": question.timezone,
                      "beverage_total_ml": payload.today_logged_total_ml,
                      "note": "Confirmed beverage volume from this iPhone's log, not a hydration measurement."}
        return {"version": ASSISTANT_VERSION, "question_id": question.question_id, "topics": list(topics),
                "escalation": "urgent" in topics, "answers": answers_for(topics), "intake_context": intake,
                "provenance": {"mode": "local_rules", "provider": None, "model": None, "answer_origin": "reviewed_text"},
                "limitations": list(LIMITATIONS)}
