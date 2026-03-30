from pydantic import BaseModel, Field


class ErrorModel(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class PaginationMeta(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)


class MessageResponse(BaseModel):
    message: str
