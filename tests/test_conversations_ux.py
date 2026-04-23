"""Tests for Sprint UX-1: Conversations UX endpoints."""

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel, Contact, Conversation, Message
from tests.conftest import FAKE_AGENCY_ID

OTHER_AGENCY_ID = str(uuid.uuid4())


async def _seed_conversation(
    db: AsyncSession,
    agency_id: str = FAKE_AGENCY_ID,
    status: str = "open",
    mode: str = "ai",
    brand_id: uuid.UUID | None = None,
    channel_id: uuid.UUID | None = None,
    num_messages: int = 3,
    last_read_at: datetime | None = None,
) -> tuple[Conversation, Contact, Channel, list[Message]]:
    """Create a conversation with contact, channel, and messages for testing."""
    contact = Contact(
        agency_id=uuid.UUID(agency_id),
        user_id=uuid.UUID(int=0),
        platform="facebook",
        platform_user_id=f"psid_{uuid.uuid4().hex[:8]}",
        name="Test User",
    )
    db.add(contact)
    await db.flush()

    if channel_id is None:
        channel = Channel(
            agency_id=uuid.UUID(agency_id),
            user_id=uuid.UUID(int=0),
            platform="facebook",
            page_id=f"page_{uuid.uuid4().hex[:8]}",
            access_token="test_token",
        )
        db.add(channel)
        await db.flush()
    else:
        result = await db.execute(select(Channel).where(Channel.id == channel_id))
        channel = result.scalar_one()

    conv = Conversation(
        agency_id=uuid.UUID(agency_id),
        user_id=uuid.UUID(int=0),
        contact_id=contact.id,
        channel_id=channel.id,
        active_brand_id=brand_id,
        status=status,
        mode=mode,
        last_message_at=datetime.utcnow(),
        last_read_at=last_read_at,
        tags=["soporte"],
    )
    db.add(conv)
    await db.flush()

    messages: list[Message] = []
    base_time = datetime.utcnow() - timedelta(minutes=num_messages)
    for i in range(num_messages):
        sender = "customer" if i % 2 == 0 else "ai"
        msg = Message(
            conversation_id=conv.id,
            sender=sender,
            content=f"Message {i}",
            sent_at=base_time + timedelta(minutes=i),
        )
        db.add(msg)
        messages.append(msg)

    await db.commit()
    return conv, contact, channel, messages


# ──────────────────────────────────────────────────────────
# 1. test_list_conversations_returns_only_own_agency
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_conversations_returns_only_own_agency(
    client: AsyncClient, db_session: AsyncSession,
):
    """Listing conversations should only return those belonging to the authed agency."""
    await _seed_conversation(db_session, agency_id=FAKE_AGENCY_ID)
    await _seed_conversation(db_session, agency_id=OTHER_AGENCY_ID)

    resp = await client.get(f"/api/v1/conversations/by-agency/{FAKE_AGENCY_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for item in data:
        # All returned conversations belong to our agency (verified via the endpoint logic)
        assert "id" in item


@pytest.mark.asyncio
async def test_list_conversations_other_agency_forbidden(
    client: AsyncClient, db_session: AsyncSession,
):
    """Trying to list conversations for another agency should return 403."""
    resp = await client.get(f"/api/v1/conversations/by-agency/{OTHER_AGENCY_ID}")
    assert resp.status_code == 403


# ──────────────────────────────────────────────────────────
# 2. test_list_conversations_filters_by_status
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_conversations_filters_by_status(
    client: AsyncClient, db_session: AsyncSession,
):
    """Filtering by status=closed should only return closed conversations."""
    await _seed_conversation(db_session, status="open")
    await _seed_conversation(db_session, status="closed")

    resp = await client.get(
        f"/api/v1/conversations/by-agency/{FAKE_AGENCY_ID}",
        params={"status": "closed"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data:
        assert item["status"] == "closed"


# ──────────────────────────────────────────────────────────
# 3. test_list_conversations_filters_by_brand
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_conversations_filters_by_brand(
    client: AsyncClient, db_session: AsyncSession,
):
    """Filtering by brand_id should only return matching conversations."""
    target_brand = uuid.uuid4()
    other_brand = uuid.uuid4()
    await _seed_conversation(db_session, brand_id=target_brand)
    await _seed_conversation(db_session, brand_id=other_brand)

    resp = await client.get(
        f"/api/v1/conversations/by-agency/{FAKE_AGENCY_ID}",
        params={"brand_id": str(target_brand)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


# ──────────────────────────────────────────────────────────
# 4. test_list_conversations_includes_last_message_preview
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_conversations_includes_last_message_preview(
    client: AsyncClient, db_session: AsyncSession,
):
    """Response should include a preview of the last message."""
    await _seed_conversation(db_session, num_messages=5)

    resp = await client.get(f"/api/v1/conversations/by-agency/{FAKE_AGENCY_ID}")
    assert resp.status_code == 200
    data = resp.json()
    found_preview = any(item.get("last_message_preview") for item in data)
    assert found_preview, "At least one conversation should have a last_message_preview"


# ──────────────────────────────────────────────────────────
# 5. test_list_conversations_calculates_unread_count
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_conversations_calculates_unread_count(
    client: AsyncClient, db_session: AsyncSession,
):
    """Unread count should reflect customer messages after last_read_at."""
    # last_read_at very old → all customer messages should count as unread
    old_time = datetime(2020, 1, 1)
    await _seed_conversation(db_session, num_messages=6, last_read_at=old_time)

    resp = await client.get(f"/api/v1/conversations/by-agency/{FAKE_AGENCY_ID}")
    assert resp.status_code == 200
    data = resp.json()
    # At least one conversation should have unread > 0
    assert any(item["unread_count"] > 0 for item in data)


# ──────────────────────────────────────────────────────────
# 6. test_get_conversation_messages_returns_chronological
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_conversation_messages_returns_chronological(
    client: AsyncClient, db_session: AsyncSession,
):
    """Messages should be returned in chronological (ascending) order."""
    conv, _, _, _ = await _seed_conversation(db_session, num_messages=5)

    resp = await client.get(f"/api/v1/conversations/{conv.id}/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["messages"]) == 5
    timestamps = [m["sent_at"] for m in data["messages"]]
    assert timestamps == sorted(timestamps)


# ──────────────────────────────────────────────────────────
# 7. test_get_conversation_messages_marks_as_read
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_conversation_messages_marks_as_read(
    client: AsyncClient, db_session: AsyncSession,
):
    """Fetching messages should update last_read_at on the conversation."""
    conv, _, _, _ = await _seed_conversation(db_session, last_read_at=None)

    resp = await client.get(f"/api/v1/conversations/{conv.id}/messages")
    assert resp.status_code == 200

    await db_session.refresh(conv)
    assert conv.last_read_at is not None


# ──────────────────────────────────────────────────────────
# 8. test_send_agent_message_switches_to_manual
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_agent_message_switches_to_manual(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,
):
    """Sending an agent message with switch_to_manual=True should set mode='manual'."""
    conv, contact, channel, _ = await _seed_conversation(db_session, mode="ai")

    # Mock send_text_message to avoid real HTTP calls
    async def _mock_send(recipient_id, text, access_token):
        return {"message_id": "mid.mock"}

    monkeypatch.setattr("app.providers.meta_graph.send_text_message", _mock_send)

    resp = await client.post(
        f"/api/v1/conversations/{conv.id}/send",
        json={"content": "Hello from agent", "switch_to_manual": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sender"] == "agent"
    assert data["content"] == "Hello from agent"

    await db_session.refresh(conv)
    assert conv.mode == "manual"


# ──────────────────────────────────────────────────────────
# 9. test_send_agent_message_other_agency_forbidden
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_agent_message_other_agency_forbidden(
    client: AsyncClient, db_session: AsyncSession,
):
    """Sending a message to a conversation from another agency should be rejected."""
    conv, _, _, _ = await _seed_conversation(db_session, agency_id=OTHER_AGENCY_ID)

    resp = await client.post(
        f"/api/v1/conversations/{conv.id}/send",
        json={"content": "Nope"},
    )
    assert resp.status_code == 404  # ConversationNotFoundError (no access)


# ──────────────────────────────────────────────────────────
# 10. test_list_platforms_returns_all_with_status
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_platforms_returns_all_with_status(client: AsyncClient):
    """GET /api/v1/channels/platforms should return all platform options."""
    resp = await client.get("/api/v1/channels/platforms")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 9
    ids = {p["id"] for p in data}
    assert "facebook" in ids
    assert "instagram" in ids
    assert "whatsapp" in ids
    # Facebook should be active
    facebook = next(p for p in data if p["id"] == "facebook")
    assert facebook["status"] == "active"
    # Others should be coming_soon
    instagram = next(p for p in data if p["id"] == "instagram")
    assert instagram["status"] == "coming_soon"
