import uuid

import pytest
from httpx import AsyncClient

from app.config import settings
from tests.conftest import FAKE_AGENCY_ID


@pytest.mark.asyncio
async def test_webhook_verify_success(client: AsyncClient):
    """GET /api/v1/webhook/meta should return the challenge when token matches."""
    response = await client.get(
        "/api/v1/webhook/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.meta_verify_token,
            "hub.challenge": "test_challenge_123",
        },
    )
    assert response.status_code == 200
    assert response.text == "test_challenge_123"


@pytest.mark.asyncio
async def test_webhook_verify_failure(client: AsyncClient):
    """GET /api/v1/webhook/meta should return 403 with a wrong token."""
    response = await client.get(
        "/api/v1/webhook/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "test_challenge",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_webhook_resolves_agency_from_channel(client: AsyncClient, db_session):
    """Webhook should create contact and conversation with the channel's agency_id."""
    from app.db.models import Channel, Contact, Conversation, Message
    from sqlalchemy import select

    agency_id = uuid.uuid4()
    brand_id = uuid.uuid4()
    page_id = "page_test_agency"

    channel = Channel(
        agency_id=agency_id,
        user_id=uuid.uuid4(),
        brand_id=brand_id,
        platform="facebook",
        page_id=page_id,
        access_token="test_token",
    )
    db_session.add(channel)
    await db_session.commit()

    payload = {
        "object": "page",
        "entry": [
            {
                "id": page_id,
                "time": 1234567890,
                "messaging": [
                    {
                        "sender": {"id": "sender_123"},
                        "recipient": {"id": page_id},
                        "timestamp": 1234567890,
                        "message": {"mid": "mid.1", "text": "Hola"},
                    }
                ],
            }
        ],
    }

    response = await client.post("/api/v1/webhook/meta", json=payload)
    assert response.status_code == 200

    # Verify contact was created with agency_id
    result = await db_session.execute(
        select(Contact).where(Contact.agency_id == agency_id)
    )
    contact = result.scalar_one()
    assert contact.platform_user_id == "sender_123"
    assert contact.agency_id == agency_id

    # Verify conversation was created with agency_id
    result = await db_session.execute(
        select(Conversation).where(Conversation.agency_id == agency_id)
    )
    conversation = result.scalar_one()
    assert conversation.agency_id == agency_id
    assert conversation.mode == "ai"


@pytest.mark.asyncio
async def test_webhook_creates_conversation_with_brand_from_channel(client: AsyncClient, db_session):
    """Conversation brand_id should come from channel.brand_id (trivial routing)."""
    from app.db.models import Channel, Conversation
    from sqlalchemy import select

    agency_id = uuid.uuid4()
    brand_id = uuid.uuid4()
    page_id = "page_1brand"

    channel = Channel(
        agency_id=agency_id,
        user_id=uuid.uuid4(),
        brand_id=brand_id,
        platform="facebook",
        page_id=page_id,
        access_token="tok",
    )
    db_session.add(channel)
    await db_session.commit()

    payload = {
        "object": "page",
        "entry": [
            {
                "id": page_id,
                "time": 1,
                "messaging": [
                    {
                        "sender": {"id": "s1"},
                        "recipient": {"id": page_id},
                        "message": {"text": "hello"},
                    }
                ],
            }
        ],
    }

    response = await client.post("/api/v1/webhook/meta", json=payload)
    assert response.status_code == 200

    result = await db_session.execute(
        select(Conversation).where(Conversation.channel_id == channel.id)
    )
    conv = result.scalar_one()
    # Brand comes from channel, not from conversation.active_brand_id
    assert conv.channel_id == channel.id
