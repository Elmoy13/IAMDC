import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import FAKE_AGENCY_ID


@pytest.mark.asyncio
async def test_send_message_missing_conversation(client: AsyncClient):
    """POST /api/v1/messages/send should return 404 for non-existent conversation."""
    response = await client.post(
        "/api/v1/messages/send",
        json={
            "conversation_id": str(uuid.uuid4()),
            "message_text": "Hello!",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ai_reply_missing_conversation(client: AsyncClient):
    """POST /api/v1/messages/ai-reply should return 404 for non-existent conversation."""
    response = await client.post(
        "/api/v1/messages/ai-reply",
        json={
            "conversation_id": str(uuid.uuid4()),
            "message_text": "Hello!",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_message_requires_jwt(client_no_auth: AsyncClient):
    """POST /api/v1/messages/send without JWT should return 401."""
    response = await client_no_auth.post(
        "/api/v1/messages/send",
        json={
            "conversation_id": str(uuid.uuid4()),
            "message_text": "Hello!",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_send_message_forbids_other_agency(client: AsyncClient, db_session):
    """POST /api/v1/messages/send should return 403 for other agency's conversation."""
    from app.db.models import Channel, Contact, Conversation

    other_agency_id = uuid.uuid4()

    channel = Channel(
        agency_id=other_agency_id,
        user_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        platform="facebook",
        page_id="other_page",
        access_token="tok",
    )
    db_session.add(channel)
    await db_session.flush()

    contact = Contact(
        agency_id=other_agency_id,
        user_id=uuid.uuid4(),
        platform="facebook",
        platform_user_id="sender_1",
    )
    db_session.add(contact)
    await db_session.flush()

    conversation = Conversation(
        agency_id=other_agency_id,
        user_id=uuid.uuid4(),
        contact_id=contact.id,
        channel_id=channel.id,
        status="open",
        mode="ai",
    )
    db_session.add(conversation)
    await db_session.commit()

    response = await client.post(
        "/api/v1/messages/send",
        json={
            "conversation_id": str(conversation.id),
            "message_text": "Hello!",
        },
    )
    assert response.status_code == 403
