"""Tests for Sprint CM-2.5: Multi-brand Channel Routing."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel, ChannelBrand, Contact, Conversation, Message
from tests.conftest import FAKE_AGENCY_ID

OTHER_AGENCY_ID = str(uuid.uuid4())
BRAND_A = str(uuid.uuid4())
BRAND_B = str(uuid.uuid4())
BRAND_C = str(uuid.uuid4())


async def _seed_channel_with_brands(
    db: AsyncSession,
    agency_id: str = FAKE_AGENCY_ID,
    brands: list[dict] | None = None,
) -> tuple[Channel, list[ChannelBrand]]:
    """Create a channel with optional brand assignments."""
    channel = Channel(
        agency_id=uuid.UUID(agency_id),
        user_id=uuid.UUID(int=0),
        platform="facebook",
        page_id=f"page_{uuid.uuid4().hex[:8]}",
        access_token="test_token",
    )
    db.add(channel)
    await db.flush()

    cbs: list[ChannelBrand] = []
    if brands:
        for b in brands:
            cb = ChannelBrand(
                channel_id=channel.id,
                brand_id=uuid.UUID(b["brand_id"]),
                is_primary=b.get("is_primary", False),
                priority=b.get("priority", 1),
                trigger_keywords=b.get("trigger_keywords"),
            )
            db.add(cb)
            cbs.append(cb)

    await db.commit()
    return channel, cbs


async def _seed_conversation_with_brand(
    db: AsyncSession,
    channel: Channel,
    active_brand_id: uuid.UUID | None = None,
    agency_id: str = FAKE_AGENCY_ID,
) -> Conversation:
    """Create a conversation linked to a channel with an active brand."""
    contact = Contact(
        agency_id=uuid.UUID(agency_id),
        user_id=uuid.UUID(int=0),
        platform="facebook",
        platform_user_id=f"psid_{uuid.uuid4().hex[:8]}",
        name="Test User",
    )
    db.add(contact)
    await db.flush()

    conv = Conversation(
        agency_id=uuid.UUID(agency_id),
        user_id=uuid.UUID(int=0),
        contact_id=contact.id,
        channel_id=channel.id,
        active_brand_id=active_brand_id,
        status="open",
        mode="ai",
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    await db.commit()
    return conv


# ──────────────────────────────────────────────────────────
# 1. GET /channels/{channel_id}/brands — list brands
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_channel_brands(
    client: AsyncClient, db_session: AsyncSession,
):
    """GET brands for a channel returns the linked brands."""
    channel, _ = await _seed_channel_with_brands(db_session, brands=[
        {"brand_id": BRAND_A, "is_primary": True, "priority": 1},
        {"brand_id": BRAND_B, "is_primary": False, "priority": 2, "trigger_keywords": ["promo"]},
    ])
    resp = await client.get(
        f"/api/v1/channels/{channel.id}/brands",
        params={"agency_id": FAKE_AGENCY_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["brand_id"] == BRAND_A
    assert data[0]["is_primary"] is True


@pytest.mark.asyncio
async def test_list_channel_brands_other_agency_forbidden(
    client: AsyncClient, db_session: AsyncSession,
):
    """Listing brands for a channel of another agency returns 403."""
    channel, _ = await _seed_channel_with_brands(db_session, agency_id=OTHER_AGENCY_ID)
    resp = await client.get(
        f"/api/v1/channels/{channel.id}/brands",
        params={"agency_id": OTHER_AGENCY_ID},
    )
    assert resp.status_code == 403


# ──────────────────────────────────────────────────────────
# 2. PUT /channels/{channel_id}/brands — atomic replace
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_replace_channel_brands_atomic(
    client: AsyncClient, db_session: AsyncSession,
):
    """PUT replaces all brands atomically."""
    channel, _ = await _seed_channel_with_brands(db_session, brands=[
        {"brand_id": BRAND_A, "is_primary": True, "priority": 1},
    ])
    resp = await client.put(
        f"/api/v1/channels/{channel.id}/brands",
        params={"agency_id": FAKE_AGENCY_ID},
        json={"brands": [
            {"brand_id": BRAND_B, "is_primary": True, "priority": 1, "trigger_keywords": ["sale"]},
            {"brand_id": BRAND_C, "is_primary": False, "priority": 2},
        ]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    brand_ids = {b["brand_id"] for b in data}
    assert BRAND_A not in brand_ids
    assert BRAND_B in brand_ids
    assert BRAND_C in brand_ids


@pytest.mark.asyncio
async def test_replace_channel_brands_requires_one_primary(
    client: AsyncClient, db_session: AsyncSession,
):
    """PUT with zero or two primaries should fail with 422."""
    channel, _ = await _seed_channel_with_brands(db_session)
    # Two primaries
    resp = await client.put(
        f"/api/v1/channels/{channel.id}/brands",
        params={"agency_id": FAKE_AGENCY_ID},
        json={"brands": [
            {"brand_id": BRAND_A, "is_primary": True, "priority": 1},
            {"brand_id": BRAND_B, "is_primary": True, "priority": 2},
        ]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_replace_channel_brands_normalizes_keywords(
    client: AsyncClient, db_session: AsyncSession,
):
    """Trigger keywords should be lowercased, trimmed, and deduplicated."""
    channel, _ = await _seed_channel_with_brands(db_session)
    resp = await client.put(
        f"/api/v1/channels/{channel.id}/brands",
        params={"agency_id": FAKE_AGENCY_ID},
        json={"brands": [
            {
                "brand_id": BRAND_A,
                "is_primary": True,
                "priority": 1,
                "trigger_keywords": ["  Sale ", "SALE", "promo"],
            },
        ]},
    )
    assert resp.status_code == 200
    keywords = resp.json()[0]["trigger_keywords"]
    assert "sale" in keywords
    assert "promo" in keywords
    # Deduplicated — " Sale " and "SALE" should collapse to one "sale"
    assert keywords.count("sale") == 1


# ──────────────────────────────────────────────────────────
# 3. PATCH /conversations/{id}/active-brand
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_patch_active_brand_success(
    client: AsyncClient, db_session: AsyncSession,
):
    """PATCH active-brand with a valid brand updates the conversation."""
    channel, _ = await _seed_channel_with_brands(db_session, brands=[
        {"brand_id": BRAND_A, "is_primary": True, "priority": 1},
        {"brand_id": BRAND_B, "is_primary": False, "priority": 2},
    ])
    conv = await _seed_conversation_with_brand(db_session, channel, active_brand_id=uuid.UUID(BRAND_A))

    resp = await client.patch(
        f"/api/v1/conversations/{conv.id}/active-brand",
        json={"brand_id": BRAND_B},
    )
    assert resp.status_code == 200
    assert resp.json()["active_brand_id"] == BRAND_B


@pytest.mark.asyncio
async def test_patch_active_brand_invalid_brand(
    client: AsyncClient, db_session: AsyncSession,
):
    """PATCH with a brand not linked to the channel should return 422."""
    channel, _ = await _seed_channel_with_brands(db_session, brands=[
        {"brand_id": BRAND_A, "is_primary": True, "priority": 1},
    ])
    conv = await _seed_conversation_with_brand(db_session, channel)

    unlinked_brand = str(uuid.uuid4())
    resp = await client.patch(
        f"/api/v1/conversations/{conv.id}/active-brand",
        json={"brand_id": unlinked_brand},
    )
    assert resp.status_code == 422


# ──────────────────────────────────────────────────────────
# 4. Conversation list shows active_brand
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_conversation_list_shows_active_brand(
    client: AsyncClient, db_session: AsyncSession,
):
    """Conversation list should populate active_brand when set."""
    channel, _ = await _seed_channel_with_brands(db_session, brands=[
        {"brand_id": BRAND_A, "is_primary": True, "priority": 1},
    ])
    await _seed_conversation_with_brand(db_session, channel, active_brand_id=uuid.UUID(BRAND_A))

    resp = await client.get(f"/api/v1/conversations/by-agency/{FAKE_AGENCY_ID}")
    assert resp.status_code == 200
    data = resp.json()
    branded = [c for c in data if c.get("active_brand")]
    assert len(branded) >= 1
    assert branded[0]["active_brand"]["id"] == BRAND_A


# ──────────────────────────────────────────────────────────
# 5. Webhook routing — brand context preservation
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_preserves_existing_brand_context(
    db_session: AsyncSession,
):
    """If conversation already has a valid active_brand_id, it should be preserved."""
    from app.services.webhook_service import process_incoming_message

    channel, _ = await _seed_channel_with_brands(db_session, brands=[
        {"brand_id": BRAND_A, "is_primary": True, "priority": 1},
        {"brand_id": BRAND_B, "is_primary": False, "priority": 2, "trigger_keywords": ["promo"]},
    ])

    # First message — should resolve to primary brand
    result1 = await process_incoming_message(
        db_session, page_id=channel.page_id, sender_id="psid_001", message_text="hello",
    )
    assert str(result1.active_brand_id) == BRAND_A

    # Second message with keyword "promo" — but existing conversation has BRAND_A,
    # which is still valid, so context should be preserved
    result2 = await process_incoming_message(
        db_session, page_id=channel.page_id, sender_id="psid_001", message_text="tell me about promo",
    )
    assert str(result2.active_brand_id) == BRAND_A  # Preserved, not switched to BRAND_B


@pytest.mark.asyncio
async def test_webhook_no_brands_sets_none(
    db_session: AsyncSession,
):
    """Channel with no brands assigned should result in active_brand_id=None."""
    from app.services.webhook_service import process_incoming_message

    channel, _ = await _seed_channel_with_brands(db_session, brands=[])

    result = await process_incoming_message(
        db_session, page_id=channel.page_id, sender_id="psid_002", message_text="hello",
    )
    assert result.active_brand_id is None


@pytest.mark.asyncio
async def test_resolve_active_brand_keyword_match():
    """_resolve_active_brand returns keyword-matched brand with reason."""
    from app.services.webhook_service import _resolve_active_brand

    cb_primary = ChannelBrand(
        channel_id=uuid.uuid4(),
        brand_id=uuid.UUID(BRAND_A),
        is_primary=True,
        priority=1,
    )
    cb_promo = ChannelBrand(
        channel_id=cb_primary.channel_id,
        brand_id=uuid.UUID(BRAND_B),
        is_primary=False,
        priority=2,
        trigger_keywords=["promo", "sale"],
    )
    brand, reason = _resolve_active_brand([cb_primary, cb_promo], "I want a promo deal")
    assert brand.brand_id == uuid.UUID(BRAND_B)
    assert "keyword_match" in reason
