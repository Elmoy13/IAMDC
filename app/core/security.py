import hashlib
import hmac

from app.config import settings


def verify_meta_signature(payload: bytes, signature_header: str) -> bool:
    """Verify the X-Hub-Signature-256 header from Meta webhooks."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected_sig = signature_header.removeprefix("sha256=")
    computed_sig = hmac.new(
        settings.meta_app_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed_sig, expected_sig)
