"""The wire contract: DTOs and the enums they publish."""

import pytest


class TestEnumContract:
    """The gap this refactor closed: allowed values used to live only in prose, so
    the document declared `"type": "string"` and a generated client got nothing."""

    def test_kind_is_a_declared_enum(self, client):
        doc = client.get("/openapi.json").json()
        ref = doc["components"]["schemas"]["NoteIn"]["properties"]["kind"]["$ref"]
        name = ref.rsplit("/", 1)[-1]
        assert doc["components"]["schemas"][name]["enum"] == [
            "area", "project", "epic", "task", "subtask", "routine",
            "doc", "decision", "meeting", "review"]

    def test_enums_come_from_the_domain(self, client):
        from planner.domain import ISSUE_TYPE
        doc = client.get("/openapi.json").json()
        found = {name: s["enum"] for name, s in doc["components"]["schemas"].items()
                 if "enum" in s}
        assert list(ISSUE_TYPE) in found.values()

    @pytest.mark.parametrize("bad", ["Epic", "EPIC", "epicc", " epic "])
    def test_misspelling_or_miscasing_kind_is_rejected(self, client, bad):
        r = client.post("/notes", json={"kind": bad, "title": "X"})
        assert r.status_code == 422
        assert r.json()["field"] == "kind"

    @pytest.mark.parametrize("field,bad", [
        ("status", "Doing"), ("type", "Bug"), ("recur", "Daily")])
    def test_vocabulary_casing_is_rejected_with_the_field(self, client, field, bad):
        kind = "routine" if field == "recur" else "task"
        r = client.post("/notes", json={"kind": kind, "title": "X", field: bad})
        assert r.status_code == 422 and r.json()["field"] == field

    def test_one_error_shape_for_both_layers(self, client):
        """A DTO rejection and a domain rejection must look the same to a client --
        which of the two fired is an implementation detail."""
        from_dto = client.post("/notes", json={"kind": "task", "title": "A",
                                               "status": "Doing"}).json()
        from_domain = client.post("/notes", json={"kind": "meeting", "title": "B",
                                                  "status": "todo"}).json()
        assert set(from_dto) == set(from_domain) == {"detail", "field"}
