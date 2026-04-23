import uuid
from datetime import datetime

from pydantic import BaseModel


class ConversationModeUpdate(BaseModel):
    mode: str  # "ai" | "manual"


class ConversationModeResponse(BaseModel):
    id: uuid.UUID
    mode: str | None
    status: str | None

    model_config = {"from_attributes": True}


# ── UX Sprint schemas ────────────────────────────────────

class ContactInfo(BaseModel):
    id: uuid.UUID
    platform: str
    platform_user_id: str
    name: str | None = None
    profile_picture_url: str | None = None


class ChannelInfo(BaseModel):
    id: uuid.UUID
    platform: str
    page_id: str | None = None
    page_name: str | None = None


class BrandInfo(BaseModel):
    id: uuid.UUID
    name: str


class ConversationListItem(BaseModel):
    id: uuid.UUID
    status: str
    mode: str
    last_message_at: datetime | None = None
    last_message_preview: str | None = None
    last_message_sender: str | None = None
    unread_count: int
    contact: ContactInfo
    channel: ChannelInfo
    active_brand: BrandInfo | None = None
    tags: list[str]


class MessageItem(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender: str
    content: str
    sent_at: datetime
    ai_suggestion: str | None = None

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    id: uuid.UUID
    status: str
    mode: str
    contact: ContactInfo
    channel: ChannelInfo
    active_brand: BrandInfo | None = None
    messages: list[MessageItem]
    total_messages: int


class SendMessageRequest(BaseModel):
    content: str
    switch_to_manual: bool = True
