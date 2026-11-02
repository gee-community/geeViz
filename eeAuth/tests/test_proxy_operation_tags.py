"""The proxy tags compute with a workload tag, and leaves operation calls
untagged.

Earth Engine refuses a workloadTag on ``operations/<id>:cancel`` ("Unknown
name workloadTag: Cannot bind query parameter"). The proxy added one to
every POST, so every export cancel through it failed: the export kept
running, and kept billing.
"""
import httpx
import pytest


class _Creds:
    def get_token(self, tenant=None):
        return {"access_token": "tok", "tenant": "t", "project_id": "p"}


@pytest.fixture
def proxy(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    sent = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def request(self, method, url, content=None, headers=None):
            sent.append((method, url))
            return httpx.Response(200, json={}, request=httpx.Request(method, url))

        async def aclose(self):
            pass

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    from geeViz.eeAuth.server import build_proxy_router

    app = FastAPI()
    app.include_router(build_proxy_router(creds=_Creds(), workload_tag_builder=lambda req, t: "wl-tag-1"),
                       prefix="/ee-api")
    return TestClient(app), sent


def test_compute_is_tagged(proxy):
    client, sent = proxy
    client.post("/ee-api/v1/projects/p/value:compute", json={})
    assert sent and "workloadTag=wl-tag-1" in sent[-1][1]


def test_an_operation_cancel_is_not_tagged(proxy):
    client, sent = proxy
    client.post("/ee-api/v1/projects/p/operations/ABC123:cancel?workloadTag=client-tag", json={})
    assert sent, "the cancel never reached Earth Engine"
    assert "workloadTag" not in sent[-1][1], sent[-1][1]
    assert sent[-1][1].endswith("/v1/projects/p/operations/ABC123:cancel")


def test_operation_paths_are_recognized():
    from geeViz.eeAuth.server import _is_operation_call

    assert _is_operation_call("v1/projects/p/operations/X:cancel")
    assert _is_operation_call("/v1/projects/p/operations/X")
    assert not _is_operation_call("v1/projects/p/value:compute")
    assert not _is_operation_call("v1/projects/p/image:export")
