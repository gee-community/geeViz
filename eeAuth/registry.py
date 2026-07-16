"""Multi-tenant Earth Engine service-account registry.

Loads service-account credentials from env vars at startup and provides
per-tenant token minting with caching. Used by the proxy server to pick
which SA to authenticate as for each incoming request.

Env-var convention:

- ``GEE_SERVICE_ACCOUNT_B64`` — the default tenant (legacy name kept
  for backward compatibility).
- ``GEE_<NAME>_SERVICE_ACCOUNT`` — additional tenants. The middle
  capture group becomes the tenant id, lowercased. So
  ``GEE_TRAINING_SERVICE_ACCOUNT`` registers as the ``training`` tenant.

Each value is base64-encoded service-account JSON. To add a tenant:

1. Create the SA, register it with Earth Engine.
2. Base64-encode the JSON key file.
3. Set ``GEE_<NAME>_SERVICE_ACCOUNT=<b64>`` in your env / deploy.

Tokens are minted on demand and cached. The registry is thread-safe;
concurrent requests for the same tenant share one in-flight refresh
via the lock.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# SA tokens are good for ~1h; re-mint every 50 min so handoffs are smooth.
_TOKEN_TTL_SEC = 50 * 60

DEFAULT_TENANT = "default"

# ``GEE_<NAME>_SERVICE_ACCOUNT`` — NAME may contain letters/digits/underscores.
# Excludes the legacy ``GEE_SERVICE_ACCOUNT_B64`` since that's handled
# separately (we don't want it loaded as tenant ``""`` or ``b64``).
_TENANT_ENV_RE = re.compile(r"^GEE_([A-Z0-9_]+)_SERVICE_ACCOUNT$")


def _decode_sa_json(b64: str) -> dict:
    """Decode a base64-encoded service-account JSON blob. Raises if the
    content isn't valid base64 OR isn't valid JSON, so misconfigured env
    vars fail loudly at startup rather than silently."""
    raw = base64.b64decode(b64)
    return json.loads(raw)


class SARegistry:
    """Per-tenant service-account credentials + cached access tokens."""

    def __init__(self) -> None:
        self._sa_json: dict[str, dict] = {}
        self._creds: dict[str, object] = {}
        self._tokens: dict[str, dict] = {}  # tenant -> {data, fetched_at}
        self._lock = threading.Lock()
        self._load_from_env()

    def _load_from_env(self) -> None:
        """Scan ``os.environ`` for SA entries. Idempotent — safe to call
        multiple times; later calls re-read env (useful in tests)."""
        # Legacy default SA — keep working with existing deployments.
        default_b64 = os.environ.get("GEE_SERVICE_ACCOUNT_B64", "")
        if default_b64:
            try:
                self._sa_json[DEFAULT_TENANT] = _decode_sa_json(default_b64)
                logger.info(
                    "SA registry: loaded default tenant (sa=%s, project=%s)",
                    self._sa_json[DEFAULT_TENANT].get("client_email"),
                    self._sa_json[DEFAULT_TENANT].get("project_id"),
                )
            except Exception:
                logger.exception(
                    "SA registry: failed to decode GEE_SERVICE_ACCOUNT_B64"
                )

        # Named tenants. Scan in sorted order so logs are stable.
        for key in sorted(os.environ):
            if key == "GEE_SERVICE_ACCOUNT_B64":
                continue
            m = _TENANT_ENV_RE.match(key)
            if not m:
                continue
            tenant = m.group(1).lower()
            try:
                self._sa_json[tenant] = _decode_sa_json(os.environ[key])
                logger.info(
                    "SA registry: loaded tenant %r (sa=%s, project=%s)",
                    tenant,
                    self._sa_json[tenant].get("client_email"),
                    self._sa_json[tenant].get("project_id"),
                )
            except Exception:
                logger.exception(
                    "SA registry: failed to decode %s for tenant %r",
                    key, tenant,
                )

    def list_tenants(self) -> list[str]:
        return sorted(self._sa_json.keys())

    def has_tenant(self, tenant: str) -> bool:
        return tenant in self._sa_json

    def resolve(self, tenant: Optional[str]) -> str:
        """Pick the actual tenant to use. Unknown / missing → default.
        Returns ``""`` if neither the requested tenant nor a default is
        configured — callers should treat that as "registry not ready"."""
        if tenant and tenant in self._sa_json:
            return tenant
        if DEFAULT_TENANT in self._sa_json:
            return DEFAULT_TENANT
        return ""

    def get_token(self, tenant: Optional[str], force_refresh: bool = False) -> dict:
        """Return ``{access_token, project_id, client_email, tenant}`` for
        the given tenant. Caches across calls; refresh-on-expire happens
        automatically. Raises ``KeyError`` if no tenant matches and no
        default is configured.
        """
        resolved = self.resolve(tenant)
        if not resolved:
            raise KeyError(
                f"unknown tenant {tenant!r} and no default configured "
                f"(known tenants: {self.list_tenants()})"
            )
        with self._lock:
            cached = self._tokens.get(resolved)
            if (cached and not force_refresh
                    and time.time() - cached["fetched_at"] < _TOKEN_TTL_SEC):
                return cached["data"]
            # Mint / refresh
            data = self._mint_locked(resolved)
            self._tokens[resolved] = {"data": data, "fetched_at": time.time()}
            return data

    def _mint_locked(self, tenant: str) -> dict:
        """Refresh credentials and return token data. Caller must hold
        ``self._lock``. Imports are local so ``ee`` doesn't get pulled in
        until actually needed (keeps test startup fast)."""
        import google.oauth2.service_account
        import google.auth.transport.requests
        import ee  # for ee.oauth.SCOPES

        sa_json = self._sa_json[tenant]
        creds = self._creds.get(tenant)
        if creds is None:
            creds = google.oauth2.service_account.Credentials.from_service_account_info(
                sa_json, scopes=ee.oauth.SCOPES,
            )
            self._creds[tenant] = creds
        creds.refresh(google.auth.transport.requests.Request())
        return {
            "access_token": creds.token,
            "project_id": sa_json.get("project_id", ""),
            "client_email": sa_json.get("client_email", ""),
            "tenant": tenant,
        }


# Module-level singleton — lazy so tests can construct their own
_REGISTRY: Optional[SARegistry] = None


def get_registry() -> SARegistry:
    """Return the process-wide SA registry, constructing it lazily on
    first access."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = SARegistry()
    return _REGISTRY


def reset_registry() -> None:
    """Clear the singleton — used by tests to re-load after env changes."""
    global _REGISTRY
    _REGISTRY = None
