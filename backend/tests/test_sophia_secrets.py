from app.services.connectors.sophia_secrets import decrypt_sophia_secret, encrypt_sophia_secret


def test_sophia_credentials_are_encrypted_and_round_trip(monkeypatch):
    from app.core import config

    class Settings:
        secret_key = "a-secure-test-secret-key-with-at-least-32-characters"

    monkeypatch.setattr(config, "get_settings", lambda: Settings())
    import app.services.connectors.sophia_secrets as secrets
    monkeypatch.setattr(secrets, "get_settings", lambda: Settings())

    encrypted = encrypt_sophia_secret("sophia-user-password")
    assert encrypted != "sophia-user-password"
    assert decrypt_sophia_secret(encrypted) == "sophia-user-password"
