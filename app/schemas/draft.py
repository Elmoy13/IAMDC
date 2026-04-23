"""Pydantic schemas for parrilla_drafts CRUD."""

from typing import Optional

from pydantic import BaseModel, Field


class CreateDraftRequest(BaseModel):
    brand_id: Optional[str] = None
    title: Optional[str] = None


class UpdateDraftRequest(BaseModel):
    chat_messages: Optional[list] = None
    config: Optional[dict] = None
    selected_product_ids: Optional[list[str]] = None
    title: Optional[str] = None
    last_step: Optional[str] = None
    brand_id: Optional[str] = None
