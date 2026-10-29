"""Strict confirmed-beverage wire validation; domain bounds are UI limits, not physiology."""
from datetime import datetime, timedelta, timezone
import re
from typing import Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .nutrition import lookup

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class CreateBeverageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, max_length=80, strict=True)
    consumed_ml: StrictInt = Field(ge=1, le=5000)
    consumed_at: datetime
    timezone: str = Field(min_length=1, max_length=128, strict=True)
    source: Literal["manual", "confirmed_recognition"]
    recognition_id: UUID | None = None
    product_id: str | None = Field(default=None, max_length=80, strict=True)
    container_ml: StrictInt | None = Field(default=None, ge=1, le=5000)

    @model_validator(mode="after")
    def confirmed_photo(self) -> Self:
        if self.source == "manual" and (self.product_id is not None or self.container_ml is not None or self.recognition_id is not None):
            raise ValueError("manual log cannot carry recognition fields")
        if self.source == "confirmed_recognition" and (self.container_ml is None or self.consumed_ml > self.container_ml):
            raise ValueError("confirm container and amount consumed")
        lookup(self.product_id, self.category)
        return self

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


class UpdateBeverageRequest(BaseModel):
    """Correct a confirmed log. Omitted fields keep their value; explicit nulls are rejected."""
    model_config = ConfigDict(extra="forbid")

    revision: StrictInt = Field(ge=1)
    category: str | None = Field(default=None, min_length=1, max_length=80, strict=True)
    consumed_ml: StrictInt | None = Field(default=None, ge=1, le=5000)
    consumed_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=128, strict=True)

    _clean_category = field_validator("category")(CreateBeverageRequest.clean_category.__func__)
    _rfc3339 = field_validator("consumed_at", mode="before")(CreateBeverageRequest.require_rfc3339.__func__)
    _instant = field_validator("consumed_at")(CreateBeverageRequest.validate_instant.__func__)
    _timezone = field_validator("timezone")(CreateBeverageRequest.valid_timezone.__func__)

    @model_validator(mode="after")
    def explicit_changes(self) -> Self:
        changed = self.model_fields_set - {"revision"}
        if not changed or any(getattr(self, name) is None for name in changed):
            raise ValueError("provide at least one non-null correction")
        return self


def utc_string(value: datetime) -> str:
    # Fixed-width canonical representation keeps SQLite/keyset ordering correct.
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
