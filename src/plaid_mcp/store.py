"""Persistence for Plaid Items / access tokens (local JSON or GCS)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from plaid_mcp.config import get_settings

_lock = threading.Lock()
_gcs_client = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path() -> Path:
    return get_settings().items_path


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path:
        raise ValueError(
            f"PLAID_ITEMS_GCS_URI must look like gs://bucket/path.json; got {uri!r}"
        )
    bucket = parsed.netloc
    blob = parsed.path.lstrip("/")
    if not blob:
        raise ValueError(f"PLAID_ITEMS_GCS_URI missing object path: {uri!r}")
    return bucket, blob


def _get_gcs_blob():
    global _gcs_client
    settings = get_settings()
    if not settings.items_gcs_uri:
        return None
    if _gcs_client is None:
        from google.cloud import storage  # lazy import

        _gcs_client = storage.Client()
    bucket_name, blob_name = _parse_gcs_uri(settings.items_gcs_uri)
    return _gcs_client.bucket(bucket_name).blob(blob_name)


def _empty() -> dict[str, Any]:
    return {"items": {}, "pending_links": {}}


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    if "items" not in data or not isinstance(data["items"], dict):
        data["items"] = {}
    if "pending_links" not in data or not isinstance(data.get("pending_links"), dict):
        data["pending_links"] = data.get("pending_links") or {}
        if not isinstance(data["pending_links"], dict):
            data["pending_links"] = {}
    return data


def _read() -> dict[str, Any]:
    blob = _get_gcs_blob()
    if blob is not None:
        if not blob.exists():
            return _empty()
        data = json.loads(blob.download_as_text(encoding="utf-8"))
        return _normalize(data if isinstance(data, dict) else _empty())

    path = _path()
    if not path.exists():
        return _empty()
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return _normalize(data if isinstance(data, dict) else _empty())


def _write(data: dict[str, Any]) -> None:
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    blob = _get_gcs_blob()
    if blob is not None:
        blob.upload_from_string(payload, content_type="application/json")
        return

    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(payload)
    tmp.replace(path)


def list_items() -> list[dict[str, Any]]:
    with _lock:
        data = _read()
    items = []
    for item_id, record in data["items"].items():
        items.append(
            {
                "item_id": item_id,
                "label": record.get("label"),
                "client_user_id": record.get("client_user_id"),
                "institution_id": record.get("institution_id"),
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
                # Expose a redacted hint only in list views.
                "access_token_prefix": (record.get("access_token") or "")[:24],
            }
        )
    items.sort(key=lambda row: row.get("updated_at") or "", reverse=True)
    return items


def get_item(item_id: str) -> dict[str, Any] | None:
    with _lock:
        data = _read()
        record = data["items"].get(item_id)
        return dict(record) if record else None


def get_access_token(*, item_id: str | None = None, access_token: str | None = None) -> str:
    if access_token:
        return access_token
    if not item_id:
        raise ValueError("Provide item_id or access_token")
    record = get_item(item_id)
    if not record or not record.get("access_token"):
        raise KeyError(f"Unknown item_id: {item_id}")
    return str(record["access_token"])


def upsert_item(
    *,
    item_id: str,
    access_token: str,
    label: str | None = None,
    client_user_id: str | None = None,
    institution_id: str | None = None,
    public_token: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    with _lock:
        data = _read()
        existing = data["items"].get(item_id, {})
        now = _now()
        record = {
            **existing,
            "item_id": item_id,
            "access_token": access_token,
            "label": label if label is not None else existing.get("label"),
            "client_user_id": client_user_id
            if client_user_id is not None
            else existing.get("client_user_id"),
            "institution_id": institution_id
            if institution_id is not None
            else existing.get("institution_id"),
            "public_token": public_token
            if public_token is not None
            else existing.get("public_token"),
            "request_id": request_id
            if request_id is not None
            else existing.get("request_id"),
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
        }
        data["items"][item_id] = record
        _write(data)
        return dict(record)


def remember_pending_link(
    *,
    link_token: str,
    client_user_id: str,
    label: str | None = None,
) -> None:
    """Store metadata so webhook exchange can attach a label/user id."""
    with _lock:
        data = _read()
        pending = data.setdefault("pending_links", {})
        pending[link_token] = {
            "client_user_id": client_user_id,
            "label": label,
            "created_at": _now(),
        }
        # Keep only the most recent few pending sessions.
        if len(pending) > 20:
            ordered = sorted(
                pending.items(),
                key=lambda pair: pair[1].get("created_at") or "",
            )
            for key, _ in ordered[:-20]:
                pending.pop(key, None)
        _write(data)


def pop_pending_link(link_token: str | None) -> dict[str, Any] | None:
    if not link_token:
        return None
    with _lock:
        data = _read()
        pending = data.get("pending_links") or {}
        record = pending.pop(link_token, None)
        if record is not None:
            data["pending_links"] = pending
            _write(data)
        return dict(record) if record else None
