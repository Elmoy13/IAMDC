"""Tests for Sprint CM-3: Single brand per channel."""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel, Contact, Conversation
from tests.conftest import FAKE_AGENCY_ID

BRAND_A = uuid.uuid4()
BRAND_B = uuid.uuid4()


async def _make_channel(
    db: AsyncSession,
    brand_id: uuid.UUID = BRAND_A,
    agency_id: str = FAKE_AGENCY_ID,
    page_id: str | None = None,
) -> Channel:
    channel = Channel(
        agency_id=uuid.UUID(agency_id),
        user_id=uuid.UUID(int=0),
        brand_id=brand_id,
        platform="facebook",
        page_id=page_id or f"page_{uuid.uuid4().hex[:8]}",
        access_token="test_token",
    )
    db.add(channel)
    await db.commit()
    return channel


async def _make_conversation(
    db: AsyncSession,
    channel: Channel,
    agency_id: str = FAKE_AGENCY_ID,
) -> Conversation:
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
        status="open",
        mode="ai",
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    await db.commit()
    return conv


# ──────────────────────────────────────────────────────────
# 1. Channel requires brand_id
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_channel_requires_brand_id(db_session: AsyncSession):
    """Creating a Channel without brand_id should fail."""
    from sqlalchemy.exc import IntegrityError

    channel = Channel(
        agency_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        platform="facebook",
        page_id="page_no_brand",
        access_token="tok",
    )
    db_session.add(channel)
    with pytest.raises((IntegrityError, Exception)):
        await db_session.flush()
    await db_session.rollback()


# ──────────────────────────────────────────────────────────
# 2. List channels filtered by brand
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_channels_by_agency_filters_by_brand(
    client: AsyncClient, db_session: AsyncSession,
):
    """GET channels should only return channels matching the brand_id filter."""
    await _make_channel(db_session, brand_id=BRAND_A)
    await _make_channel(db_session, brand_id=BRAND_B)

    resp = await client.get(
        f"/api/v1/channels/by-agency/{FAKE_AGENCY_ID}",
        params={"brand_id": str(BRAND_A)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for ch in data:
        assert ch["brand"]["id"] == str(BRAND_A)


# ──────────────────────────────────────────────────────────
# 3. List conversations filtered by brand
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_conversations_by_agency_filters_by_brand(
    client: AsyncClient, db_session: AsyncSession,
):
    """GET conversations should only return those whose channel.brand_id matches."""
    ch_a = await _make_channel(db_session, brand_id=BRAND_A)
    ch_b = await _make_channel(db_session, brand_id=BRAND_B)
    await _make_conversation(db_session, ch_a)
    await _make_conversation(db_session, ch_b)

    resp = await client.get(
        f"/api/v1/conversations/by-agency/{FAKE_AGENCY_ID}",
        params={"brand_id": str(BRAND_A)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["active_brand"]["id"] == str(BRAND_A)


# ──────────────────────────────────────────────────────────
# 4. OAuth callback creates channel with brand_id from state
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_oauth_connect_creates_channel_with_brand(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,
):
    """POST /oauth/meta/connect should create a Channel with brand_id."""
    from app.api.v1.oauth_meta import _oauth_states
    import datetime as dt
    from tests.conftest import FAKE_USER_ID

    user_id = FAKE_USER_ID
    agency_id = FAKE_AGENCY_ID
    brand_id = str(BRAND_A)
    page_id = "connect_page_123"

    # Seed the OAuth cache as if callback completed
    cache_key = f"user_token:{user_id}"
    _oauth_states[cache_key] = {
        "long_lived_user_token": "long_token",
        "pages": [
            {"id": page_id, "name": "My Page", "access_token": "page_tok", "category": "Brand"}
        ],
        "agency_id": agency_id,
        "brand_id": brand_id,
        "created_at": dt.datetime.now(dt.timezone.utc),
    }

    # Mock subscribe + handover
    async def _mock_subscribe(page_id, page_access_token):
        return True

    async def _mock_handover(page_id, page_access_token):
        return True

    monkeypatch.setattr("app.services.meta_oauth.subscribe_page_to_webhook", _mock_subscribe)
    monkeypatch.setattr("app.services.meta_oauth.handover_to_app", _mock_handover)

    # Override get_current_user to return matching user_id
    from app.middleware.auth import get_current_user
    from main import app

    def _fake_user():
        return {"user_id": user_id, "email": "t@t.com", "jwt_token": "t", "jwt_alg": "HS256"}

    app.dependency_overrides[get_current_user] = _fake_user

    resp = await client.post(
        "/api/v1/oauth/meta/connect",
        json={"page_id": page_id, "agency_id": agency_id, "brand_id": brand_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["brand_id"] == brand_id
    assert data["page_id"] == page_id

    # Verify channel in DB
    result = await db_session.execute(
        select(Channel).where(Channel.page_id == page_id)
    )
    channel = result.scalar_one()
    assert channel.brand_id == uuid.UUID(brand_id)


# ──────────────────────────────────────────────────────────
# 5. OAuth start validates brand belongs to agency
#    (403 handled by agency check, brand validation is app-level)
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_oauth_start_validates_agency(client: AsyncClient):
    """start_oauth should 403 if agency_id doesn't match authenticated user's agency."""
    other_agency = str(uuid.uuid4())
    resp = await client.get(
        "/api/v1/oauth/meta/start",
        params={"agency_id": other_agency, "brand_id": str(BRAND_A)},
    )
    assert resp.status_code == 403


# ──────────────────────────────────────────────────────────
# 6. Webhook creates conversation with brand from channel
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_creates_conversation_with_brand_from_channel(
    db_session: AsyncSession,
):
    """process_incoming_message should return brand_id = channel.brand_id."""
    from app.services.webhook_service import process_incoming_message

    channel = await _make_channel(db_session, brand_id=BRAND_A, page_id="page_webhook_brand")

    result = await process_incoming_message(
        db_session, page_id=channel.page_id, sender_id="psid_brand", message_text="hello",
    )
    assert result.brand_id == BRAND_A


# ──────────────────────────────────────────────────────────
# 7. auth_type=reauthenticate in authorize URL
# ──────────────────────────────────────────────────────────

def test_authorize_url_includes_reauthenticate():
    """build_authorize_url should include auth_type=reauthenticate."""
    from app.services.meta_oauth import build_authorize_url
    url = build_authorize_url(state="test_state")
    assert "auth_type=reauthenticate" in url
