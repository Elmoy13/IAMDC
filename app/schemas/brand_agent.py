"""Pydantic schemas for the Brand Agent endpoints."""
import uuid
from typing import Any

from pydantic import BaseModel, Field


class AgentChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class AgentChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message: str
    history: list[AgentChatMessage] = Field(default_factory=list)
    logo_url: str | None = None
    uploaded_images: list[str] | None = None


class AgentChatResponse(BaseModel):
    session_id: str
    reply: str
    presentation: list[dict[str, Any]] | None = None
    status: str  # "chatting" | "generating" | "done"
    extracted_config: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    creative_dna: dict[str, Any] | None = None


class ImageSearchRequest(BaseModel):
    query: str
    count: int = Field(default=5, ge=1, le=20)
    orientation: str = Field(default="landscape", pattern="^(landscape|portrait|squarish)$")


class ImageSearchResult(BaseModel):
    url: str
    thumb: str
    alt: str
    credit: str


class ImageSearchResponse(BaseModel):
    results: list[ImageSearchResult]


class FileUploadResponse(BaseModel):
    url: str
    filename: str
