"""Library HTTP helpers must not reach the cloud metadata service.

Found while evaluating a checklist that named 169.254.169.254 as a
must-block. Checking whether that applied here turned up a live SSRF
that the MCP import blocklist could not see:

    from geeViz import esriLib
    esriLib.getServiceMetadata('http://example.com')

``getServiceMetadata`` is PUBLIC and takes a URL. It runs in a geeViz
frame, and _called_from_trusted_lib trusts the geeViz tree, so the
sandbox's HTTP-library block never applies. Verified with urllib3 fully
blocked: that call fetched example.com and returned the response body
inside the exception message — outbound HTTP *and* read-back, from a
sandbox that supposedly had neither.

On Cloud Run the payoff is concrete: 169.254.169.254 hands the runtime
service account's OAuth token to anything that can make a local HTTP
request.

This guard is not a boundary. It closes loopback / private / link-local
and the file:// scheme. Any public host is still reachable, which is what
network egress control is for — the guard removes the cheap credential
grab, it does not replace the network policy.
"""
import ipaddress
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from geeViz._ssrf import BlockedAddressError, check_url, _is_forbidden  # noqa: E402


@pytest.mark.parametrize("ip", [
    "169.254.169.254",   # GCP / AWS / Azure instance metadata
    "127.0.0.1", "::1",  # other services on the same host
    "10.0.0.1", "172.16.0.1", "192.168.1.1",   # RFC1918, inside the VPC
    "0.0.0.0",
])
def test_forbidden_addresses(ip):
    assert _is_forbidden(ip) is True


@pytest.mark.parametrize("ip", ["8.8.8.8", "142.250.72.206", "1.1.1.1"])
def test_public_addresses_are_allowed(ip):
    assert _is_forbidden(ip) is False


def test_link_local_is_checked_specifically():
    """169.254/16 is the whole reason this module exists. A test that
    only goes through check_url() can pass on some other rule catching
    the address first."""
    assert _is_forbidden("169.254.169.254") is True
    assert _is_forbidden("169.254.0.1") is True
    src = (ROOT / "_ssrf.py").read_text(encoding="utf-8")
    code = chr(10).join(l.split("#")[0] for l in src.splitlines())
    assert "is_link_local" in code, (
        "the link-local check is gone — metadata is reachable again")


def test_the_metadata_endpoint_is_refused_by_url():
    with pytest.raises(BlockedAddressError) as e:
        check_url("http://169.254.169.254/computeMetadata/v1/instance/"
                  "service-accounts/default/token")
    assert "169.254.169.254" in str(e.value)


@pytest.mark.parametrize("scheme", ["file", "ftp", "gopher", "data"])
def test_only_http_schemes_are_allowed(scheme):
    """file:// would turn every fetch helper into an arbitrary file read.

    Asserts on the REASON, not just that something raised. The first
    version used ``file:///etc/passwd``, which has no host — so it
    raised "No host in URL" and passed even with `file` added to
    ALLOWED_SCHEMES. Mutation testing caught it: the test could not
    fail.
    """
    with pytest.raises(BlockedAddressError) as e:
        check_url(f"{scheme}://example.com/etc/passwd")
    assert "scheme" in str(e.value).lower(), (
        f"{scheme}:// was refused for the wrong reason: {e.value}")


def test_unparseable_addresses_are_refused_not_guessed():
    assert _is_forbidden("not-an-ip") is True


def test_a_dns_failure_is_not_reported_as_a_security_block():
    """An ordinary typo must produce the real DNS error from the request,
    not a misleading 'blocked address' message."""
    assert check_url("http://this-host-does-not-exist-xyzzy.invalid/x")


# ── every helper that fetches must consult the guard ───────────────────

@pytest.mark.parametrize("mod,call", [
    ("esriLib.py", "urlopen"),
    ("googleMapsLib.py", "urlopen"),
])
def test_every_fetch_site_is_guarded(mod, call):
    """One unguarded helper is the whole hole again — they all take a URL
    and they are all reachable from a trusted frame."""
    src = (ROOT / mod).read_text(encoding="utf-8")
    code = [l for l in src.splitlines() if not l.strip().startswith("#")]
    body = "\n".join(code)
    assert "_check_url" in body, f"{mod} fetches without calling the guard"
    n_fetch = len(re.findall(re.escape(call), body))
    n_guard = len(re.findall(r"_check_url\(", body))
    assert n_guard >= n_fetch, (
        f"{mod}: {n_fetch} fetch call(s) but only {n_guard} guard call(s)")


def test_edw_and_fs_insights_make_no_requests_of_their_own():
    """They delegate to georest, whose connections the MCP sandbox holds to
    the same policy (``_connect_refusal`` refuses georest frames too), so a
    fetch reappearing here would need its own guard."""
    for mod in ("edwLib.py", "fsInsights/__init__.py"):
        src = (ROOT / mod).read_text(encoding="utf-8")
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        for call in ("urlopen", "requests.", "http.client", "socket"):
            assert call not in code, f"{mod} fetches ({call}) without the guard"
