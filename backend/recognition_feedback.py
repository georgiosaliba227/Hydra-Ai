"""Consented correction descriptors; no provider calls or automatic training."""
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .recognition import AnalysisRequest, Candidate
from .meta_images import sanitized_jpeg

TRAINING_CONSENT = "hydra-training-photo-correction-v1"


def candidate_key(candidate: dict) -> str:
    fields = [candidate.get(name) or "" for name in ("brand", "product", "identity")]
    return hashlib.sha256(json.dumps([s.casefold().strip() for s in fields]).encode()).hexdigest()


def product_signature(candidate: dict) -> str | None:
    fields = [candidate.get(name) for name in ("brand", "product", "visible_label_text")]
    if not all(isinstance(s,str) and s.strip() for s in fields):
        return None
    return hashlib.sha256(json.dumps([" ".join(s.casefold().split()) for s in fields]).encode()).hexdigest()


class RecognitionFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$", strict=True)
    source_mode: Literal["mock", "meta_live"]
    original_candidate: Candidate
    remember_for_me: bool = Field(default=True, strict=True)
    share_for_training: bool = Field(default=False, strict=True)
    corrected_liquid_ml: StrictInt | None = Field(default=None, ge=1, le=5000)
    training_consent_version: Literal["hydra-training-photo-correction-v1"] | None = None
    training_photo_base64: str | None = Field(default=None, max_length=1_398_104, strict=True)

    @field_validator("original_candidate",mode="before")
    @classmethod
    def exclude_catalogue_enrichment(cls,value: object) -> object:
        # Catalogue values are server-owned enrichment, not a model prediction
        # or a training target supplied by the phone.
        if isinstance(value,dict):
            return {key:item for key,item in value.items() if key!="nutrition"}
        return value

    @model_validator(mode="after")
    def explicit_training_consent(self):
        if not self.share_for_training:
            if self.training_consent_version is not None or self.training_photo_base64 is not None:
                raise ValueError("Training photo requires separate explicit consent")
        else:
            if self.training_consent_version != TRAINING_CONSENT or self.training_photo_base64 is None:
                raise ValueError("Versioned consent and one owned photo required")
            image=AnalysisRequest(image_base64=self.training_photo_base64,photo_consent=True)
            if hashlib.sha256(sanitized_jpeg(image)).hexdigest()!=self.image_sha256:
                raise ValueError("Training image differs from the corrected image")
        return self

    def storage_value(self, identity: str, container: int, timestamp: str) -> dict:
        original=self.original_candidate.model_dump(exclude={"personal_correction"})
        result={"image_sha256":self.image_sha256,"source_mode":self.source_mode,
                "candidate_key":candidate_key(original),"product_signature":product_signature(original),
                "original_candidate":original,"corrected_identity":identity,
                "corrected_container_ml":container,"corrected_liquid_ml":self.corrected_liquid_ml,
                "created_at":timestamp,"remember_for_me":self.remember_for_me,
                "share_for_training":self.share_for_training,"synthetic":self.source_mode=="mock",
                "original_candidate_provenance":"user_submitted_reference",
                "corrected_details_provenance":"user_confirmed"}
        if self.share_for_training:
            image=AnalysisRequest(image_base64=self.training_photo_base64,photo_consent=True)
            result["photo_bytes"]=sanitized_jpeg(image)
            result["consent_version"]=TRAINING_CONSENT
            result["review_status"]="pending_review"
        return result
