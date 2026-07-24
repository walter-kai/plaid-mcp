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
    web_host: str
    web_port: int
    public_base_url: str
    google_oauth_client_id: str
    google_oauth_client_secret: str
    jwt_signing_key: str
    allowed_emails: frozenset[str]
    items_gcs_uri: str

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


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = os.getenv("PLAID_ENV", "production").strip().lower()
    items_raw = os.getenv("PLAID_ITEMS_PATH", "data/items.json").strip()
    items_path = Path(items_raw)
    if not items_path.is_absolute():
        items_path = _ROOT / items_path

    web_port = int(os.getenv("PLAID_WEB_PORT", "3000"))
    public_base = _optional("PUBLIC_BASE_URL")
    if not public_base:
        # Local default: ngrok/public URL should override this in .env for Plaid.
        public_base = f"http://127.0.0.1:{web_port}"

    allowed_raw = _optional("ALLOWED_EMAILS")
    allowed = frozenset(
        email.strip().lower()
        for email in allowed_raw.split(",")
        if email.strip()
    )

    return Settings(
        client_id=_require("PLAID_CLIENT_ID"),
        secret=_require("PLAID_SECRET"),
        env=env,
        redirect_uri=_require("PLAID_REDIRECT_URI"),
        completion_uri=_require("PLAID_COMPLETION_URI"),
        webhook_uri=_require("PLAID_WEBHOOK_URI"),
        items_path=items_path,
        web_host=os.getenv("PLAID_WEB_HOST", "0.0.0.0").strip() or "0.0.0.0",
        web_port=web_port,
        public_base_url=public_base.rstrip("/"),
        google_oauth_client_id=_optional("GOOGLE_OAUTH_CLIENT_ID"),
        google_oauth_client_secret=_optional("GOOGLE_OAUTH_CLIENT_SECRET"),
        jwt_signing_key=_optional("JWT_SIGNING_KEY"),
        allowed_emails=allowed,
        items_gcs_uri=_optional("PLAID_ITEMS_GCS_URI"),
    )
