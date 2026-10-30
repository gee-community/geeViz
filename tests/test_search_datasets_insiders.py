"""search_datasets says when a community dataset cannot be read.

Session 320fcf96 (2026-10-29), "what greenhouse gas data do you have
access to": the answer listed Carbon Mapper plumes under
``projects/sat-io/open-datasets/carbon-mapper/*`` as data on hand. The
next question asked for a Carbon Mapper plume map; both ids failed with
"Asset not found" and the agent fell back to another product. The
community catalog files those ids, with 27 others, under "Insiders only
datasets": they are not public, and none of the 30 can be read here.
Results in that group now say so.
"""
import json

import geeViz.mcp.server as srv

CATALOG = [
    {"id": "projects/sat-io/open-datasets/carbon-mapper/plume_geo",
     "title": "Carbon Mapper Data Portal Methane Emissions: Plume",
     "type": "image_collection", "provider": "Carbon Mapper, Inc.",
     "tags": "Methane Emissions", "thematic_group": "Insiders only datasets",
     "docs": "https://gee-community-catalog.org/projects/cmapper/"},
    {"id": "projects/sat-io/open-datasets/some/methane_public",
     "title": "Public Methane Grid", "type": "image",
     "provider": "Someone", "tags": "Methane Emissions",
     "thematic_group": "Climate", "docs": ""},
]


def _search(monkeypatch, query):
    monkeypatch.setattr(srv, "_get_cached_catalog",
                        lambda src: CATALOG if src == "community" else [])
    return {r["id"]: r for r in json.loads(srv.search_datasets(query))["results"]}


def test_an_insiders_only_dataset_is_marked_unreadable(monkeypatch):
    r = _search(monkeypatch, "methane")["projects/sat-io/open-datasets/carbon-mapper/plume_geo"]
    assert "cannot be read" in r["access"]


def test_a_public_community_dataset_is_not_marked(monkeypatch):
    r = _search(monkeypatch, "methane")["projects/sat-io/open-datasets/some/methane_public"]
    assert "access" not in r
