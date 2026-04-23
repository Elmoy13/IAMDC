"""Symmetric encryption for sensitive data (access tokens)."""

from cryptography.fernet import Fernet

from app.config import settings


def _get_cipher() -> Fernet:
    return Fernet(settings.encryption_key.encode())


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a string. Returns base64 encoded ciphertext."""
    if not plaintext:
        return plaintext
    return _get_cipher().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a base64 encoded ciphertext."""
    if not ciphertext:
        return ciphertext
    return _get_cipher().decrypt(ciphertext.encode()).decode()
