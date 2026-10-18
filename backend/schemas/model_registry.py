from typing import Any

from pydantic import BaseModel, Field, model_validator


class ModelVersionRecord(BaseModel):
    id: str
    version: str
    metrics: dict[str, float]
    artifact_path: str
    status: str
    created_at: float


class RegisterModelRequest(BaseModel):
    version: str = Field(min_length=1)
    metrics: dict[str, float] = Field(default_factory=dict)
    artifact_path: str = Field(min_length=1)


class ShadowTestRequest(BaseModel):
    candidate_model_id: str = Field(min_length=1)


class PromoteModelRequest(BaseModel):
    candidate_model_id: str = Field(min_length=1)
    # Admin escape hatch: promote despite gate blockers. Requires a reason and is
    # recorded as a model_promotion_gate_overridden audit event.
    override_gate: bool = False
    override_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _reason_required_for_override(self):
        if self.override_gate and not (self.override_reason and self.override_reason.strip()):
            raise ValueError("override_reason is required when override_gate is true")
        return self


class RollbackRequest(BaseModel):
    target_model_id: str | None = None


class ModelRegistryResponse(BaseModel):
    active_model_id: str
    shadow_model_id: str | None
    versions: list[ModelVersionRecord]


class ModelMutationResponse(BaseModel):
    message: str
    active_model_id: str
    shadow_model_id: str | None
    validation: dict[str, Any] | None = None  # set by /promote: the gate result
