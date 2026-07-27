"""Unit tests for AES-GCM token crypto and store tenancy."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from plaid_mcp import store, token_crypto


@pytest.fixture(autouse=True)
def _reset_crypto(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    token_crypto.reset_key_cache()
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    monkeypatch.delenv("PLAID_TOKEN_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("PLAID_ITEMS_GCS_URI", raising=False)
    items = tmp_path / "items.json"
    monkeypatch.setenv("PLAID_ITEMS_PATH", str(items))
    # Settings is lru_cached — clear so path picks up.
    from plaid_mcp import config

    config.get_settings.cache_clear()
    yield
    token_crypto.reset_key_cache()
    config.get_settings.cache_clear()


def _set_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = os.urandom(32)
    encoded = base64.b64encode(key).decode("ascii")
    monkeypatch.setenv("PLAID_TOKEN_ENCRYPTION_KEY", encoded)
    token_crypto.reset_key_cache()
    return encoded


def test_encrypt_decrypt_round_trip(monkeypatch: pytest.MonkeyPatch):
    _set_key(monkeypatch)
    plain = "access-sandbox-test-token-value"
    encrypted = token_crypto.encrypt_token(plain)
    assert encrypted.startswith("enc:v1:")
    assert encrypted != plain
    assert token_crypto.decrypt_token(encrypted) == plain


def test_legacy_plaintext_passthrough(monkeypatch: pytest.MonkeyPatch):
    _set_key(monkeypatch)
    assert token_crypto.decrypt_token("access-legacy-plain") == "access-legacy-plain"


def test_upsert_encrypts_and_drops_public_token(monkeypatch: pytest.MonkeyPatch):
    _set_key(monkeypatch)
    record = store.upsert_item(
        item_id="item-1",
        access_token="access-sandbox-secret",
        client_user_id="alice@example.com",
        institution_id="ins_1",
        institution_name="Chase",
    )
    assert record["access_token"].startswith("enc:v1:")
    assert "public_token" not in record
    assert record["access_token_prefix"] == "access-sandbox-secret"[:24]
    assert store.get_access_token(item_id="item-1", client_user_id="alice@example.com") == (
        "access-sandbox-secret"
    )


def test_list_items_filters_by_user(monkeypatch: pytest.MonkeyPatch):
    _set_key(monkeypatch)
    store.upsert_item(
        item_id="a",
        access_token="access-a",
        client_user_id="alice@example.com",
    )
    store.upsert_item(
        item_id="b",
        access_token="access-b",
        client_user_id="bob@example.com",
    )
    alice = store.list_items(client_user_id="alice@example.com")
    assert [row["item_id"] for row in alice] == ["a"]
    assert alice[0]["access_token_prefix"] == "access-a"
    assert not alice[0]["access_token_prefix"].startswith("enc:")


def test_ownership_rejects_other_user(monkeypatch: pytest.MonkeyPatch):
    _set_key(monkeypatch)
    store.upsert_item(
        item_id="a",
        access_token="access-a",
        client_user_id="alice@example.com",
    )
    with pytest.raises(PermissionError):
        store.get_access_token(item_id="a", client_user_id="bob@example.com")


def test_delete_item_enforces_owner(monkeypatch: pytest.MonkeyPatch):
    _set_key(monkeypatch)
    store.upsert_item(
        item_id="a",
        access_token="access-a",
        client_user_id="alice@example.com",
    )
    with pytest.raises(PermissionError):
        store.delete_item("a", client_user_id="bob@example.com")
    store.delete_item("a", client_user_id="alice@example.com")
    assert store.get_item("a") is None


def test_lazy_plaintext_migration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _set_key(monkeypatch)
    path = Path(os.environ["PLAID_ITEMS_PATH"])
    path.write_text(
        json.dumps(
            {
                "items": {
                    "legacy": {
                        "item_id": "legacy",
                        "access_token": "access-legacy-plain",
                        "client_user_id": "alice@example.com",
                    }
                },
                "pending_links": {},
            }
        ),
        encoding="utf-8",
    )
    plain = store.get_access_token(item_id="legacy", client_user_id="alice@example.com")
    assert plain == "access-legacy-plain"
    stored = store.get_item("legacy")
    assert stored is not None
    assert stored["access_token"].startswith("enc:v1:")
