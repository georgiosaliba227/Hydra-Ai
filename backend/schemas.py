"""Strict manual-log wire validation; domain bounds are UI limits, not physiology."""
from datetime import datetime, timedelta, timezone
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class CreateBeverageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, max_length=80, strict=True)
    consumed_ml: StrictInt = Field(ge=1, le=5000)
    consumed_at: datetime
    timezone: str = Field(min_length=1, max_length=128, strict=True)
    source: Literal["manual"]

    @field_validator("category")
    @classmethod
    def clean_category(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty category")
        return value

    @field_validator("consumed_at", mode="before")
    @classmethod
    def require_rfc3339(cls, value: object) -> object:
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value
        ):
            raise ValueError("explicit RFC3339 offset required")
        return value

    @field_validator("consumed_at")
    @classmethod
    def validate_instant(cls, value: datetime) -> datetime:
        try:
            utc = value.astimezone(timezone.utc)
        except (OverflowError, ValueError):
            raise ValueError("invalid instant") from None
        if utc.year < 2000 or utc > datetime.now(timezone.utc) + timedelta(seconds=60):
            raise ValueError("instant outside supported interval")
        return utc

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("invalid timezone") from None
        return value


def utc_string(value: datetime) -> str:
    # Fixed-width canonical representation keeps SQLite/keyset ordering correct.
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
