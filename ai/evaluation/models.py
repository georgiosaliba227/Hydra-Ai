"""Versioned private evaluation inputs; reports contain aggregate metrics only."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,80}$")]
Fingerprint = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Signal = Literal["review_intake", "activity_context", "composition_missing", "supplement_uncertain",
                 "weather_context", "intake_pattern_context"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CameraTruth(StrictModel):
    # Empty labels mean the field is not identifiable from the approved image.
    categories: list[Label] = Field(default_factory=list, max_length=10)
    brands: list[Label] = Field(default_factory=list, max_length=10)
    container_ml: StrictInt | None = Field(default=None, ge=1, le=5000)
    capacity_visible: bool = False

    @model_validator(mode="after")
    def visible_capacity(self):
        if self.capacity_visible and self.container_ml is None:
            raise ValueError("Visible capacity requires measured or label-verified ground truth")
        return self


class HydrationTruth(StrictModel):
    required_signals: list[Signal] = Field(default_factory=list, max_length=6)
    allowed_signals: list[Signal] = Field(min_length=1, max_length=6)
    consistency_group: Identifier | None = None

    @model_validator(mode="after")
    def bounded_rubric(self):
        if not set(self.required_signals) <= set(self.allowed_signals):
            raise ValueError("Required signals must be allowed")
        if len(self.required_signals) != len(set(self.required_signals)) or len(self.allowed_signals) != len(set(self.allowed_signals)):
            raise ValueError("Duplicate rubric signals")
        return self


class EvaluationCase(StrictModel):
    case_id: Identifier
    purpose: Literal["camera", "hydration"]
    source: Literal["synthetic_fixture", "private_owned_input"]
    input_sha256: Fingerprint | None = None
    truth_reference: Label
    camera: CameraTruth | None = None
    hydration: HydrationTruth | None = None

    @model_validator(mode="after")
    def matching_truth(self):
        if (self.purpose == "camera") != (self.camera is not None) or (self.purpose == "hydration") != (self.hydration is not None):
            raise ValueError("Exactly one matching truth rubric is required")
        if self.source == "private_owned_input" and self.input_sha256 is None:
            raise ValueError("Private input must bind its exact prepared fingerprint")
        return self


class Dataset(StrictModel):
    version: Literal["meta-evaluation-dataset-v1"] = "meta-evaluation-dataset-v1"
    cases: list[EvaluationCase] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def distinct_cases(self):
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate case IDs")
        return self


class HumanReview(StrictModel):
    """Explicit review; absent labels remain unscored rather than assumed safe."""
    reviewer_reference: Label
    hallucinated_identity: bool | None = None
    invented_nutrition: bool | None = None
    unsupported_medical_claim: bool | None = None
    unsupported_numerical_recommendation: bool | None = None
    explanation_quality_1_to_5: StrictInt | None = Field(default=None, ge=1, le=5)


class Observation(StrictModel):
    case_id: Identifier
    mode: Literal["mock", "meta_live"]
    outcome: Literal["success", "error"]
    # Retain exact parsed gateway result privately to verify its canonical digest.
    result: dict | None = None
    attempt_id: str | None = Field(default=None, min_length=1, max_length=100)
    latency_ms: float | None = Field(default=None, ge=0, le=3_600_000, allow_inf_nan=False)
    human_review: HumanReview | None = None

    @model_validator(mode="after")
    def observation_shape(self):
        if (self.outcome == "success") != (self.result is not None):
            raise ValueError("Successful results and errors must be distinguished")
        if self.mode == "meta_live" and self.attempt_id is None:
            raise ValueError("Live claims require an authoritative attempt")
        if self.mode == "mock" and self.attempt_id is not None:
            raise ValueError("Mock results cannot claim a live attempt")
        return self


class ObservationFile(StrictModel):
    version: Literal["meta-evaluation-observations-v1"] = "meta-evaluation-observations-v1"
    observations: list[Observation] = Field(max_length=100)

    @model_validator(mode="after")
    def distinct_observations(self):
        if len({item.case_id for item in self.observations}) != len(self.observations):
            raise ValueError("One observation per case; repetitions need distinct case IDs")
        attempts = [item.attempt_id for item in self.observations if item.attempt_id is not None]
        if len(attempts) != len(set(attempts)):
            raise ValueError("A provider attempt cannot be counted twice")
        return self


class Usage(StrictModel):
    input_tokens: StrictInt = Field(ge=0)
    output_tokens: StrictInt = Field(ge=0)
    cached_tokens: StrictInt = Field(ge=0)
    total_tokens: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def consistent_usage(self):
        if self.cached_tokens > self.input_tokens or self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("Inconsistent usage")
        return self


class VerifiedEvidence(StrictModel):
    """Returned by a trusted read-only verifier, never accepted from result JSON."""
    account_id: Literal["georgiosaliba227", "aminealichaouche"]
    usage: Usage | None = None
    settled_cost_micro_usd: StrictInt | None = Field(default=None, ge=0)
    final_gross_micro_usd: StrictInt | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0, le=3_600_000, allow_inf_nan=False)
