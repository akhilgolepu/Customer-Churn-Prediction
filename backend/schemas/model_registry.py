from pydantic import BaseModel, Field


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
