import uuid

from pydantic import BaseModel


class ConversationModeUpdate(BaseModel):
    mode: str  # "ai" | "manual"


class ConversationModeResponse(BaseModel):
    id: uuid.UUID
    mode: str | None
    status: str | None

    model_config = {"from_attributes": True}
