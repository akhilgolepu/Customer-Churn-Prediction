from pydantic import BaseModel, Field
from typing import Literal

Role = Literal["admin", "analyst", "viewer"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=3)
    password: str = Field(min_length=3)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    username: str
    role: Role
