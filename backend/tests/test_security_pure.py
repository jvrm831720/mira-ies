"""Testes puros de crypto (sem deps pesadas)."""
import hashlib
import hmac
import secrets


def hash_api_key(raw_key: str, pepper: str = "test-pepper") -> str:
    return hmac.new(pepper.encode(), raw_key.encode(), hashlib.sha256).hexdigest()


def test_api_key_hash_stable():
    raw = "bkn_" + secrets.token_urlsafe(16)
    h1 = hash_api_key(raw)
    h2 = hash_api_key(raw)
    assert h1 == h2
    assert h1 != hash_api_key(raw + "x")


def test_webhook_hmac():
    body = b'{"a":1}'
    secret = "s3cret"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(sig, hmac.new(secret.encode(), body, hashlib.sha256).hexdigest())
