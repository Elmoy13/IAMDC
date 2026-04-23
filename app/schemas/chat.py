"""Pydantic schemas for chat and product analysis endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Product analysis
# ---------------------------------------------------------------------------

class ProductAnalyzeRequest(BaseModel):
    product_b64: str = Field(description="Product photo as data URL or raw base64 PNG")
    brand_id: Optional[str] = Field(
        default=None,
        description="If provided together with persist=True, saves product to brand_products.",
    )
    product_name: Optional[str] = Field(
        default=None,
        description="Optional display name for the product.",
    )
    persist: bool = Field(
        default=False,
        description="When True and brand_id is set, stores the product in brand_products.",
    )
    display_order: int = Field(
        default=0,
        description="Display order for the product within the brand.",
    )


class ProductAnalyzeResponse(BaseModel):
    product_type: str = ""
    product_description: str = ""
    key_features: list[str] = Field(default_factory=list)
    style: str = ""
    best_angles: str = ""
    ideal_settings: list[str] = Field(default_factory=list)
    photography_style: str = ""
    is_physical: bool = True
    is_digital: bool = False


# ---------------------------------------------------------------------------
# Brand vision analysis (extends existing color analysis)
# ---------------------------------------------------------------------------

class BrandVisionRequest(BaseModel):
    logo_b64: str = Field(description="Logo as data URL or raw base64 PNG")
    brand_id: Optional[str] = Field(
        default=None,
        description="If provided, persists analysis + logo to Supabase and storage.",
    )


class BrandVisionResponse(BaseModel):
    analysis: dict
    logo_url: Optional[str] = None
    persisted: bool = False


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    brand_context: dict | None = None
    product_context: dict | None = None
    brand_colors: dict | None = None
    language: str = Field(
        default="auto",
        pattern="^(es|en|auto)$",
        description='Chat language: "es", "en", or "auto" (detect from last user message).',
    )


class ChatResponse(BaseModel):
    reply: str
