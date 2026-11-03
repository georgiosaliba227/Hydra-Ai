"""Local trained Meta identity, with independent conservative metric label evidence."""
import re
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from .label_volume import label_capacity_ml, label_capacity_evidence
from .meta_images import sanitized_jpeg
from .recognition import AnalysisRequest, AnalysisResult, Candidate, LOCAL_MODEL, RecognitionUnavailable

ADAPTER_SHA256 = "71a361e862c5e1399b25098601fd7d974253a5f5d285e9ad194f90e38028d48f"
BASE_REVISION = "3e7677d7a40d348a3daba263a2b1c0aa41910710"
BASE_ID = "mlx-community/Muse-Glimmer-30B-4bit"
PROMPT_SHA256 = "0d9b19529813b8effc401618f529df66c1967f13238fde5d675a204b882defa1"


class LocalPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    image_id: str
    model_id: str
    base_revision: str
    adapter_sha256: str
    prompt_sha256: str
    outcome: str
    error: None
    brand: str | None = Field(max_length=200)
    product: str | None = Field(max_length=200)
    capacity_ml: StrictInt | None = Field(ge=1, le=20_000)
    latency_ms: StrictInt = Field(ge=0)


def local_result(prediction: dict, label_text: str) -> AnalysisResult:
    try:
        value = LocalPrediction.model_validate(prediction)
        if (value.model_id, value.base_revision, value.adapter_sha256, value.prompt_sha256, value.outcome) != (
                BASE_ID, BASE_REVISION, ADAPTER_SHA256, PROMPT_SHA256, "success"):
            raise ValueError("Local checkpoint mismatch")
        if not isinstance(label_text, str) or len(label_text) > 600:
            raise ValueError("Invalid label evidence")
        identity = " ".join(part.strip() for part in (value.brand, value.product) if part and part.strip()) or "Unknown beverage"
        # No multiplication or inference of per-container volume from package text.
        multipack = re.search(r"\b\d+\s*(?:[x×]|packs?\b|bottles?\b|cans?\b)", label_text, re.I)
        printed = None if multipack else label_capacity_ml(label_text)
        capacity = printed if printed is not None and printed == value.capacity_ml else None
        # Keep unit/size context only. OCR can also see private background text;
        # it must not become a durable recognition receipt or correction label.
        evidence = label_capacity_evidence(label_text,capacity)
        reasons = ["Local trained Meta suggestion; verify the brand, variant and printed size",
                   "Printed capacity is not measured liquid or the amount consumed"]
        if capacity is None:
            reasons.append("Printed size is unreadable, conflicting or not corroborated; enter the size yourself")
        candidate = Candidate(identity=identity, brand=value.brand, product=value.product,
                              visible_label_text=evidence or None, container_ml=capacity,
                              label_capacity_ml=capacity, confidence="medium" if capacity else "low",
                              uncertainty_reasons=reasons)
        return AnalysisResult(mode="local_meta", model=LOCAL_MODEL, recognition_id=str(uuid4()), candidates=[candidate])
    except (ValidationError, ValueError, TypeError):
        raise RecognitionUnavailable() from None


class LocalMetaRecognizer:
    def __init__(self, runtime):
        self.runtime = runtime

    @classmethod
    def from_environment(cls):
        from .local_meta_runtime import LocalMetaRuntime
        return cls(LocalMetaRuntime.from_environment())

    def analyze(self, image: AnalysisRequest) -> AnalysisResult:
        if image.mode != "local_meta" or image.photo_consent is not True:
            raise RecognitionUnavailable()
        try:
            prediction, label = self.runtime.recognize(sanitized_jpeg(image))
            return local_result(prediction, label)
        except Exception:
            # Private image/model error data never enters logs or the HTTP error.
            raise RecognitionUnavailable() from None
