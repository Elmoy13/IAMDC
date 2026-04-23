"""Pydantic schemas for Brands CRUD."""

from typing import Optional

from pydantic import BaseModel, Field


class CreateBrandRequest(BaseModel):
    name: str = Field(description="Brand display name")
    logo_b64: str = Field(default="", description="Logo as data URL or raw base64 PNG")
    primary_color: str = Field(default="#000000")
    secondary_color: str = Field(default="#ffffff")
    accent_color: str = Field(default="#888888")
    contrast_color: str = Field(default="#ffffff")
    font_family: str = Field(default="Montserrat")
    logo_analysis: Optional[dict] = None
    product_analysis: Optional[dict] = None
    extra_metadata: Optional[dict] = None


class UpdateBrandRequest(BaseModel):
    name: Optional[str] = None
    logo_b64: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    accent_color: Optional[str] = None
    contrast_color: Optional[str] = None
    font_family: Optional[str] = None
    logo_analysis: Optional[dict] = None
    product_analysis: Optional[dict] = None
    extra_metadata: Optional[dict] = None


class BrandResponse(BaseModel):
    id: str
    agency_id: str
    name: str
    logo_b64: str = ""
    primary_color: str = "#000000"
    secondary_color: str = "#ffffff"
    accent_color: str = "#888888"
    contrast_color: str = "#ffffff"
    font_family: str = "Montserrat"
    logo_analysis: Optional[dict] = None
    product_analysis: Optional[dict] = None
    extra_metadata: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BrandListResponse(BaseModel):
    brands: list[BrandResponse]
