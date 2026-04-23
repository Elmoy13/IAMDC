import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr("app.config.settings.encryption_key", key)


def test_encrypt_decrypt_roundtrip():
    from app.core.encryption import decrypt_secret, encrypt_secret

    original = "EAASiLFMyIBYBO_test_token_123"
    encrypted = encrypt_secret(original)
    assert encrypted != original
    assert decrypt_secret(encrypted) == original


def test_encrypt_empty_string():
    from app.core.encryption import encrypt_secret

    assert encrypt_secret("") == ""


def test_decrypt_empty_string():
    from app.core.encryption import decrypt_secret

    assert decrypt_secret("") == ""


def test_encrypt_special_characters():
    from app.core.encryption import decrypt_secret, encrypt_secret

    original = "tökéñ/with+special=chars&más"
    assert decrypt_secret(encrypt_secret(original)) == original


def test_encrypt_long_string():
    from app.core.encryption import decrypt_secret, encrypt_secret

    original = "A" * 5000
    assert decrypt_secret(encrypt_secret(original)) == original
