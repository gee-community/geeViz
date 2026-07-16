"""``eeCreds`` — friendly API for using multiple Earth Engine credentials
interchangeably from the same Python process.

**You don't need to call this directly if you only use one credential.**
Importing :mod:`geeViz.geeView` and calling ``Map.view()`` already
auto-starts the proxy under the hood via ``ensure_started("auto")`` —
single-credential workflows get the proxy for free. Multi-credential
workflows use this module to register, switch, and stop credentials
explicitly.

Supports both service accounts and OAuth user-account refresh tokens, in
any of these input formats:

- File path to a JSON key
- Base64-encoded JSON string
- JSON string
- Dict (already-parsed JSON)
- Raw bytes (UTF-8 JSON or base64 of either)

Auto-start behaviour (the default path)
---------------------------------------
::

    from geeViz.geeView import Map
    import ee

    # That's it. Map.view() called below will:
    #   1. Discover credentials in the environment
    #   2. Start a local proxy (uvicorn in a daemon thread) if needed
    #   3. Point ee.Initialize at the proxy
    Map.addLayer(ee.Image("USGS/SRTMGL1_003"), {"min": 0, "max": 4000}, "SRTM")
    Map.view()

The proxy survives for the lifetime of the Python process — subsequent
``Map.view()`` calls reuse it without restarting.

Explicit multi-credential workflow
----------------------------------
::

    from geeViz.eeAuth import eeCreds
    import ee

    eeCreds.addCreds("path/to/sa-prod.json", name="prod")
    eeCreds.addCreds(b64_sa_string,          name="acme")
    eeCreds.addCreds("~/.config/earthengine/credentials", name="ian")  # OAuth
    eeCreds.start()                # initializes ee + spawns local proxy

    eeCreds.use("acme")
    ee.Image(1).getInfo()          # routes through the acme SA

    # Or scoped switching — restores previous tenant on block exit
    with eeCreds.use("ian"):
        ee.Image(2).getInfo()      # routes through ian's OAuth refresh token

Why this exists
---------------
``ee.Initialize()`` stores credentials in module-global state — you can
only have one active identity per Python process. ``eeCreds`` works
around that by running a local proxy server that holds N credentials,
re-signs each EE REST request with the right one, and lets the SDK's
single ``ee.Initialize`` point at the proxy. The proxy reads which
credential to use from a thread-aware ``ContextVar`` set by
``eeCreds.use()``.

Same machinery powers the JS / browser path: each browser tab that
``Map.view()`` opens has its tenant baked into the per-session run_js
file (NOT the page URL), so every tab routes through the right
credential for its lifetime — process-wide ``eeCreds.use()`` switches
can't drift an open tab to a different credential.
"""
from __future__ import annotations

import base64
import binascii
import contextlib
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from .client import (
    CURRENT_TENANT,
    initialize_via_proxy,
    set_tenant,
    reset_tenant,
    tenant_context,
)

logger = logging.getLogger(__name__)

# Re-mint access tokens every 50 min (well inside the 1h expiry).
_TOKEN_TTL_SEC = 50 * 60

# Default port for the in-process proxy when ``start()`` runs one.
# Picked away from common dev ports (8888 is the agent UI) to avoid
# collisions when both are in the same process.
_DEFAULT_PROXY_PORT = 8889


def _gcloud_default_project() -> str:
    """Return ``gcloud config get-value project`` or ``""`` on any
    failure. Used as the last-resort fallback for OAuth project detection.

    Best-effort and silent: if ``gcloud`` isn't installed, the command
    times out, or the project is unset, returns an empty string. Never
    raises — auto-discovery should always succeed at returning
    SOMETHING (possibly empty), never crash.
    """
    import shutil
    import subprocess

    # ``shutil.which`` finds ``gcloud.cmd`` on Windows via PATHEXT.
    gcloud_path = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not gcloud_path:
        return ""
    try:
        result = subprocess.run(
            [gcloud_path, "config", "get-value", "project"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return ""
        out = (result.stdout or "").strip()
        if out and out.lower() != "(unset)":
            logger.info(
                "eeCreds: project hint from gcloud config: %r", out
            )
            return out
    except Exception:
        return ""
    return ""


# ──────────────────────── Credential entries ────────────────────────
@dataclass
class _CredEntry:
    """One registered credential, identified by ``name``.

    Holds the parsed credential payload, the type ("sa" / "oauth"), and
    lazily-built google.auth ``Credentials`` + cached access token data.
    """
    name: str
    type: str                       # "sa" or "oauth"
    data: dict                      # the parsed JSON
    source: str = ""                # debugging hint: "path", "b64", "dict", ...
    project_id: str = ""            # for SA: from data["project_id"]; for OAuth: env override
    client_email: str = ""          # SA only

    _creds: Any = field(default=None, repr=False)   # google.oauth2.* Credentials
    _token: dict = field(default_factory=dict, repr=False)
    _token_fetched_at: float = field(default=0.0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


# ──────────────────────── Core class ────────────────────────
class EECreds:
    """Multi-tenant credential registry + EE init lifecycle.

    Usually used via the module-level singleton ``eeCreds`` — but
    instantiable directly when you need multiple independent registries
    (e.g. tests, multi-tenant servers with isolated credential sets)::

        from geeViz.eeAuth.eeCreds import EECreds
        creds = EECreds()
        creds.addCreds(...)
        creds.start()
    """

    def __init__(self) -> None:
        self._entries: dict[str, _CredEntry] = {}
        self._started = False
        self._proxy_url: Optional[str] = None
        self._proxy_thread: Optional[threading.Thread] = None
        self._proxy_server = None       # uvicorn.Server
        self._lock = threading.Lock()

    # ─────────────── adding credentials ───────────────
    def addCreds(
        self,
        creds: Union[str, dict, bytes],
        name: str,
        project: Optional[str] = None,
    ) -> "EECreds":
        """Register a set of credentials under ``name``.

        Accepts:

        - File path to a JSON key file (SA, OAuth, WIF, or impersonation config)
        - Base64-encoded JSON string (typical for env vars)
        - JSON string (literal contents)
        - Already-parsed dict
        - **Bare service-account email string** (``foo@bar.iam.gserviceaccount.com``)
          → routed to :meth:`addImpersonation` so the proxy mints tokens
          via the IAM credentials API at request time (no key held)

        Auto-detects which credential shape it is. ``project`` overrides
        the default project — required for OAuth + impersonation,
        optional for SAs since their JSON has ``project_id``.

        Returns self so chaining works::

            eeCreds.addCreds(sa1, "a").addCreds(sa2, "b").start()
        """
        # Bare SA-email string → impersonation. Recognized by the
        # ``*@*.iam.gserviceaccount.com`` shape; anything else falls
        # through to the JSON parser.
        if isinstance(creds, str) and self._looks_like_sa_email(creds.strip()):
            return self.addImpersonation(creds.strip(), name=name, project=project)

        data, source = self._parse_input(creds)
        entry_type, defaults = self._classify(data)
        entry = _CredEntry(
            name=name,
            type=entry_type,
            data=data,
            source=source,
            project_id=project or defaults.get("project_id", "") or "",
            client_email=defaults.get("client_email", "") or "",
        )
        with self._lock:
            self._entries[name] = entry
        logger.info(
            "eeCreds: added %r (type=%s, source=%s, project=%s)",
            name, entry_type, source, entry.project_id,
        )
        return self

    @staticmethod
    def _looks_like_sa_email(s: str) -> bool:
        """True iff ``s`` is shaped like a GCP service-account email.
        Used by :meth:`addCreds` to route bare emails to impersonation
        instead of trying to parse them as JSON / base64 / paths."""
        if not s or len(s) > 254 or " " in s:
            return False
        if "@" not in s:
            return False
        local, _, domain = s.partition("@")
        # SA emails always live under iam.gserviceaccount.com.
        return bool(local) and domain.endswith(".iam.gserviceaccount.com")

    def addImpersonation(
        self,
        target_email: str,
        name: str,
        project: Optional[str] = None,
    ) -> "EECreds":
        """Register a tenant that mints tokens by **impersonating**
        ``target_email`` at request time.

        No key material is held. The runtime's ADC source must hold
        ``roles/iam.serviceAccountTokenCreator`` on the target SA. On
        each token mint, ``google.auth.impersonated_credentials`` calls
        the IAM credentials API to fetch a short-lived (1h) access
        token; google-auth refreshes it automatically when it expires.

        This is the multi-tenant **keyless** path: the proxy holds N
        SA emails, not N JSON keys. Works identically across GCP Cloud
        Run (source = attached SA), AWS via WIF (source = federated
        identity from STS), and local dev (source = gcloud user creds).

        Args:
            target_email: The SA to impersonate (``foo@proj.iam.gserviceaccount.com``).
            name: Tenant name for ``eeCreds.use(name)``.
            project: Quota project for EE calls. If omitted, falls
                back to the runtime's default ADC project.
        """
        if not self._looks_like_sa_email(target_email):
            raise ValueError(
                f"eeCreds.addImpersonation: {target_email!r} is not a "
                "valid SA email (expected ``*@*.iam.gserviceaccount.com``)."
            )
        entry = _CredEntry(
            name=name,
            type="impersonated",
            # Self-describing dict so ``info()`` round-trips and
            # ``_classify`` can re-route this entry without losing
            # information.
            data={
                "type": "impersonated_service_account",
                "client_email": target_email,
                "impersonate": True,
            },
            source="impersonation",
            project_id=project or "",
            client_email=target_email,
        )
        with self._lock:
            self._entries[name] = entry
        logger.info(
            "eeCreds: added %r (type=impersonated, target=%s, project=%s)",
            name, target_email, entry.project_id,
        )
        return self

    def addADC(
        self,
        name: str = "adc",
        project: Optional[str] = None,
    ) -> "EECreds":
        """Register the runtime's Application Default Credentials as a
        tenant entry.

        Use this when you want the **proxy** to route through ADC
        (attached SA on Cloud Run, WIF federation on AWS, gcloud user
        creds locally) — without holding any key material. Without this,
        ADC-only deployments still get EE working via :meth:`robust_init`
        but the proxy starts empty and the multi-tenant features are
        inaccessible.

        Tokens are minted by calling ``google.auth.default()`` at mint
        time, then refreshing. Same code path as keyed SAs from the
        proxy's perspective.
        """
        entry = _CredEntry(
            name=name,
            type="adc",
            data={"type": "application_default_credentials"},
            source="adc",
            project_id=project or "",
            client_email="",
        )
        with self._lock:
            self._entries[name] = entry
        logger.info(
            "eeCreds: added %r (type=adc, project=%s)",
            name, entry.project_id or "<runtime default>",
        )
        return self

    def _parse_input(self, x: Union[str, dict, bytes]) -> tuple[dict, str]:
        """Return ``(parsed_dict, source_description)`` from any of the
        supported input forms."""
        # Bytes → decode as utf-8 first
        if isinstance(x, bytes):
            try:
                x = x.decode("utf-8")
            except UnicodeDecodeError:
                x = base64.b64decode(x).decode("utf-8", errors="replace")

        if isinstance(x, dict):
            return dict(x), "dict"

        if not isinstance(x, str):
            raise TypeError(
                f"eeCreds.addCreds: expected str / dict / bytes, got {type(x).__name__}"
            )

        # Expand ~ in paths
        expanded = os.path.expanduser(x)
        if os.path.isfile(expanded):
            try:
                with open(expanded, "r", encoding="utf-8") as f:
                    return json.load(f), f"path:{expanded}"
            except (OSError, json.JSONDecodeError) as e:
                raise ValueError(
                    f"eeCreds.addCreds: could not read JSON from {expanded!r}: {e}"
                ) from e

        # JSON string?
        x_stripped = x.strip()
        if x_stripped.startswith(("{", "[")):
            try:
                return json.loads(x_stripped), "json_string"
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"eeCreds.addCreds: starts like JSON but failed to parse: {e}"
                ) from e

        # If the string LOOKS like a filesystem path (separator chars,
        # ``.json`` suffix, or a Windows drive letter) but didn't match
        # ``os.path.isfile`` above, the user almost certainly meant to
        # pass a file path that doesn't exist — surface that directly
        # rather than falling through to base64 and producing a
        # confusing "Only base64 data is allowed" error.
        looks_like_path = (
            "/" in x_stripped
            or "\\" in x_stripped
            or x_stripped.lower().endswith(".json")
            or (len(x_stripped) >= 3 and x_stripped[1:3] == ":\\")
        )
        if looks_like_path:
            raise FileNotFoundError(
                f"eeCreds.addCreds: file not found: {expanded!r}. "
                "Pass an existing path to a JSON key, a JSON literal, "
                "a base64-encoded JSON string, or a dict."
            )

        # Base64?
        try:
            decoded = base64.b64decode(x_stripped, validate=True)
            data = json.loads(decoded)
            return data, "base64"
        except (binascii.Error, ValueError, json.JSONDecodeError) as e:
            raise ValueError(
                f"eeCreds.addCreds: could not interpret string as path, JSON, "
                f"or base64 JSON (last error: {e})"
            ) from e

    def _classify(self, data: dict) -> tuple[str, dict]:
        """Identify the credential shape in ``data``.

        Returns ``(entry_type, defaults_dict)``. Recognized types:

        - ``sa``: a service-account key file
          (``{"type": "service_account", "private_key": ...}``).
          Holds a long-lived private key; the riskiest shape — security
          teams typically flag these.
        - ``oauth``: a refresh-token file (``earthengine authenticate``
          or ``gcloud auth application-default login`` output for user
          accounts).
        - ``adc``: an Application Default Credentials source — either a
          workload-identity-federation config (``type: external_account``)
          OR a marker that the entry should mint via
          ``google.auth.default()``. No key held; tokens come from the
          runtime's identity (Cloud Run metadata server, AWS STS via
          WIF, gcloud user creds, etc.). Both JS and Python proxy paths
          end up with whatever ``google.auth.default()`` resolves to
          on this host.
        - ``impersonated``: a stored target SA email. Tokens minted via
          ``google.auth.impersonated_credentials`` at request time using
          ADC as the source. No key held; the runtime identity must
          have ``roles/iam.serviceAccountTokenCreator`` on the target.
          This is the multi-tenant keyless path — the proxy holds N
          emails, not N keys.
        """
        t = data.get("type", "")
        if t == "service_account":
            return "sa", {
                "project_id": data.get("project_id", ""),
                "client_email": data.get("client_email", ""),
            }
        if t == "authorized_user" or "refresh_token" in data:
            # google-auth-style "authorized_user" file OR a manually-built
            # refresh-token dict with at least the refresh_token field.
            return "oauth", {
                "project_id": data.get("quota_project_id", "")
                              or data.get("project", "") or "",
            }
        if t == "external_account":
            # Workload Identity Federation config. The config itself is
            # not a secret — it routes ``google.auth`` through GCP STS
            # to exchange an external (AWS, Azure, OIDC) identity for a
            # GCP token, optionally chained through impersonation of a
            # target SA. The ``service_account_impersonation_url`` field
            # names that target if set; surface it for log clarity.
            url = data.get("service_account_impersonation_url", "") or ""
            target = ""
            if "/serviceAccounts/" in url:
                target = url.split("/serviceAccounts/", 1)[1].split(":", 1)[0]
            return "adc", {
                "project_id": data.get("quota_project_id", "") or "",
                "client_email": target,
            }
        if t == "impersonated_service_account":
            # Explicit impersonation config (e.g. produced by gcloud
            # auth impersonate-service-account-flow). Extract the
            # target SA email so the runtime knows what to impersonate.
            url = data.get("service_account_impersonation_url", "") or ""
            target = (data.get("target_principal", "")
                      or (url.split("/serviceAccounts/", 1)[1].split(":", 1)[0]
                          if "/serviceAccounts/" in url else ""))
            return "impersonated", {
                "project_id": data.get("quota_project_id", "") or "",
                "client_email": target,
            }
        # ``client_email`` as the only meaningful key + an explicit
        # ``impersonate`` flag is the in-memory shape ``addImpersonation``
        # constructs. Keep it routable through the same classifier so
        # round-tripping (``addCreds(eeCreds.info(name))``) works.
        if data.get("impersonate") and data.get("client_email"):
            return "impersonated", {
                "project_id": data.get("project_id", "") or "",
                "client_email": data["client_email"],
            }
        raise ValueError(
            f"eeCreds: unrecognized credential JSON shape "
            f"(keys: {sorted(data.keys())}). Expected one of:\n"
            f"  - service-account key (type='service_account')\n"
            f"  - OAuth credentials (type='authorized_user' or with 'refresh_token')\n"
            f"  - WIF config (type='external_account')\n"
            f"  - impersonation config (type='impersonated_service_account')"
        )

    # ─────────────── ADC stub-metadata guard ───────────────
    @staticmethod
    def _adc_is_stub_gce_metadata(creds) -> bool:
        """Return True when ``google.auth.default()`` handed back a
        ``compute_engine.Credentials`` but no metadata server is
        actually reachable.

        Colab is the motivating case: google-auth's environment probe
        thinks it's on GCE (the Colab VM sets some of the same env
        indicators) so it returns a ``compute_engine.Credentials``
        object, but ``metadata.google.internal`` doesn't resolve.
        Every subsequent ``refresh()`` then blocks on a 5-retry
        exponential-backoff loop against the metadata server, emitting
        a wall of TransportError tracebacks before the caller can
        recover.

        A quick 0.5s probe to the metadata "ping" endpoint tells us
        whether we're actually on GCE. Any failure — HTTP error,
        network error, timeout — means "this isn't a real GCE
        instance" and the caller should skip registration.
        """
        try:
            from google.auth.compute_engine import credentials as _gce_creds
        except Exception:
            return False
        if not isinstance(creds, _gce_creds.Credentials):
            return False
        # Real GCE hosts respond to a ping in single-digit ms. The
        # 0.5s cap is generous enough to survive a network hiccup
        # without being long enough to hurt startup in the "actually
        # on GCE" case.
        try:
            import google.auth.compute_engine._metadata as _md
            import google.auth.transport.requests as _gart
            return not _md.ping(_gart.Request(), timeout=0.5)
        except Exception:
            return True

    # ─────────────── auto-discovery ───────────────
    @staticmethod
    def _detect_oauth_project() -> str:
        """Best-effort: which GCP project should OAuth-credential EE
        calls be billed against?

        OAuth refresh tokens (``~/.config/earthengine/credentials``)
        don't carry a project — so without an explicit answer the proxy
        forwards EE requests without ``x-goog-user-project``, EE
        defaults to ``earthengine-legacy`` as the consumer, and the
        personal Google account can't use that → 403.

        Checked sources (first hit wins):

        1. ``ee.data._get_state().cloud_api_user_project`` — most
           reliable; populated by a successful ``ee.Initialize(project=...)``.
        2. ``$GEE_PROJECT`` env var — geeViz convention. EE-specific, so
           it beats ADC's bookkeeping when the caller explicitly named a
           project (e.g. multi-tenant deploys where test EE runs on a
           training-tier project but BQ/Storage stay on the commercial
           tenant project).
        3. ``$GOOGLE_CLOUD_PROJECT`` env var — standard GCP convention.
        4. ``ee.oauth.get_appdefault_project()`` — reads
           ``application_default_credentials.json``'s ``quota_project_id``;
           this is the value EE's own ``get_persistent_credentials`` uses.
        5. ``gcloud config get-value project`` — last resort, subprocess
           call. Often diverges from ADC's quota project; lower priority
           than ADC for that reason.

        Returns ``""`` when nothing's discoverable; caller can leave the
        entry's project blank or surface a clear error to the user.
        """
        try:
            import ee.oauth as _ee_oauth
        except Exception:
            _ee_oauth = None

        # ``earthengine-legacy`` is the SDK's internal placeholder for
        # "no real project set yet"; SDK project numbers (764086051850
        # etc) are EE's shared OAuth-client projects that no end user
        # can quota against. Neither is a usable project hint — filter
        # both out at every detection step.
        def _ok(proj: str) -> bool:
            if not proj:
                return False
            p = proj.strip()
            if p.lower() == "earthengine-legacy":
                return False
            if _ee_oauth is not None and _ee_oauth.is_sdk_project(p):
                return False
            return True

        # 1. EE's current state — only honour if ``ee.Initialize(project=...)``
        #    set a real project (not the legacy placeholder).
        try:
            import ee.data
            proj = getattr(ee.data._get_state(),
                           "cloud_api_user_project", None) or ""
            if _ok(proj):
                return proj
        except Exception:
            pass
        # 2. geeViz convention — explicit EE override; beats both the
        #    standard GCP env var and the ADC bookkeeping value, because
        #    a caller who set GEE_PROJECT explicitly meant "use THIS for
        #    EE" (the geeViz multi-tenant test/prod split depends on it).
        proj = os.environ.get("GEE_PROJECT", "").strip()
        if _ok(proj):
            return proj
        # 3. GCP standard env var
        proj = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        if _ok(proj):
            return proj
        # 4. ADC's quota_project_id — same source EE uses internally.
        if _ee_oauth is not None:
            try:
                proj = _ee_oauth.get_appdefault_project() or ""
                if _ok(proj):
                    return proj
            except Exception:
                pass
        # 5. gcloud config get-value project — usually set by anyone
        #    who's run ``gcloud auth login``. Subprocess so this only
        #    runs once per discover() call.
        proj = _gcloud_default_project()
        if _ok(proj):
            return proj
        return ""

    def discover(self, *, overwrite: bool = False) -> list[str]:
        """Scan the environment for credentials and register any found.

        Lookups, in order — each one that produces a credential gets
        added under a stable name:

        =====================================================  =================
        Source                                                  Registered as
        =====================================================  =================
        ``$GOOGLE_APPLICATION_CREDENTIALS`` (JSON path)         ``"adc"``
        ``~/.config/earthengine/credentials`` (EE persistent)   ``"ee-persistent"``
        gcloud ADC well-known file                              ``"adc-default"``
        ``$GEE_SERVICE_ACCOUNT_B64`` (legacy default SA)        ``"env-default"``
        ``$GEE_<NAME>_SERVICE_ACCOUNT`` (per-tenant SA keys)    ``<name>``
        ``$GEE_<NAME>_SA_EMAIL`` (per-tenant impersonation)     ``<name>``
        ``google.auth.default()`` fallback (Cloud Run / WIF)    ``"adc"``
        =====================================================  =================

        The fallback only fires when nothing else registered, so keyed
        deployments aren't disturbed. On Cloud Run with an attached SA,
        on GKE with workload identity, or on AWS via Workload Identity
        Federation, this is the path that boots the proxy without any
        JSON key on disk.

        Returns the list of names actually registered by this call.
        Existing names are not overwritten unless ``overwrite=True``.

        Safe to call multiple times; failing sources are logged but
        don't raise — discovery is best-effort.
        """
        added: list[str] = []

        # OAuth credentials don't carry a project; SAs do. Detect a
        # project hint once and apply it only to OAuth entries (after
        # classification) so SAs keep their JSON-supplied project_id.
        oauth_project = self._detect_oauth_project()

        def _try_add(value, name: str) -> None:
            if not value:
                return
            if not overwrite and self.has(name):
                return
            try:
                self.addCreds(value, name=name)
                added.append(name)
                # Backfill project for OAuth entries only — SA entries
                # already have the correct project from their JSON.
                entry = self._entries.get(name)
                if (entry is not None
                        and entry.type == "oauth"
                        and not entry.project_id
                        and oauth_project):
                    entry.project_id = oauth_project
                    logger.info(
                        "eeCreds.discover: backfilled project %r for "
                        "OAuth entry %r", oauth_project, name,
                    )
            except Exception:
                logger.exception(
                    "eeCreds.discover: failed to register %s as %r",
                    type(value).__name__, name,
                )

        # 1. GOOGLE_APPLICATION_CREDENTIALS (path to JSON — could be SA or
        #    OAuth depending on the file). _try_add does the right thing
        #    per-type once addCreds has classified the file.
        adc_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if adc_path and os.path.isfile(os.path.expanduser(adc_path)):
            _try_add(adc_path, "adc")

        # 2. Persistent EE credentials file (``earthengine authenticate``).
        #    Always OAuth — the project backfill in _try_add prevents the
        #    classic 403 from EE routing personal-account calls to
        #    earthengine-legacy as the consumer. Files that exist but
        #    don't contain a refresh_token (e.g. ``earthengine
        #    set_project`` written before the user re-authenticated) are
        #    silently skipped by ``addCreds`` via the new
        #    no-refresh-token check below.
        try:
            import ee.oauth as _ee_oauth
            ee_path = _ee_oauth.get_credentials_path()
            if ee_path and os.path.isfile(ee_path):
                _try_add(ee_path, "ee-persistent")
        except Exception:
            logger.debug(
                "eeCreds.discover: ee.oauth.get_credentials_path unavailable",
                exc_info=True,
            )

        # 2b. gcloud Application Default Credentials. When a user has
        #     run ``gcloud auth application-default login``, an OAuth
        #     refresh token lives at a well-known path independent of
        #     the EE one. Picking this up means ``Map.view()`` can spin
        #     up the proxy in ADC-only environments (no
        #     $GOOGLE_APPLICATION_CREDENTIALS, no EE-persistent file)
        #     instead of falling back to the legacy direct-token URL.
        try:
            from google.auth import _cloud_sdk as _gauth_cloud_sdk
            adc_default_path = _gauth_cloud_sdk.get_application_default_credentials_path()
            if adc_default_path and os.path.isfile(adc_default_path):
                _try_add(adc_default_path, "adc-default")
        except Exception:
            logger.debug(
                "eeCreds.discover: gcloud ADC well-known file lookup failed",
                exc_info=True,
            )

        # 3. Legacy default SA env var (used by the env-var registry).
        sa_b64 = os.environ.get("GEE_SERVICE_ACCOUNT_B64", "").strip()
        if sa_b64:
            _try_add(sa_b64, "env-default")

        # 4. Per-tenant SAs from GEE_<NAME>_SERVICE_ACCOUNT pattern.
        import re as _re_disc
        named_re = _re_disc.compile(r"^GEE_([A-Z0-9_]+)_SERVICE_ACCOUNT$")
        for key in sorted(os.environ):
            if key == "GEE_SERVICE_ACCOUNT_B64":
                continue
            m = named_re.match(key)
            if not m:
                continue
            tenant_name = m.group(1).lower()
            _try_add(os.environ[key], tenant_name)

        # 4b. Keyless per-tenant impersonation: GEE_<NAME>_SA_EMAIL=<email>.
        #     Same shape as GEE_<NAME>_SERVICE_ACCOUNT but holds an SA
        #     email instead of a base64 key. The runtime's ADC source
        #     impersonates the target at token-mint time — no key
        #     material in env or on disk. Optional companion
        #     GEE_<NAME>_PROJECT=<id> overrides the quota project.
        email_re = _re_disc.compile(r"^GEE_([A-Z0-9_]+)_SA_EMAIL$")
        for key in sorted(os.environ):
            m = email_re.match(key)
            if not m:
                continue
            tenant_name = m.group(1).lower()
            target_email = os.environ[key].strip()
            if not target_email:
                continue
            if not overwrite and self.has(tenant_name):
                continue
            project_override = os.environ.get(
                f"GEE_{m.group(1)}_PROJECT", "",
            ).strip() or None
            try:
                self.addImpersonation(
                    target_email, name=tenant_name, project=project_override,
                )
                added.append(tenant_name)
            except Exception:
                logger.exception(
                    "eeCreds.discover: failed to register %s as %r "
                    "(impersonation)", key, tenant_name,
                )

        # 5. Keyless ADC fallback. If discovery found nothing AND no
        #    ``adc`` entry already exists, try ``google.auth.default()``.
        #    This is the path for Cloud Run with attached SA, GKE
        #    workload identity, and AWS via Workload Identity Federation
        #    — environments where credentials come from the runtime, not
        #    a JSON file. Registers as ``"adc"`` so the proxy has at
        #    least one tenant to route through.
        #
        #    Exception: in Colab (and other environments where
        #    ``google.auth.default()`` returns ``compute_engine.Credentials``
        #    but the metadata server isn't actually reachable — Colab
        #    fools google-auth's env-var probe), skip the ADC registration
        #    entirely. Otherwise every proxy request would try to mint a
        #    token via the metadata server, hit 404, retry with backoff up
        #    to five times, and emit a wall of scary tracebacks before the
        #    real ``ee.Authenticate(auth_mode='colab')`` path finishes and
        #    the entry gets re-registered with valid creds.
        if not added and not self.has("adc"):
            try:
                import google.auth
                _creds, default_project = google.auth.default()
                if self._adc_is_stub_gce_metadata(_creds):
                    logger.info(
                        "eeCreds.discover: skipping ADC fallback — "
                        "compute_engine.Credentials returned but the "
                        "metadata server isn't reachable (typical Colab "
                        "pre-auth state). Waiting for user auth to run."
                    )
                else:
                    self.addADC(name="adc", project=default_project or None)
                    added.append("adc")
                    logger.info(
                        "eeCreds.discover: registered ADC fallback "
                        "(project=%s)", default_project or "<runtime>",
                    )
            except Exception:
                logger.debug(
                    "eeCreds.discover: ADC fallback unavailable",
                    exc_info=True,
                )

        if added:
            logger.info(
                "eeCreds.discover: registered %d credential(s): %s",
                len(added), ", ".join(added),
            )
        return added

    # ─────────────── introspection ───────────────
    def list(self) -> list[str]:
        """Return registered credential names in insertion order."""
        return list(self._entries.keys())

    def names(self) -> list[str]:
        """Alias for ``list()`` — also returns registered names."""
        return self.list()

    def current(self) -> str:
        """Return the currently active tenant name. Falls back to the
        first registered name if no explicit ``use()`` has been made yet
        and at least one credential is registered. Returns ``""`` if
        nothing's registered."""
        active = CURRENT_TENANT.get()
        if active and active in self._entries:
            return active
        if self._entries:
            return next(iter(self._entries))
        return ""

    def has(self, name: str) -> bool:
        return name in self._entries

    def info(self, name: Optional[str] = None) -> dict:
        """Inspect a registered credential without exposing the secret
        key material. Returns ``{name, type, project_id, client_email,
        source}``. ``name=None`` returns the currently active one."""
        nm = name or self.current()
        if nm not in self._entries:
            raise KeyError(f"eeCreds: unknown credential {nm!r}")
        e = self._entries[nm]
        return {
            "name": e.name, "type": e.type, "source": e.source,
            "project_id": e.project_id, "client_email": e.client_email,
        }

    # ─────────────── token minting ───────────────
    def get_token(
        self, name: Optional[str] = None, force_refresh: bool = False
    ) -> dict:
        """Mint (or return cached) access token for ``name``. If no name
        is given, uses the currently active tenant.

        Returns ``{access_token, project_id, client_email, tenant}`` —
        same shape as ``geeViz.eeAuth.registry.SARegistry.get_token`` so
        ``build_proxy_router`` can accept either.
        """
        nm = name or self.current()
        if not nm:
            raise KeyError("eeCreds: no credentials registered")
        entry = self._entries.get(nm)
        if entry is None:
            # Fall back to the first registered tenant — keeps things
            # forgiving when an unknown name is passed (callers can
            # check has() themselves if they want strict mode).
            fallback = next(iter(self._entries), "")
            if not fallback:
                raise KeyError(f"eeCreds: unknown credential {nm!r}")
            entry = self._entries[fallback]

        with entry._lock:
            if (entry._token and not force_refresh
                    and time.time() - entry._token_fetched_at < _TOKEN_TTL_SEC):
                return entry._token
            self._mint(entry)
            return entry._token

    def _mint(self, entry: _CredEntry) -> None:
        """Refresh ``entry``'s credentials and cache the token. Caller
        must hold ``entry._lock``."""
        import google.auth.transport.requests
        import ee  # for ee.oauth.SCOPES

        if entry._creds is None:
            entry._creds = self._build_credentials(entry)

        entry._creds.refresh(google.auth.transport.requests.Request())
        entry._token = {
            "access_token": entry._creds.token,
            "project_id": entry.project_id,
            "client_email": entry.client_email,
            "tenant": entry.name,
        }
        entry._token_fetched_at = time.time()

    def _build_credentials(self, entry: _CredEntry):
        """Build the appropriate google.auth Credentials object for this
        entry. Lazily, so ``ee`` / ``google.auth`` are only imported on
        first use."""
        import ee  # for ee.oauth.SCOPES
        scopes = ee.oauth.SCOPES

        if entry.type == "sa":
            import google.oauth2.service_account as gsa
            return gsa.Credentials.from_service_account_info(
                entry.data, scopes=scopes,
            )
        if entry.type == "oauth":
            import google.oauth2.credentials as gco
            d = entry.data

            # Older ``earthengine authenticate`` credentials files contain
            # only a ``refresh_token`` (sometimes with scopes). The EE
            # Python library knows to inject its own well-known OAuth
            # client_id/client_secret when refreshing these — but
            # ``google.oauth2.credentials.Credentials.refresh`` will
            # fail with "The credentials do not contain the necessary
            # fields" unless we provide them up front. Fall back to
            # EE's well-known client when the JSON doesn't carry one.
            client_id = d.get("client_id") or ee.oauth.CLIENT_ID
            client_secret = d.get("client_secret") or ee.oauth.CLIENT_SECRET
            token_uri = d.get("token_uri") or ee.oauth.TOKEN_URI

            return gco.Credentials(
                token=None,
                refresh_token=d.get("refresh_token"),
                client_id=client_id,
                client_secret=client_secret,
                token_uri=token_uri,
                scopes=scopes,
            )
        if entry.type == "adc":
            # Application Default Credentials. No key material in the
            # entry; tokens come from whatever ``google.auth.default()``
            # resolves to on this host:
            #   - Cloud Run / GCE / GKE: attached SA via metadata server
            #   - AWS EC2/ECS/EKS with WIF: federated via STS, optionally
            #     auto-impersonating a target SA (when the WIF config
            #     names ``service_account_impersonation_url``)
            #   - Local dev: ``gcloud auth application-default login``
            # The proxy treats this identically to any other entry —
            # the resulting Credentials object refreshes the same way.
            import google.auth
            creds, default_project = google.auth.default(scopes=scopes)
            # Quota project — honor entry override; otherwise let ADC's
            # own resolution stand. ``with_quota_project`` is supported
            # on every Credentials subclass google-auth ships.
            proj = entry.project_id or default_project
            if proj and hasattr(creds, "with_quota_project"):
                try:
                    creds = creds.with_quota_project(proj)
                except Exception:
                    # ``AnonymousCredentials`` and a few exotic types
                    # don't support quota project. Fall through.
                    pass
            return creds
        if entry.type == "impersonated":
            # Service-account impersonation. Source identity comes from
            # ADC (the runtime's own identity — attached SA on GCP, WIF
            # federation on AWS, gcloud user creds locally). The source
            # principal must hold ``roles/iam.serviceAccountTokenCreator``
            # on the target SA. The IAM credentials API mints a
            # short-lived (default 1h) access token for the target;
            # google-auth handles refresh automatically.
            import google.auth
            from google.auth import impersonated_credentials
            target_email = (entry.client_email
                            or entry.data.get("client_email", ""))
            if not target_email:
                raise ValueError(
                    f"eeCreds: impersonated entry {entry.name!r} has no "
                    "target SA email (set client_email or use "
                    "addImpersonation())."
                )
            source_creds, _ = google.auth.default()
            return impersonated_credentials.Credentials(
                source_credentials=source_creds,
                target_principal=target_email,
                target_scopes=list(scopes),
                lifetime=3600,
            )
        raise ValueError(f"eeCreds: unknown credential type {entry.type!r}")

    # ─────────────── switching ───────────────
    def use(self, name: str):
        """Switch the active credential and return a context manager
        that restores the previous one on exit. Works as a statement OR
        a ``with`` block::

            eeCreds.use("acme")              # switch and forget
            ee.Image(1).getInfo()            # uses acme

            with eeCreds.use("ian"):         # scoped
                ee.Image(2).getInfo()        # uses ian
            # back to acme here
        """
        if name not in self._entries:
            raise KeyError(
                f"eeCreds: unknown credential {name!r} "
                f"(known: {self.list()})"
            )

        # Allow both:
        #   eeCreds.use("acme")             — plain call, no with
        #   with eeCreds.use("ian"): ...    — context manager
        return _UseContext(self, name)

    # ─────────────── lifecycle ───────────────
    def start(
        self,
        *,
        proxy_port: int = _DEFAULT_PROXY_PORT,
        proxy_host: str = "127.0.0.1",
        ee_init: bool = True,
        launch_proxy: bool = True,
    ) -> dict:
        """Initialize Earth Engine for multi-credential use.

        Steps (each can be disabled via kwargs):

        1. ``launch_proxy=True``: start a background HTTP proxy that
           injects per-tenant SA / OAuth tokens. Required for switching
           credentials at runtime without re-initializing ``ee``.
        2. ``ee_init=True``: call ``ee.Initialize(url=proxy_url, ...)``
           so the EE Python SDK routes all REST calls through the proxy.

        Returns a status dict with ``{started, proxy_url, tenants,
        ee_initialized}`` for inspection.

        Idempotent — calling ``start()`` twice is safe; the second call
        returns the current state.
        """
        with self._lock:
            if self._started:
                return self._status()

            if not self._entries:
                raise RuntimeError(
                    "eeCreds.start(): no credentials registered — "
                    "call addCreds(...) first"
                )

            if launch_proxy:
                self._launch_proxy(proxy_host, proxy_port)

            if ee_init:
                proxy_url = self._proxy_url or ""
                if proxy_url:
                    # Pass the first registered credential's project so EE
                    # builds API URLs like ``projects/<real>/value:compute``
                    # instead of the placeholder. The proxy then doesn't have
                    # to rewrite paths — all tenants in a single eeCreds
                    # instance share a process-wide ee.Initialize, and EE
                    # rejects the placeholder string at the path level.
                    first = next(iter(self._entries.values()))
                    initialize_via_proxy(
                        proxy_url, project=first.project_id or None,
                    )
                else:
                    # No proxy → direct ee.Initialize with the FIRST creds
                    # (single-tenant mode; .use() will then raise unless
                    # the user re-initializes).
                    first = next(iter(self._entries.values()))
                    self._direct_init(first)

            self._started = True
            return self._status()

    def stop(self) -> None:
        """Shut down the in-process proxy if one's running. Safe to
        call when not started."""
        with self._lock:
            srv = self._proxy_server
            if srv is not None:
                try:
                    srv.should_exit = True  # uvicorn graceful shutdown
                except Exception:
                    pass
            if self._proxy_thread is not None:
                self._proxy_thread.join(timeout=5.0)
            self._proxy_server = None
            self._proxy_thread = None
            self._proxy_url = None
            self._started = False

    def _find_free_port(self, host: str, preferred: int) -> int:
        """Return ``preferred`` if it's bindable, otherwise the first
        free port walking up from ``preferred+1`` (up to ``+49``).

        Falls back to an OS-assigned ephemeral port if all 50 candidates
        in the explicit range are taken — never raises, always returns
        SOMETHING the caller can bind.

        Why this matters: the default proxy port (8889) is often in use
        from a previous Python process whose proxy thread didn't get
        cleaned up (notebook kernel restart, crashed script, two scripts
        running side by side). Without this, ``start()`` would silently
        hand back a ``_proxy_url`` pointing at a dead socket.

        There's a small TOCTOU race here — between our probe-and-close
        and uvicorn's actual bind, something else could grab the port.
        In practice this almost never happens; if it does, the user
        sees the original WinError 10048 and can rerun.
        """
        import socket
        candidates = [preferred] + list(range(preferred + 1, preferred + 50))
        for candidate in candidates:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind((host, candidate))
                return candidate
            except OSError:
                continue
        # Everything in the explicit range was taken — let the OS pick
        # any free ephemeral port.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, 0))
            return s.getsockname()[1]

    def _launch_proxy(self, host: str, port: int) -> None:
        """Start a uvicorn server in a background thread serving the
        proxy router. Captures the URL so ``ee.Initialize`` can point
        at it.

        If the requested ``port`` is already in use (common when a prior
        notebook kernel's proxy thread is still alive), this method
        transparently picks a different free port — the resulting
        ``proxy_url`` reflects whatever port was actually bound.
        """
        try:
            import uvicorn
        except ImportError as e:
            raise RuntimeError(
                "eeCreds.start(launch_proxy=True) requires uvicorn. "
                "Install it (pip install uvicorn) or call "
                "start(launch_proxy=False) to skip."
            ) from e

        # Late import to dodge circular: server.py imports from registry,
        # we import from server here.
        from .server import create_proxy_app

        # Find a port we can actually bind. Most of the time this is
        # the preferred port; on conflicts we walk up.
        actual_port = self._find_free_port(host, port)
        if actual_port != port:
            logger.info(
                "eeCreds: port %d busy, using %d instead", port, actual_port
            )

        app = create_proxy_app(creds=self, prefix="/ee-api")
        config = uvicorn.Config(
            app, host=host, port=actual_port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)

        # Start the server loop in a daemon thread. Uvicorn drives its
        # own asyncio loop internally — fine for daemonized use.
        def _run():
            try:
                server.run()
            except Exception:
                logger.exception("eeCreds: proxy thread died")

        t = threading.Thread(target=_run, name="eeCreds-proxy", daemon=True)
        t.start()
        # Brief wait for the socket to bind so first EE call doesn't race
        for _ in range(50):  # up to ~5s
            if server.started:
                break
            time.sleep(0.1)
        else:
            logger.warning(
                "eeCreds: proxy thread didn't report 'started' within 5s; "
                "first EE call may need a retry"
            )

        self._proxy_server = server
        self._proxy_thread = t
        self._proxy_url = f"http://{host}:{actual_port}/ee-api"
        logger.info("eeCreds: proxy listening at %s", self._proxy_url)

    def _direct_init(self, entry: _CredEntry) -> None:
        """Fallback ``launch_proxy=False`` path: call ``ee.Initialize``
        directly with the first registered credential. Single-tenant
        only — ``.use()`` won't switch credentials without re-init."""
        import ee
        if entry._creds is None:
            entry._creds = self._build_credentials(entry)
        ee.Initialize(
            credentials=entry._creds,
            project=entry.project_id or "ee-direct-init",
        )
        logger.info(
            "eeCreds: ee.Initialize direct (no proxy) with %r", entry.name
        )

    def router(self, **kwargs):
        """Return a FastAPI ``APIRouter`` that proxies EE requests using
        these credentials. Mount it in your own FastAPI app::

            app.include_router(eeCreds.router(), prefix="/ee-api")

        ``kwargs`` pass through to ``build_proxy_router`` — customize
        the tenant header, resolver, workload-tag builder, etc.
        """
        from .server import build_proxy_router
        return build_proxy_router(creds=self, **kwargs)

    # ─────────────── detached-subprocess proxy ───────────────
    # Lets a script start a proxy once, exit cleanly, and have any
    # subsequent script attach to the same process — survives the
    # caller's lifecycle so multi-``Map.view()`` workflows don't need
    # the blocking ``input()`` at the end of each script. See
    # ``ensure_started(mode="detached")``.

    @staticmethod
    def _detached_state_path() -> str:
        """Path to the JSON state file describing the running detached
        proxy. Single shared file per machine (one detached proxy at a
        time)."""
        import tempfile
        return os.path.join(tempfile.gettempdir(), ".geeViz_eeauth_proxy.json")

    @classmethod
    def _read_detached_state(cls) -> Optional[dict]:
        """Return the parsed state file contents, or ``None`` when the
        file is missing or unreadable."""
        path = cls._detached_state_path()
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    @classmethod
    def _write_detached_state(cls, state: dict) -> None:
        path = cls._detached_state_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            logger.exception("eeCreds: failed writing detached state %s", path)

    @classmethod
    def _clear_detached_state(cls) -> None:
        path = cls._detached_state_path()
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        """Cross-platform: is process ``pid`` currently alive?

        Critical Windows note: ``os.kill(pid, 0)`` on Windows does NOT
        check liveness — it calls ``TerminateProcess(pid, 0)``, which
        actually KILLS the process. A previous version of this code
        used ``os.kill(pid, 0)`` and was silently murdering the detached
        proxy on every liveness check. Always use the Win32 API
        ``OpenProcess`` + ``GetExitCodeProcess`` on Windows.
        """
        if pid <= 0:
            return False
        if os.name == "nt":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid,
            )
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                ok = kernel32.GetExitCodeProcess(
                    handle, ctypes.byref(exit_code),
                )
                if not ok:
                    return False
                return exit_code.value == STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
        except OSError:
            return False

    def _tenant_fingerprint(self) -> str:
        """sha256(16) over the sorted tenant names — same hash the
        proxy's ``/health`` endpoint computes. When this drifts from
        what the running proxy reports, we know the env has new SA
        env vars that aren't in the proxy yet, and we restart it."""
        import hashlib
        names = sorted(self._entries.keys())
        return hashlib.sha256(",".join(names).encode("utf-8")).hexdigest()[:16]

    @classmethod
    def _probe_detached_health(cls, url: str, timeout: float = 2.0) -> Optional[dict]:
        """GET ``<url>/health`` and return the parsed JSON, or ``None``
        on any failure (down, timeout, non-200, JSON parse error)."""
        try:
            import urllib.request as _urlreq
        except Exception:
            return None
        try:
            with _urlreq.urlopen(url.rstrip("/") + "/health", timeout=timeout) as resp:
                if getattr(resp, "status", 200) != 200:
                    return None
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    @classmethod
    def _kill_detached(cls, state: dict, *, timeout: float = 5.0) -> None:
        """Terminate the detached proxy referenced by ``state``. SIGTERM
        first, wait up to ``timeout`` seconds for graceful exit, then
        SIGKILL (or TerminateProcess on Windows)."""
        pid = int(state.get("pid", 0) or 0)
        if pid <= 0 or pid == os.getpid():
            return
        if not cls._pid_alive(pid):
            return
        try:
            if os.name == "nt":
                # Windows: send Ctrl+Break to the process group, then
                # TerminateProcess as the kill fallback.
                import signal as _sig
                try:
                    os.kill(pid, _sig.CTRL_BREAK_EVENT)
                except (AttributeError, OSError):
                    pass
            else:
                import signal as _sig
                os.kill(pid, _sig.SIGTERM)
        except Exception:
            pass
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not cls._pid_alive(pid):
                return
            time.sleep(0.2)
        # Still alive — hard kill.
        try:
            if os.name == "nt":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                PROCESS_TERMINATE = 1
                handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
                if handle:
                    kernel32.TerminateProcess(handle, 1)
                    kernel32.CloseHandle(handle)
            else:
                import signal as _sig
                os.kill(pid, _sig.SIGKILL)
        except Exception:
            pass

    def _spawn_detached(self, port: int) -> dict:
        """Spawn ``python -m geeViz.eeAuth`` as a detached background
        subprocess listening on ``port``. Inherits this process's env
        (so the same ``GEE_*`` discovery rules apply) but detaches
        stdin/stdout/stderr and runs in its own process group so the
        spawning script can exit without taking the proxy down.

        Waits up to ~15s for ``/health`` to respond before returning.
        Writes the state file on success. Raises on failure."""
        import subprocess as _sp
        url = f"http://127.0.0.1:{port}/ee-api"
        # The standalone runner uses --prefix /ee-api by default
        # (same as ``router(...)`` consumers) so the /health probe is
        # at ``<url>/health``. The runner reads SA tenants from env vars
        # via ``discover()`` — which is exactly what this parent
        # process did, so the child sees the same tenants.
        # Core command — same on all platforms.
        target_args = [
            sys.executable, "-m", "geeViz.eeAuth",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--prefix", "/ee-api",
            "--log-level", "WARNING",
        ]
        kwargs: dict = {
            "stdin": _sp.DEVNULL,
            "stdout": _sp.DEVNULL,
            "stderr": _sp.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            # Windows Job Object problem: when the parent process is in
            # a Job with KILL_ON_JOB_CLOSE (VS Code's terminal, many
            # CI runners, GitHub Actions, etc.), the child inherits the
            # Job and gets killed ~seconds after the parent exits. The
            # ``CREATE_BREAKAWAY_FROM_JOB`` Popen flag only works when
            # the Job permits breakaway — VS Code's doesn't.
            #
            # Workaround: launch through ``cmd /c start /B`` so the
            # process is created by ``cmd``, then ``cmd`` exits, leaving
            # the launched process as an orphan owned by the system.
            # ``/B`` = no new window. The empty ``""`` first arg to
            # ``start`` is the (ignored) window title — required when
            # the executable path contains spaces.
            quoted = " ".join(f'"{a}"' if " " in a else a for a in target_args)
            args = ["cmd", "/c", "start", "", "/B", *target_args]
            # ``CREATE_NO_WINDOW`` (0x08000000) suppresses the brief cmd
            # window flash. Mutually exclusive with ``DETACHED_PROCESS``
            # (which can ALLOCATE a fresh console for the child if the
            # parent has none) — pick CREATE_NO_WINDOW since we just
            # don't want any window, ever.
            kwargs["creationflags"] = (
                0x08000000  # CREATE_NO_WINDOW
                | getattr(_sp, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
                | getattr(_sp, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
            )
        else:
            args = target_args
            # New session = own process group + detached from parent's
            # controlling terminal. Survives parent exit on POSIX.
            kwargs["start_new_session"] = True
        try:
            proc = _sp.Popen(args, **kwargs)
        except Exception as e:
            raise RuntimeError(
                f"eeCreds: failed to spawn detached proxy on port {port}: {e}"
            ) from e
        # On Windows the cmd-wrapped Popen returns the PID of cmd.exe,
        # which exits immediately after dispatching. We need to track
        # the actual proxy python.exe PID. Discover it by health-probing
        # /health (which returns ``pid``) once it's up.
        # Wait for /health to come up. The child takes ~1-3s to import
        # everything and bind the socket; if it's not responsive after
        # ~15s something is wrong (port conflict, env error, etc.).
        deadline = time.time() + 15.0
        health = None
        # On Windows the launcher (cmd.exe) exits within ~50ms — that's
        # not a failure, it's the intended detach. Only treat
        # ``proc.poll() not None`` as fatal on POSIX where the Popen
        # PID IS the proxy. On Windows we rely on /health responding
        # to confirm the proxy actually started; if it doesn't, we
        # raise after the timeout.
        is_launcher = (os.name == "nt")
        while time.time() < deadline:
            if not is_launcher and proc.poll() is not None:
                raise RuntimeError(
                    f"eeCreds: detached proxy exited prematurely with code "
                    f"{proc.returncode}. Run "
                    f"`python -m geeViz.eeAuth --port {port}` directly to see "
                    f"the error."
                )
            health = self._probe_detached_health(url, timeout=1.0)
            if health is not None:
                break
            time.sleep(0.3)
        if health is None:
            raise RuntimeError(
                f"eeCreds: detached proxy on port {port} didn't respond to "
                f"/health within 15s. Run "
                f"`python -m geeViz.eeAuth --port {port}` directly to see "
                f"the error."
            )
        # Use the PID from /health — on Windows the Popen PID was the
        # cmd-launcher (already exited), not the actual proxy process.
        actual_pid = int(health.get("pid", 0) or proc.pid)
        state = {
            "pid": actual_pid,
            "port": port,
            "url": url,
            "version": health.get("version", ""),
            "tenant_fingerprint": health.get("tenant_fingerprint", ""),
            "started_at": health.get("started_at", ""),
            "python": sys.executable,
        }
        self._write_detached_state(state)
        logger.info(
            "eeCreds: spawned detached proxy pid=%s url=%s tenants=%s",
            proc.pid, url, health.get("tenants", []),
        )
        return state

    def _ensure_detached(self, proxy_port: int) -> dict:
        """``ensure_started(mode='detached')`` core. Discover tenants,
        compute expected tenant fingerprint, look at the state file:

        - No state file → spawn fresh
        - Stale state (PID dead, port unresponsive, version mismatch,
          tenant-fingerprint mismatch) → kill it, spawn fresh
        - Healthy state with matching fingerprint → attach
        """
        # Run discovery in THIS process first so we know what tenants
        # SHOULD be loaded. The child process will run its own
        # discover() at startup and (assuming the env is identical)
        # arrive at the same fingerprint. Discrepancy means the
        # detached process is stale — restart it.
        if not self._entries:
            try:
                self.discover()
            except Exception:
                logger.exception("eeCreds.ensure_detached: discovery failed")

        expected_fp = self._tenant_fingerprint()
        try:
            from geeViz import __version__ as _our_version
        except Exception:
            _our_version = ""

        # Inspect any existing detached proxy.
        state = self._read_detached_state()
        if state is not None:
            stale_reason = None
            pid = int(state.get("pid", 0) or 0)
            url = state.get("url") or ""
            if not self._pid_alive(pid):
                stale_reason = "pid not alive"
            elif not url:
                stale_reason = "no url in state"
            else:
                health = self._probe_detached_health(url)
                if health is None:
                    stale_reason = "health probe failed"
                elif (state.get("version") or "") and _our_version \
                        and health.get("version") != _our_version:
                    stale_reason = (
                        f"version mismatch (proxy={health.get('version')!r} "
                        f"client={_our_version!r})"
                    )
                elif health.get("tenant_fingerprint") != expected_fp:
                    stale_reason = (
                        f"tenant fingerprint mismatch "
                        f"(proxy={health.get('tenant_fingerprint')!r} "
                        f"expected={expected_fp!r})"
                    )

            if stale_reason is None:
                # Attach — set the inline-mode fields so callers that
                # read .proxy_url see the detached URL transparently.
                self._proxy_url = url
                logger.info(
                    "eeCreds: attached to detached proxy %s pid=%s",
                    url, pid,
                )
                return {
                    "proxy_url": url, "tenants": self.list(),
                    "current": self.current(),
                    "mode": "detached", "discovered": [],
                    "attached": True, "pid": pid,
                }

            logger.info(
                "eeCreds: detached proxy stale (%s); replacing", stale_reason,
            )
            self._kill_detached(state)
            self._clear_detached_state()

        # No usable existing proxy — spawn a new one.
        new_state = self._spawn_detached(proxy_port)
        self._proxy_url = new_state["url"]
        return {
            "proxy_url": new_state["url"], "tenants": self.list(),
            "current": self.current(),
            "mode": "detached", "discovered": [],
            "attached": False, "pid": new_state["pid"],
        }

    @classmethod
    def stop_detached(cls) -> bool:
        """Public helper: kill the detached proxy (if any) and clear
        the state file. Returns ``True`` if a process was actually
        terminated, ``False`` if there was nothing to kill."""
        state = cls._read_detached_state()
        if not state:
            return False
        cls._kill_detached(state)
        cls._clear_detached_state()
        return True

    @property
    def proxy_url(self) -> Optional[str]:
        """URL of the in-process proxy (if one's running). Useful for
        embedding into iframe URLs / Map exports so the JS side uses
        the same proxy."""
        return self._proxy_url

    def sync_oauth_project(self, project: str) -> int:
        """Update every OAuth entry's ``project_id`` to ``project`` and
        invalidate the cached access token so the next mint includes
        the new project on the ``x-goog-user-project`` header.

        Used by ``robustInitializer`` after the legacy ``ee.Initialize``
        fallback succeeds: discovery may have guessed a project the
        OAuth user can't access (e.g. ``gcloud config`` pointing at a
        service-account-owned project), but legacy init knows what
        ACTUALLY works. Syncing that back to the OAuth entries means
        subsequent ``Map.view()`` calls route through the proxy with
        the correct project instead of repeating the 403.

        Service-account entries are NOT touched — their project_id came
        from the SA JSON and is authoritative.

        Args:
            project: The known-good project ID.

        Returns:
            Number of entries actually updated.
        """
        if not project or project.lower() == "earthengine-legacy":
            return 0
        updated = 0
        with self._lock:
            for entry in self._entries.values():
                # SA entries have an authoritative project_id from their
                # JSON key — never overwrite that. OAuth and ADC entries
                # can both be missing/stale (Colab's ADC in particular
                # discovers no default project), so they get synced.
                if entry.type not in ("oauth", "adc"):
                    continue
                if entry.project_id == project:
                    continue
                logger.info(
                    "eeCreds: syncing %s entry %r project from %r to %r",
                    entry.type, entry.name,
                    entry.project_id or "<empty>", project,
                )
                entry.project_id = project
                # Invalidate cached token so the next get_token() includes
                # the new project on the response, and also drop the
                # cached Credentials object so ``_build_credentials`` will
                # re-run with the new project applied via
                # ``with_quota_project`` (ADC path).
                entry._token = {}
                entry._token_fetched_at = 0.0
                entry._creds = None
                updated += 1
        return updated

    # ─────────────── robust_init: the full bootstrap flow ───────────────
    def robust_init(self, *, verbose: bool = False,
                    interactive: bool = True) -> dict:
        """Best-effort EE initialization with the simplest possible UX.

        Decision tree (first hit wins, no prompts):

        1. EE already initialized AND a test call works → return as-is.
        2. eeAuth multi-tenant proxy via ``ensure_started`` → use it.
        3. ``ee.Initialize()`` with NO project arg → let EE's own
           resolution chain (credentials' ``quota_project_id`` → ADC →
           env vars) pick the project. This is the path that mirrors
           what ``ee.Initialize()`` would do if the user typed it
           themselves.
        4. Fallback: ``ee.Authenticate(force=True, auth_mode='localhost')``
           (interactive only) and re-run step 3.

        No project-id prompts. If a user wants a specific project they
        can call ``ee.Initialize(project='X')`` themselves before
        importing geeViz, or run ``earthengine set_project X`` /
        ``gcloud auth application-default set-quota-project X``.

        Returns a status dict::

            {"ok": bool,
             "source": "already-initialized" | "eeauth-proxy"
                     | "ee-auto-init" | "interactive-auth",
             "project": "..."}

        Raises ``RuntimeError`` when no path completes — e.g.
        non-interactive environment with no creds, or no quota project
        discoverable after a fresh authenticate.

        Args:
            verbose: Print progress to stdout.
            interactive: If False, skip the ``ee.Authenticate()``
                fallback and raise instead. Useful for daemons / CI
                where blocking on a browser would hang.
        """
        import ee

        def _verify_and_return_project() -> str:
            ee.Number(1).getInfo()
            return ee.data._get_state().cloud_api_user_project or ""

        def _announce_ready(project: str, source: str) -> None:
            """Single unconditional success line so the user knows
            things worked — especially valuable after the interactive
            auth path (Colab in particular emits a wall of noise from
            google-auth's GCE-metadata retries before the flow
            resolves). Skipped in the fast ``already-initialized``
            path since repeat imports would just print the same line
            over and over."""
            proj_msg = f"project={project!r}" if project else "no project set"
            print(f"geeViz: Earth Engine ready ({proj_msg}, source={source})")

        # 1. Already initialized + working?
        try:
            proj = _verify_and_return_project()
            if verbose:
                print(
                    f"geeViz: EE already initialized (project={proj!r})"
                )
            return {
                "ok": True, "source": "already-initialized",
                "project": proj,
            }
        except Exception:
            pass

        # 2. eeAuth proxy path. Default ``detached`` so multi-``Map.view()``
        # workflows and successive script runs reuse one long-lived proxy
        # process — no blocking ``input()`` at the end of each script, no
        # daemon-thread death dragging the browser tab down. Set
        # ``GEEVIZ_EEAUTH_MODE=auto`` to force the legacy in-process
        # daemon-thread proxy (one-shot, dies with the script). ``legacy``
        # skips proxy startup entirely.
        #
        # Exception: in Colab default to ``auto``. See geeView.py for
        # the full rationale — short version: the interactive project
        # prompt below only reaches the in-process tenant registry, so
        # a detached-mode proxy would sign every EE request without
        # ``x-goog-user-project`` and get 403. Auto mode keeps the
        # proxy in-process so ``sync_oauth_project`` after the prompt
        # actually takes effect.
        _default_mode = "auto" if "google.colab" in sys.modules else "detached"
        mode = os.environ.get("GEEVIZ_EEAUTH_MODE", _default_mode).lower()
        if mode != "legacy":
            try:
                status = self.ensure_started(mode=mode)
                if status.get("proxy_url"):
                    try:
                        proj = _verify_and_return_project()
                        if verbose:
                            print(
                                f"geeViz: initialized via eeAuth proxy "
                                f"({status['proxy_url']}, "
                                f"project={proj!r})"
                            )
                        _announce_ready(proj, "eeauth-proxy")
                        return {
                            "ok": True, "source": "eeauth-proxy",
                            "project": proj,
                            "proxy_url": status["proxy_url"],
                        }
                    except Exception as e:
                        if verbose:
                            print(
                                "geeViz: proxy started but EE call "
                                f"failed; falling back: {e}"
                            )
            except RuntimeError:
                # mode='proxy' demanded the proxy and it couldn't start.
                raise
            except Exception as e:
                if verbose:
                    print(
                        f"geeViz: eeAuth proxy unavailable, "
                        f"falling back: {e}"
                    )

        # 3a. Cached project from a previous prompt. When ``robust_init``
        #     prompted the user once (step 4 below), it cached the
        #     project id alongside the EE credentials file. Reuse it
        #     before falling through to a re-auth — otherwise every
        #     subsequent call would burn another ``ee.Authenticate(force=True)``
        #     OAuth roundtrip and re-prompt the user (Sphinx imports
        #     geeViz dozens of times during ``make html``).
        cached_project = self._read_cached_project()
        if cached_project:
            try:
                ee.Initialize(project=cached_project)
                proj = _verify_and_return_project() or cached_project
                if verbose:
                    print(
                        f"geeViz: EE initialized from cached project "
                        f"(project={proj!r})"
                    )
                if self._entries:
                    self.sync_oauth_project(proj)
                _announce_ready(proj, "ee-init-cached-project")
                return {"ok": True, "source": "ee-init-cached-project",
                        "project": proj}
            except Exception as e:
                if verbose:
                    print(
                        f"geeViz: cached project {cached_project!r} "
                        f"failed: {e}"
                    )
                # Cache is stale (project deleted, access revoked,
                # different Google account signed in). Wipe it so the
                # prompt path below can offer a fresh try instead of
                # silently re-attempting the same broken value on every
                # future run.
                self._clear_cached_project()

        # 3b. ``ee.Initialize()`` with no project. EE walks its own
        #     resolution chain (credentials.quota_project_id → ADC →
        #     env vars). On this user's machine this is what makes
        #     everything Just Work — they reported that bare
        #     ``ee.Initialize()`` succeeds and picks ``rcr-gee-ops`` from
        #     ADC, which is what we want to mirror.
        try:
            ee.Initialize()
            proj = _verify_and_return_project()
            if verbose:
                print(
                    f"geeViz: EE initialized (project={proj!r})"
                )
            if self._entries:
                self.sync_oauth_project(proj)
            _announce_ready(proj, "ee-auto-init")
            return {"ok": True, "source": "ee-auto-init", "project": proj}
        except Exception as e:
            if verbose:
                print(f"geeViz: ee.Initialize() failed: {e}")
            init_err = e

        # 4. Last resort: force a fresh auth and try once more.
        if not interactive:
            raise RuntimeError(
                "geeViz: ee.Initialize() failed and running "
                "non-interactively. Run "
                "`ee.Authenticate()` + `ee.Initialize(project=...)` "
                "before importing geeViz, or set "
                "$GOOGLE_APPLICATION_CREDENTIALS."
            ) from init_err

        # Hosted notebooks (Colab, Kaggle) run the Python kernel on a
        # remote VM, so ``auth_mode='localhost'`` opens a loopback server
        # the user's browser can't reach and the flow hangs. Detect those
        # and use the auth mode EE picks for that environment
        # (``colab`` in Colab → silent google.colab.auth flow, ``notebook``
        # for other hosted Jupyter → URL-and-code paste). Everywhere else
        # ``localhost`` remains the best desktop UX (auto-close browser tab,
        # no code paste). See ee.oauth.authenticate for the auto-detection
        # chain.
        if "google.colab" in sys.modules:
            print(
                "geeViz: running ee.Authenticate(force=True, "
                "auth_mode='colab') — Colab flow (localhost can't "
                "reach your browser from a hosted notebook)."
            )
            ee.Authenticate(force=True, auth_mode="colab")
        elif os.environ.get("KAGGLE_KERNEL_RUN_TYPE") or "kaggle_secrets" in sys.modules:
            print(
                "geeViz: running ee.Authenticate(force=True, "
                "auth_mode='notebook') — hosted notebook flow "
                "(copy the URL, sign in, paste the code back here)."
            )
            ee.Authenticate(force=True, auth_mode="notebook")
        else:
            print(
                "geeViz: running ee.Authenticate(force=True, "
                "auth_mode='localhost') — a browser window should open."
            )
            ee.Authenticate(force=True, auth_mode="localhost")
        try:
            ee.Initialize()
            proj = _verify_and_return_project()
            if verbose:
                print(
                    f"geeViz: EE initialized after auth (project={proj!r})"
                )
            if self._entries:
                self.sync_oauth_project(proj)
            _announce_ready(proj, "interactive-auth")
            return {
                "ok": True, "source": "interactive-auth", "project": proj,
            }
        except Exception as e:
            # Auth succeeded but no quota project came with the creds.
            # Restore the legacy ``simpleSetProject`` UX: prompt for a
            # project id, validate it against a live ``ee.Initialize``,
            # and only persist the value on success. Give the user a
            # few tries so a typo or an inaccessible project isn't
            # instantly fatal — a common Colab failure mode is signing
            # in with the wrong Google account, entering a project the
            # right account owns, and having the wrong account's EE
            # backend reject it. Three attempts is enough to survive a
            # typo and one account-swap without becoming annoying.
            MAX_PROJECT_ATTEMPTS = 3
            last_err: Exception = e
            for attempt in range(MAX_PROJECT_ATTEMPTS):
                proj = self._prompt_for_project(verbose=verbose)
                if not proj:
                    # No stdin (batch worker, closed pipe) or the user
                    # hit Enter to bail. Nothing else to try — surface
                    # the concrete remedies and re-raise.
                    raise RuntimeError(
                        f"geeViz: ee.Initialize() failed even after "
                        f"fresh authentication: {last_err}\n"
                        "No quota project could be auto-resolved and "
                        "no project id was entered. Set one explicitly "
                        "with one of:\n"
                        "  earthengine set_project YOUR_PROJECT\n"
                        "  gcloud auth application-default "
                        "set-quota-project YOUR_PROJECT\n"
                        "  ee.Initialize(project='YOUR_PROJECT')  "
                        "# before importing geeViz"
                    ) from last_err
                try:
                    ee.Initialize(project=proj)
                except Exception as e2:
                    last_err = e2
                    remaining = MAX_PROJECT_ATTEMPTS - attempt - 1
                    if remaining <= 0:
                        raise RuntimeError(
                            f"geeViz: ee.Initialize(project={proj!r}) "
                            f"failed after {MAX_PROJECT_ATTEMPTS} "
                            f"attempts: {e2}\n"
                            "Common causes:\n"
                            "  - Project id has a typo or does not "
                            "exist under this Google account\n"
                            "  - Project isn't registered for Earth "
                            "Engine (see https://earthengine.google.com"
                            "/noncommercial/)\n"
                            "  - Signed-in Google account lacks EE "
                            "access to the project (Colab: check the "
                            "account chip in the top-right)"
                        ) from e2
                    print(
                        f"\ngeeViz: project {proj!r} did not work "
                        f"({e2}).\nTry a different project id "
                        f"({remaining} attempt"
                        f"{'s' if remaining != 1 else ''} left)."
                    )
                    continue
                # Success — persist the working value so subsequent
                # runs pick it up from step 3a without re-prompting.
                self._write_cached_project(proj)
                if verbose:
                    print(
                        f"geeViz: EE initialized after auth + project "
                        f"prompt (project={proj!r})"
                    )
                if self._entries:
                    self.sync_oauth_project(proj)
                _announce_ready(proj, "interactive-auth-prompted-project")
                return {
                    "ok": True,
                    "source": "interactive-auth-prompted-project",
                    "project": proj,
                }

    @staticmethod
    def _project_cache_path() -> str:
        """Path to the ``<creds_path>.proj_id`` cache file used by
        ``_prompt_for_project`` / ``_read_cached_project``. Empty
        string when EE's oauth module can't tell us where to put it."""
        try:
            import ee.oauth as _ee_oauth
            creds_path = _ee_oauth.get_credentials_path()
        except Exception:
            return ""
        return os.path.normpath(f"{creds_path}.proj_id") if creds_path else ""

    @classmethod
    def _read_cached_project(cls) -> str:
        """Read the cached project id if one exists. Used by step 3a
        of ``robust_init`` to short-circuit before any auth path
        — once the user has answered the prompt once, subsequent calls
        in the same env should never re-auth or re-prompt."""
        cache = cls._project_cache_path()
        if not cache or not os.path.isfile(cache):
            return ""
        try:
            return open(cache, "r", encoding="utf-8").read().strip()
        except Exception:
            return ""

    @classmethod
    def _prompt_for_project(cls, *, verbose: bool = False) -> str:
        """Ask the user once for a GEE project ID.

        Does NOT cache — the caller must validate against
        ``ee.Initialize`` first and only persist on success
        (``_write_cached_project``). A cached failure would otherwise
        poison every subsequent run.

        Returns the entered project id, or ``""`` when there is no
        stdin (closed pipe / daemon / batch worker) so the caller can
        decide whether to raise instead of blocking forever.
        """
        try:
            entered = input("Please enter GEE project ID: ").strip()
        except (EOFError, OSError):
            return ""
        if not entered:
            return ""
        print(f"You entered: {entered}")
        return entered

    @classmethod
    def _write_cached_project(cls, project: str) -> None:
        """Persist a project id next to the EE credentials file so
        subsequent runs (and step 3a of ``robust_init``) can reuse it
        without another prompt.

        Called ONLY after ``ee.Initialize(project=project)`` succeeds,
        so a bad guess can't be baked into the cache.
        """
        cache = cls._project_cache_path()
        if not cache:
            return
        cache_dir = os.path.dirname(cache)
        if cache_dir and not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir, exist_ok=True)
            except Exception:
                pass
        try:
            with open(cache, "w", encoding="utf-8") as f:
                f.write(project)
        except Exception:
            pass

    @classmethod
    def _clear_cached_project(cls) -> None:
        """Remove the cached project file when its stored value no
        longer works (project deleted, access revoked, wrong account
        signed in). Silent on missing file; best-effort on delete
        failure so the caller doesn't die just because it couldn't
        clean up a stale cache."""
        cache = cls._project_cache_path()
        if not cache:
            return
        try:
            if os.path.exists(cache):
                os.remove(cache)
        except Exception:
            pass

    # ─────────────── ensure_started: discover + start in one call ───────────────
    def ensure_started(
        self,
        *,
        mode: str = "auto",
        proxy_port: int = _DEFAULT_PROXY_PORT,
    ) -> dict:
        """Idempotent "I want the proxy running, please" helper used by
        ``Map.view()`` and any other code that wants to ride the eeCreds
        proxy without forcing the user to call ``addCreds`` + ``start``.

        Modes:

        - ``"auto"``: try discovery + start (inline daemon thread). If
          anything fails, return a status dict with ``proxy_url=""`` —
          caller can fall back.
        - ``"proxy"``: try discovery + start (inline daemon thread).
          RAISE if nothing can be discovered or the proxy fails to bind.
        - ``"detached"``: attach to or spawn a long-lived background
          subprocess running ``python -m geeViz.eeAuth``. Survives the
          calling script's exit, so multi-``Map.view()`` workflows and
          successive script invocations all share one proxy without
          needing the blocking ``input()`` at the end of each. The
          subprocess is identified by a state file at
          ``<tmp>/.geeViz_eeauth_proxy.json``; clients verify version +
          tenant fingerprint via ``/health`` and respawn if anything
          drifted.
        - ``"legacy"``: do nothing. Returns immediately with ``""``.

        Returns ``{proxy_url, tenants, current, mode, discovered}``.
        ``proxy_url == ""`` means caller should fall back.
        """
        m = (mode or "auto").lower()
        if m not in ("auto", "proxy", "detached", "legacy"):
            raise ValueError(
                f"eeCreds.ensure_started: mode must be auto/proxy/detached/"
                f"legacy, got {mode!r}"
            )

        if m == "legacy":
            return {
                "proxy_url": "", "tenants": self.list(),
                "current": "", "mode": m, "discovered": [],
            }

        if m == "detached":
            return self._ensure_detached(proxy_port)

        if self._started and self._proxy_url:
            return self._status_for_ensure(m, discovered=[])

        discovered: list[str] = []
        if not self._entries:
            try:
                discovered = self.discover()
            except Exception:
                logger.exception("eeCreds.ensure_started: discovery failed")

        if not self._entries:
            if m == "proxy":
                raise RuntimeError(
                    "eeCreds.ensure_started(mode='proxy'): no credentials "
                    "could be auto-discovered. Either set "
                    "GOOGLE_APPLICATION_CREDENTIALS, run "
                    "`earthengine authenticate`, or call "
                    "eeCreds.addCreds(...) manually before this."
                )
            # mode='auto' → silent fallback
            return {
                "proxy_url": "", "tenants": [], "current": "",
                "mode": m, "discovered": discovered,
            }

        try:
            self.start(proxy_port=proxy_port)
        except Exception:
            logger.exception(
                "eeCreds.ensure_started: start() failed; falling back"
            )
            if m == "proxy":
                raise
            return {
                "proxy_url": "", "tenants": self.list(),
                "current": self.current(),
                "mode": m, "discovered": discovered,
            }

        return self._status_for_ensure(m, discovered=discovered)

    def _status_for_ensure(self, mode: str, discovered: list) -> dict:
        return {
            "proxy_url": self._proxy_url or "",
            "tenants": self.list(),
            "current": self.current(),
            "mode": mode,
            "discovered": discovered,
        }

    def _status(self) -> dict:
        return {
            "started": self._started,
            "proxy_url": self._proxy_url,
            "tenants": self.list(),
            "current": self.current(),
        }


class _UseContext:
    """Return value of ``eeCreds.use(name)``. Acts as both a plain
    statement (the side effect of switching is immediate) AND a context
    manager (restores the previous tenant on exit)."""
    def __init__(self, parent: EECreds, name: str):
        self._parent = parent
        self._name = name
        # Switch immediately — supports the no-with style
        self._token = set_tenant(name)
        self._used_as_context = False

    def __enter__(self):
        self._used_as_context = True
        # set_tenant was already called in __init__; the token captured
        # there is what we restore on exit.
        return self._parent

    def __exit__(self, exc_type, exc_val, exc_tb):
        reset_tenant(self._token)
        return False  # don't swallow exceptions


# ──────────────────────── robust_init helpers ────────────────────────
def _diagnose_ee_credentials() -> dict:
    """Best-effort: identify what creds EE will end up using, BEFORE
    ``ee.Initialize`` makes that decision silently.

    Returns ``{has_ee_refresh_token, ee_project, has_adc, adc_project}``.

    Why it matters: ``ee.data.get_persistent_credentials()`` falls
    through to ADC when the EE credentials file has no ``refresh_token``,
    and ``ee.Authenticate()`` short-circuits when those ADC creds are
    "valid enough" — meaning a user who deleted their EE token and
    expects a fresh auth flow gets gcloud creds + gcloud's quota_project
    used silently. This helper surfaces what's happening.
    """
    out = {
        "has_ee_refresh_token": False,
        "ee_project": "",
        "has_adc": False,
        "adc_project": "",
    }
    try:
        import ee.oauth as _ee_oauth
        args = _ee_oauth.get_credentials_arguments()
        out["has_ee_refresh_token"] = bool(args.get("refresh_token"))
        # get_credentials_arguments() maps the JSON 'project' field
        # to 'quota_project_id' in its return value.
        out["ee_project"] = args.get("quota_project_id") or ""
    except (OSError, FileNotFoundError):
        pass
    except Exception:
        logger.debug(
            "eeCreds._diagnose: EE credentials file unreadable", exc_info=True,
        )
    try:
        import google.auth
        import google.auth.exceptions
        try:
            creds, _proj = google.auth.default()
            out["has_adc"] = creds is not None
        except google.auth.exceptions.DefaultCredentialsError:
            pass
    except Exception:
        logger.debug(
            "eeCreds._diagnose: google.auth.default() unavailable", exc_info=True,
        )
    try:
        import ee.oauth as _ee_oauth
        out["adc_project"] = _ee_oauth.get_appdefault_project() or ""
    except Exception:
        pass
    return out


def _save_ee_project_to_credentials_file(project: str) -> None:
    """Persist ``project`` to the EE credentials JSON's ``project`` field
    so the next session picks it up without prompting.

    Matches ``earthengine set_project`` semantics — writes to the same
    file via ``ee.oauth.write_private_json`` (atomic, 0600 perms).
    Best-effort: failures are logged but don't raise.
    """
    if not project:
        return
    try:
        import ee.oauth as _ee_oauth
        path = _ee_oauth.get_credentials_path()
        config: dict = {}
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (OSError, json.JSONDecodeError):
                config = {}
        config["project"] = project
        _ee_oauth.write_private_json(path, config)
        logger.info(
            "eeCreds: saved project %r to EE credentials file", project,
        )
    except Exception as e:
        logger.warning(
            "eeCreds: could not persist project to EE credentials file: %s", e,
        )


# ──────────────────────── Module-level singleton ────────────────────────
# Users who want zero ceremony do ``from geeViz.eeAuth import eeCreds``.
# Users who want their own isolated registry do
# ``from geeViz.eeAuth.eeCreds import EECreds; my = EECreds()``.
eeCreds = EECreds()
