"""Tests for Meta OAuth service, endpoints and channel management."""

import datetime as dt
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import Response

from app.services import meta_oauth
from app.services.channel_service import (
    create_channel_with_encrypted_token,
    delete_channel,
)
from app.db.models import Channel, ChannelBrand
from sqlalchemy import select


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr("app.config.settings.encryption_key", key)


@pytest.fixture(autouse=True)
def set_meta_config(monkeypatch):
    monkeypatch.setattr("app.config.settings.meta_app_id", "123456")
    monkeypatch.setattr("app.config.settings.meta_app_secret", "secret")
    monkeypatch.setattr(
        "app.config.settings.meta_oauth_redirect_uri",
        "https://api.bacachitofeliz.org/api/v1/oauth/meta/callback",
    )
    monkeypatch.setattr(
        "app.config.settings.meta_oauth_scopes",
        "pages_messaging,pages_manage_metadata",
    )


# ── 1. build_authorize_url ────────────────────────────────

def test_build_authorize_url_has_required_params():
    url = meta_oauth.build_authorize_url(state="abc123")
    assert "client_id=123456" in url
    assert "redirect_uri=" in url
    assert "state=abc123" in url
    assert "scope=" in url
    assert "response_type=code" in url
    assert url.startswith("https://www.facebook.com/v21.0/dialog/oauth?")


# ── 2. exchange_code_for_user_token success ───────────────

@pytest.mark.asyncio
async def test_exchange_code_for_user_token_success():
    mock_resp = AsyncMock(spec=Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "short_token_abc",
        "token_type": "bearer",
        "expires_in": 3600,
    }
    mock_resp.raise_for_status = AsyncMock()

    with patch("app.services.meta_oauth.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        token = await meta_oauth.exchange_code_for_user_token("code123")
        assert token == "short_token_abc"


# ── 3. exchange_code failure raises ───────────────────────

@pytest.mark.asyncio
async def test_exchange_code_failure_raises():
    mock_resp = AsyncMock(spec=Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"error": "invalid_code"}
    mock_resp.raise_for_status = AsyncMock()

    with patch("app.services.meta_oauth.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        with pytest.raises(ValueError, match="No access_token"):
            await meta_oauth.exchange_code_for_user_token("bad_code")


# ── 4. exchange_for_long_lived_returns_dict ───────────────

@pytest.mark.asyncio
async def test_exchange_for_long_lived_returns_dict():
    mock_resp = AsyncMock(spec=Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "long_lived_token_xyz",
        "token_type": "bearer",
        "expires_in": 5184000,
    }
    mock_resp.raise_for_status = AsyncMock()

    with patch("app.services.meta_oauth.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await meta_oauth.exchange_for_long_lived_user_token("short")
        assert result["access_token"] == "long_lived_token_xyz"
        assert result["expires_in"] == 5184000
        assert result["token_type"] == "bearer"


# ── 5. get_user_pages parses response ─────────────────────

@pytest.mark.asyncio
async def test_get_user_pages_parses_response():
    mock_resp = AsyncMock(spec=Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"id": "111", "name": "Page One", "access_token": "tok1", "category": "Brand"},
            {"id": "222", "name": "Page Two", "access_token": "tok2", "category": "Local Business"},
        ]
    }
    mock_resp.raise_for_status = AsyncMock()

    with patch("app.services.meta_oauth.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        pages = await meta_oauth.get_user_pages("long_token")
        assert len(pages) == 2
        assert pages[0]["id"] == "111"
        assert pages[1]["name"] == "Page Two"


# ── 6. subscribe_page success ─────────────────────────────

@pytest.mark.asyncio
async def test_subscribe_page_to_webhook_success():
    mock_resp = AsyncMock(spec=Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"success": True}
    mock_resp.raise_for_status = AsyncMock()

    with patch("app.services.meta_oauth.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        ok = await meta_oauth.subscribe_page_to_webhook("111", "page_token")
        assert ok is True


# ── 7. create_channel encrypts token ─────────────────────

@pytest.mark.asyncio
async def test_create_channel_with_encrypted_token_encrypts(db_session):
    agency_id = uuid.uuid4()
    user_id = uuid.uuid4()
    brand_id = uuid.uuid4()
    plaintext_token = "EAASiLFMyIBYBO_test_page_token"

    channel = await create_channel_with_encrypted_token(
        db=db_session,
        agency_id=agency_id,
        user_id=user_id,
        platform="facebook",
        page_id="page_123",
        page_name="Test Page",
        page_access_token=plaintext_token,
        brand_id=brand_id,
    )

    assert channel.access_token_encrypted is True
    assert channel.access_token != plaintext_token  # stored encrypted

    # Verify channel_brands was created
    result = await db_session.execute(
        select(ChannelBrand).where(ChannelBrand.channel_id == channel.id)
    )
    cb = result.scalar_one()
    assert cb.brand_id == brand_id
    assert cb.is_primary is True


# ── 8. create_channel is idempotent ───────────────────────

@pytest.mark.asyncio
async def test_create_channel_idempotent(db_session):
    agency_id = uuid.uuid4()
    user_id = uuid.uuid4()
    brand_id = uuid.uuid4()

    ch1 = await create_channel_with_encrypted_token(
        db=db_session,
        agency_id=agency_id,
        user_id=user_id,
        platform="facebook",
        page_id="page_idempotent",
        page_name="Page",
        page_access_token="token_v1",
        brand_id=brand_id,
    )
    ch2 = await create_channel_with_encrypted_token(
        db=db_session,
        agency_id=agency_id,
        user_id=user_id,
        platform="facebook",
        page_id="page_idempotent",
        page_name="Page",
        page_access_token="token_v2",
        brand_id=brand_id,
    )

    assert ch1.id == ch2.id  # same channel

    # Only 1 channel row for this page_id
    result = await db_session.execute(
        select(Channel).where(
            Channel.agency_id == agency_id,
            Channel.page_id == "page_idempotent",
        )
    )
    assert len(result.scalars().all()) == 1


# ── 9. delete_channel removes row ─────────────────────────

@pytest.mark.asyncio
async def test_delete_channel_removes_row(db_session):
    agency_id = uuid.uuid4()
    user_id = uuid.uuid4()
    brand_id = uuid.uuid4()

    channel = await create_channel_with_encrypted_token(
        db=db_session,
        agency_id=agency_id,
        user_id=user_id,
        platform="facebook",
        page_id="page_delete_test",
        page_name="Deletable",
        page_access_token="token_del",
        brand_id=brand_id,
    )
    channel_id = channel.id

    # Patch unsubscribe to avoid real HTTP call
    with patch(
        "app.services.meta_oauth.unsubscribe_page_from_webhook",
        new_callable=AsyncMock,
    ):
        await delete_channel(db_session, channel_id, agency_id)

    result = await db_session.execute(
        select(Channel).where(Channel.id == channel_id)
    )
    assert result.scalar_one_or_none() is None


# ── 10. callback with invalid state → 400 ────────────────

@pytest.mark.asyncio
async def test_oauth_callback_invalid_state_returns_400(client):
    resp = await client.get(
        "/api/v1/oauth/meta/callback",
        params={"code": "some_code", "state": "nonexistent_state"},
    )
    assert resp.status_code == 400
    assert "Invalid or expired state" in resp.json()["detail"]


# ── 11. callback with expired state → 400 ────────────────

@pytest.mark.asyncio
async def test_oauth_callback_expired_state_returns_400(client):
    from app.api.v1.oauth_meta import _oauth_states

    expired_state = "expired_state_abc"
    _oauth_states[expired_state] = {
        "user_id": "user-1",
        "agency_id": "agency-1",
        "brand_id": "brand-1",
        "created_at": dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=9999),
    }

    resp = await client.get(
        "/api/v1/oauth/meta/callback",
        params={"code": "some_code", "state": expired_state},
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()
