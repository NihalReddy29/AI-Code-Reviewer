from __future__ import annotations

import hashlib
import hmac


def verify_signature(payload: bytes, signature: str | None, secret: str | None) -> bool:
    if not payload or not signature or not secret:
        return False
    expected = 'sha256=' + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
