"""A workload tag the client put in the request BODY counts as the
client's tag, the same as one in the query.

The Earth Engine SDK puts the tag in the query for ``getMapId`` (so every
tile URL) and in the JSON body for ``value:compute``, ``computePixels``
and every export. Tag builders read only the query, so a body tag was
never seen: the proxy minted its own in its place, and an export's usage
reached Cloud Monitoring under a tag nobody had registered.
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

    sent, seen = [], []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def request(self, method, url, content=None, headers=None):
            sent.append((method, url, content))
            return httpx.Response(200, json={}, request=httpx.Request(method, url))

        async def aclose(self):
            pass

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    from geeViz.eeAuth.server import build_proxy_router

    def builder(req, tenant):
        # The library's own rule: a client tag wins, else mint.
        client_tag = req.query_params.get("workloadTag")
        seen.append(client_tag)
        return client_tag or "minted-by-proxy"

    app = FastAPI()
    app.include_router(build_proxy_router(creds=_Creds(), workload_tag_builder=builder), prefix="/ee-api")
    return TestClient(app), sent, seen


@pytest.mark.parametrize("path", ["v1/projects/p/value:compute", "v1/projects/p/image:computePixels",
                                  "v1/projects/p/image:export", "v1/projects/p/table:export"])
def test_a_body_tag_reaches_the_builder_and_earth_engine(proxy, path):
    client, sent, seen = proxy
    body = {"expression": {"values": {}}, "workloadTag": "wl_export_abc__test"}
    client.post(f"/ee-api/{path}", json=body)
    assert seen[-1] == "wl_export_abc__test"
    assert "workloadTag=wl_export_abc__test" in sent[-1][1]
    assert "minted-by-proxy" not in sent[-1][1]


def test_the_body_is_forwarded_unchanged(proxy):
    client, sent, _ = proxy
    client.post("/ee-api/v1/projects/p/image:export", json={"workloadTag": "wl_x", "description": "d"})
    import json
    assert json.loads(sent[-1][2]) == {"workloadTag": "wl_x", "description": "d"}


def test_without_a_tag_anywhere_the_proxy_mints(proxy):
    client, sent, seen = proxy
    client.post("/ee-api/v1/projects/p/value:compute", json={"expression": {}})
    assert seen[-1] is None
    assert "workloadTag=minted-by-proxy" in sent[-1][1]


def test_a_query_tag_outranks_a_body_tag(proxy):
    client, sent, seen = proxy
    client.post("/ee-api/v1/projects/p/value:compute?workloadTag=from-query",
                json={"workloadTag": "from-body"})
    assert seen[-1] == "from-query"
    assert sent[-1][1].count("workloadTag=") == 1


def test_other_query_parameters_survive(proxy):
    client, sent, seen = proxy
    client.post("/ee-api/v1/projects/p/value:compute?prettyPrint=false", json={"workloadTag": "wl_y"})
    assert seen[-1] == "wl_y"
    assert "prettyPrint=false" in sent[-1][1]


def test_an_operation_call_is_still_untagged(proxy):
    client, sent, _ = proxy
    client.post("/ee-api/v1/projects/p/operations/ABC:cancel", json={"workloadTag": "wl_z"})
    assert "workloadTag" not in sent[-1][1]


@pytest.mark.parametrize("body,expect", [
    (b'{"workloadTag": "wl_a"}', "wl_a"),
    (b'{"workloadTag": " wl_a "}', "wl_a"),
    (b'{"expression": {}}', ""),
    (b"", ""),
    (b"not json \"workloadTag\"", ""),
    (b'["workloadTag"]', ""),
    (b'{"workloadTag": 5}', ""),
    (b'{"workloadTag": ""}', ""),
])
def test_reading_the_body_tag(body, expect):
    from geeViz.eeAuth.server import _body_workload_tag
    assert _body_workload_tag(body) == expect
