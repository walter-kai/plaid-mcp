"""Shared Plaid API client helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.link_token_create_hosted_link import LinkTokenCreateHostedLink
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from plaid_mcp.config import Settings, get_settings


def _host_for_env(env: str) -> str:
    hosts = {
        "sandbox": plaid.Environment.Sandbox,
        "production": plaid.Environment.Production,
        # Development host still works; newer SDKs omit the constant.
        "development": "https://development.plaid.com",
    }
    try:
        return hosts[env]
    except KeyError as exc:
        raise ValueError(
            f"PLAID_ENV must be one of {sorted(hosts)}; got {env!r}"
        ) from exc


@lru_cache(maxsize=1)
def get_client(settings: Settings | None = None) -> plaid_api.PlaidApi:
    settings = settings or get_settings()
    configuration = plaid.Configuration(
        host=_host_for_env(settings.env),
        api_key={
            "clientId": settings.client_id,
            "secret": settings.secret,
        },
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def _to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _to_dict(value) for key, value in obj.items()}
    return obj


def normalize_countries(countries: list[str] | None = None, country: str | None = None) -> list[str]:
    """Resolve country selection to ``['US']``, ``['CA']``, or ``['US', 'CA']``."""
    allowed = {"US", "CA"}
    if country is not None:
        key = country.strip().upper()
        aliases = {
            "US": ["US"],
            "USA": ["US"],
            "UNITED STATES": ["US"],
            "CA": ["CA"],
            "CAN": ["CA"],
            "CANADA": ["CA"],
            "BOTH": ["US", "CA"],
            "ALL": ["US", "CA"],
            "US,CA": ["US", "CA"],
            "CA,US": ["CA", "US"],
        }
        if key not in aliases:
            raise ValueError(
                'country must be "US", "CA", or "both" '
                f"(got {country!r})"
            )
        return aliases[key]

    selected = [code.upper() for code in (countries or ["US", "CA"])]
    if not selected:
        raise ValueError("countries must include at least one of: US, CA")
    invalid = [code for code in selected if code not in allowed]
    if invalid:
        raise ValueError(
            f"Unsupported country code(s): {invalid}. Allowed: {sorted(allowed)}"
        )
    seen: set[str] = set()
    ordered: list[str] = []
    for code in selected:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


def create_hosted_link_session(
    *,
    client_user_id: str,
    label: str | None = None,
    countries: list[str] | None = None,
    country: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Create a Hosted Link session for Transactions.

    Prefer ``country="CA"`` for a Canada-only Link, ``country="US"`` for US-only,
    or ``country="both"`` (default) for US + Canada.
    """
    settings = settings or get_settings()
    client = get_client(settings)

    selected = normalize_countries(countries=countries, country=country)
    country_codes = [CountryCode(code) for code in selected]

    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Plaid MCP",
        country_codes=country_codes,
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=client_user_id),
        redirect_uri=settings.redirect_uri,
        webhook=settings.webhook_uri,
        hosted_link=LinkTokenCreateHostedLink(
            completion_redirect_uri=settings.completion_uri,
        ),
    )
    response = client.link_token_create(request)
    payload = _to_dict(response)
    return {
        "link_token": payload.get("link_token"),
        "hosted_link_url": payload.get("hosted_link_url"),
        "expiration": payload.get("expiration"),
        "request_id": payload.get("request_id"),
        "client_user_id": client_user_id,
        "label": label,
        "countries": selected,
        "env": settings.env,
        "canada_note": (
            None
            if "CA" not in selected
            else (
                "If only US banks appear, your Plaid Production account is likely "
                "not enabled for Canada. File a product-access ticket in the Plaid "
                "Dashboard, or try Sandbox with PLAID_ENV=sandbox first."
            )
        ),
    }


def exchange_public_token(public_token: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    client = get_client(settings)
    response = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    )
    return _to_dict(response)


def item_get(access_token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Fetch Item metadata (includes institution_id when available)."""
    settings = settings or get_settings()
    client = get_client(settings)
    response = client.item_get(ItemGetRequest(access_token=access_token))
    return _to_dict(response)


def institutions_get_by_id(
    institution_id: str,
    *,
    country_codes: list[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Resolve institution display name (and related metadata) by id."""
    settings = settings or get_settings()
    client = get_client(settings)
    codes = [CountryCode(code) for code in (country_codes or ["US", "CA"])]
    response = client.institutions_get_by_id(
        InstitutionsGetByIdRequest(
            institution_id=institution_id,
            country_codes=codes,
        )
    )
    return _to_dict(response)


def resolve_institution_metadata(
    access_token: str,
    settings: Settings | None = None,
) -> dict[str, str | None]:
    """Return institution_id / institution_name for an Item access token."""
    try:
        item_payload = item_get(access_token, settings=settings)
    except Exception:
        return {"institution_id": None, "institution_name": None}

    item = item_payload.get("item") if isinstance(item_payload, dict) else None
    institution_id = None
    if isinstance(item, dict):
        institution_id = item.get("institution_id")
    if not institution_id or not isinstance(institution_id, str):
        return {"institution_id": None, "institution_name": None}

    try:
        institution_payload = institutions_get_by_id(institution_id, settings=settings)
        institution = (
            institution_payload.get("institution")
            if isinstance(institution_payload, dict)
            else None
        )
        name = institution.get("name") if isinstance(institution, dict) else None
        return {
            "institution_id": institution_id,
            "institution_name": name if isinstance(name, str) else None,
        }
    except Exception:
        return {"institution_id": institution_id, "institution_name": None}


def item_remove(access_token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Revoke an Item access token via Plaid /item/remove."""
    settings = settings or get_settings()
    client = get_client(settings)
    response = client.item_remove(ItemRemoveRequest(access_token=access_token))
    return _to_dict(response)


def accounts_get(access_token: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    client = get_client(settings)
    response = client.accounts_get(AccountsGetRequest(access_token=access_token))
    return _to_dict(response)


def transactions_sync_all(
    access_token: str,
    *,
    cursor: str | None = None,
    count: int = 500,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Paginate /transactions/sync until has_more is false."""
    settings = settings or get_settings()
    client = get_client(settings)

    added: list[dict[str, Any]] = []
    modified: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    next_cursor = cursor or ""
    pages = 0
    has_more = True

    while has_more:
        kwargs: dict[str, Any] = {
            "access_token": access_token,
            "count": count,
        }
        if next_cursor:
            kwargs["cursor"] = next_cursor
        response = client.transactions_sync(TransactionsSyncRequest(**kwargs))
        payload = _to_dict(response)
        added.extend(payload.get("added") or [])
        modified.extend(payload.get("modified") or [])
        removed.extend(payload.get("removed") or [])
        next_cursor = payload.get("next_cursor") or next_cursor
        has_more = bool(payload.get("has_more"))
        pages += 1
        # Safety cap against runaway pagination.
        if pages >= 100:
            break

    return {
        "added": added,
        "modified": modified,
        "removed": removed,
        "next_cursor": next_cursor,
        "pages": pages,
        "has_more": has_more,
        "counts": {
            "added": len(added),
            "modified": len(modified),
            "removed": len(removed),
        },
    }
