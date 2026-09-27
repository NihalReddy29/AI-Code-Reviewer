from app.utils.security import verify_signature


def test_verify_signature_rejects_missing_values() -> None:
    assert verify_signature(b'{"ok": true}', None, None) is False


def test_verify_signature_rejects_invalid_payload() -> None:
    assert verify_signature(b'{}', 'sha256=bad', 'secret') is False
