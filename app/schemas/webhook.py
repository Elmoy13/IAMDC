from pydantic import BaseModel


# ── Meta Webhook Verification (GET) ─────────────────────
class WebhookVerifyQuery(BaseModel):
    hub_mode: str
    hub_verify_token: str
    hub_challenge: str


# ── Meta Webhook Payload (POST) ─────────────────────────
class MetaMessageSender(BaseModel):
    id: str


class MetaMessageRecipient(BaseModel):
    id: str


class MetaMessagePayload(BaseModel):
    mid: str | None = None
    text: str | None = None


class MetaMessagingEntry(BaseModel):
    sender: MetaMessageSender
    recipient: MetaMessageRecipient
    timestamp: int | None = None
    message: MetaMessagePayload | None = None


class MetaEntryChange(BaseModel):
    id: str
    time: int | None = None
    messaging: list[MetaMessagingEntry] = []


class MetaWebhookBody(BaseModel):
    object: str | None = None
    entry: list[MetaEntryChange] = []
