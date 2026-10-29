"""Hydration assistant boundary (ASSISTANT_API.md). Local rules only; questions are never stored or sent out."""
from datetime import date
import os
from pathlib import Path
from typing import Literal, Self

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai.assistant import SUGGESTED, VERSION, answers_for, match_topics, suggested_topics
from ai.hydration import CalculationError, summarize_day

QuestionId = Literal["coffee_counts", "creatine_water", "workout_sweat", "milk_vs_water", "daily_amount",
                     "logged_meaning", "heart_rate", "hot_weather"]
LIMITATIONS = ["Wellness information, not medical advice.",
               "Answers are reviewed text selected by local rules; no AI model wrote them.",
               "Logged volume is not a measurement of hydration status."]


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str | None = Field(default=None, max_length=1000, strict=True)
    question_id: QuestionId | None = None
    context_scope: Literal["none", "today_logged_total"] = "none"
    # recorded_wonder replays a saved, already-settled Wonder selection; it never dispatches.
    source: Literal["local_rules", "recorded_wonder"] = "local_rules"
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    timezone: str | None = Field(default=None, min_length=1, max_length=128, strict=True)

    @field_validator("question")
    @classmethod
    def trimmed(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not 1 <= len(value) <= 300:
                raise ValueError("question must be 1-300 characters")
        return value

    @model_validator(mode="after")
    def one_question_and_consistent_context(self) -> Self:
        if (self.question is None) == (self.question_id is None):
            raise ValueError("provide exactly one of question or question_id")
        if (self.context_scope == "today_logged_total") != (self.date is not None and self.timezone is not None):
            raise ValueError("date and timezone are required exactly when consenting to intake context")
        if self.context_scope == "none" and (self.date is not None or self.timezone is not None):
            raise ValueError("date and timezone are only accepted with intake context")
        if self.source == "recorded_wonder" and (self.question_id is None or self.context_scope != "none"):
            raise ValueError("recorded Wonder answers exist only for suggested questions without context")
        return self


def install_assistant_routes(app, to_engine) -> None:
    configured = os.getenv("HYDRA_WONDER_RESULTS_DIR", "")
    results_dir = Path(configured) if configured else None
    if results_dir is not None and not results_dir.is_absolute():
        raise ValueError("HYDRA_WONDER_RESULTS_DIR must be absolute")

    @app.get("/v1/assistant/questions")
    def suggested_questions():
        return {"version": VERSION, "questions": [{"id": key, "text": text} for key, (text, _) in SUGGESTED.items()]}

    @app.post("/v1/assistant")
    def ask(payload: AssistantRequest, request: Request):
        # A restricted developer credential never reads the owner's logs.
        if payload.context_scope != "none" and request.scope["state"].get("principal") != "owner":
            raise HTTPException(403, "forbidden")
        if payload.source == "recorded_wonder":
            from backend.wonder_results import load_recorded_answer
            try:
                recorded = load_recorded_answer(results_dir, payload.question_id) if results_dir else None
            except (OSError, ValueError):
                recorded = None
            if recorded is None:
                raise HTTPException(404, "not_found")
            return recorded
        topics = suggested_topics(payload.question_id) if payload.question_id else match_topics(payload.question)
        intake = None
        if payload.context_scope == "today_logged_total":
            try:
                local_date = date.fromisoformat(payload.date)
                logs = [to_engine(record) for record in request.app.state.repository.list_all("local-demo")]
                summary = summarize_day(logs, local_date, payload.timezone)
            except (ValueError, CalculationError):
                raise HTTPException(422, "invalid_request") from None
            intake = {"local_date": payload.date, "timezone": payload.timezone,
                      "beverage_total_ml": summary.beverage_total_ml,
                      "note": "Confirmed beverage volume, not a hydration measurement."}
        return {"version": VERSION, "question_id": payload.question_id, "topics": list(topics),
                "escalation": "urgent" in topics, "answers": answers_for(topics), "intake_context": intake,
                "provenance": {"mode": "local_rules", "provider": None, "model": None, "answer_origin": "reviewed_text"},
                "limitations": LIMITATIONS}
