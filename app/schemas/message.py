import uuid
from datetime import datetime

from pydantic import BaseModel


class AIReplyRequest(BaseModel):
    conversation_id: uuid.UUID
    message_text: str


class SendMessageRequest(BaseModel):
    conversation_id: uuid.UUID
    message_text: str


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender: str
    content: str | None
    sent_at: datetime

    model_config = {"from_attributes": True}
