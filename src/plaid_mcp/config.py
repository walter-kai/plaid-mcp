"""Environment configuration for the Plaid MCP gateway."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root when present.
# override=True so a project .env wins over placeholder env blocks in
# Claude Desktop / Cursor MCP configs (e.g. "your-client-id").
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env", override=True)
load_dotenv(override=False)


@dataclass(frozen=True)
class Settings:
    client_id: str
    secret: str
    env: str
    redirect_uri: str
    completion_uri: str
    webhook_uri: str
    items_path: Path
    items_gcs_uri: str | None
    web_host: str
    web_port: int
    upstream_key: str | None
    service_key: str | None
    public_base_url: str | None

    @property
    def plaid_host(self) -> str:
        mapping = {
            "sandbox": "https://sandbox.plaid.com",
            "development": "https://development.plaid.com",
            "production": "https://production.plaid.com",
        }
        try:
            return mapping[self.env]
        except KeyError as exc:
            raise ValueError(
                f"PLAID_ENV must be one of {sorted(mapping)}; got {self.env!r}"
            ) from exc


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _optional(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = os.getenv("PLAID_ENV", "production").strip().lower()
    items_raw = os.getenv("PLAID_ITEMS_PATH", "data/items.json").strip()
    items_path = Path(items_raw)
    if not items_path.is_absolute():
        items_path = _ROOT / items_path

    # Cloud Run sets PORT; prefer it when present.
    port_raw = os.getenv("PORT") or os.getenv("PLAID_WEB_PORT", "3000")

    # Prefer PLAID_SERVICE_KEY; accept legacy PLAID_MCP_UPSTREAM_KEY.
    service_key = _optional("PLAID_SERVICE_KEY") or _optional("PLAID_MCP_UPSTREAM_KEY")

    return Settings(
        client_id=_require("PLAID_CLIENT_ID"),
        secret=_require("PLAID_SECRET"),
        env=env,
        redirect_uri=_require("PLAID_REDIRECT_URI"),
        completion_uri=_require("PLAID_COMPLETION_URI"),
        webhook_uri=_require("PLAID_WEBHOOK_URI"),
        items_path=items_path,
        items_gcs_uri=_optional("PLAID_ITEMS_GCS_URI"),
        web_host=os.getenv("PLAID_WEB_HOST", "0.0.0.0").strip() or "0.0.0.0",
        web_port=int(port_raw),
        upstream_key=service_key,  # legacy alias
        service_key=service_key,
        public_base_url=_optional("PUBLIC_BASE_URL"),
    )
