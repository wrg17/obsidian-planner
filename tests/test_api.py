"""The HTTP surface, including the OpenAPI document itself."""

import pytest


class TestSchemaEndpoint:
    def test_publishes_every_kind(self, client):
        body = client.get("/schema").json()
        assert {k["name"] for k in body["kinds"]} == {
            "area", "project", "epic", "task", "subtask", "routine",
            "doc", "decision", "meeting", "review"}

    def test_vocabularies_are_published(self, client):
        vocab = client.get("/schema").json()["vocabularies"]
        assert "doing" in vocab["ticket_status"]
        assert vocab["priority_range"] == [1, 4]

    def test_matches_what_the_server_enforces(self, client):
        """The docs are generated from the module the vault validates against, so a
        drift between them would be a bug in one place, not two."""
        task = next(k for k in client.get("/schema").json()["kinds"] if k["name"] == "task")
        assert task["default_status"] == "todo"
        assert "blocked_by" in task["fields"]
        assert task["parent_kinds"] == ["epic", "project", "meeting"]


class TestOpenApi:
    def test_document_is_served(self, client):
        assert client.get("/openapi.json").status_code == 200

    def test_swagger_ui_is_served(self, client):
        r = client.get("/docs")
        assert r.status_code == 200 and "swagger" in r.text.lower()

    def test_root_redirects_to_docs(self, client):
        assert client.get("/", follow_redirects=False).headers["location"] == "/docs"

    def test_every_route_is_documented(self, client):
        doc = client.get("/openapi.json").json()
        for path in ("/notes", "/notes/{title}", "/notes/{title}/close",
                     "/schema", "/problems"):
            assert path in doc["paths"], f"{path} missing from OpenAPI"

    def test_operations_carry_summaries_and_tags(self, client):
        doc = client.get("/openapi.json").json()
        for path, ops in doc["paths"].items():
            for verb, op in ops.items():
                assert op.get("tags"), f"{verb.upper()} {path} has no tag"
                assert op.get("summary") or op.get("description"), \
                    f"{verb.upper()} {path} is undocumented"

    def test_error_shapes_are_declared(self, client):
        doc = client.get("/openapi.json").json()
        assert "422" in doc["paths"]["/notes"]["post"]["responses"]


class TestListNotes:
    def test_lists_everything(self, client):
        assert len(client.get("/notes").json()) == 6

    def test_filter_by_kind(self, client):
        body = client.get("/notes", params={"kind": "task"}).json()
        assert [n["title"] for n in body] == ["Pick a type scale"]

    def test_filter_by_project(self, client):
        body = client.get("/notes", params={"project": "Website relaunch"}).json()
        assert "Studio" not in [n["title"] for n in body]

    def test_open_filter(self, client):
        client.post("/notes/Pick a type scale/close")
        titles = [n["title"] for n in client.get("/notes",
                                                 params={"kind": "task", "open": True}).json()]
        assert titles == []

    def test_unknown_kind_is_422(self, client):
        assert client.get("/notes", params={"kind": "epicc"}).status_code == 422


class TestCrud:
    def test_create_returns_201_and_defaults(self, client):
        r = client.post("/notes", json={"kind": "task", "title": "New task"})
        assert r.status_code == 201
        assert r.json()["status"] == "todo"

    def test_create_accepts_plain_titles_for_links(self, client):
        """Callers should not need to know [[wikilink]] syntax."""
        r = client.post("/notes", json={
            "kind": "subtask", "title": "S", "parent": "Pick a type scale"})
        assert r.json()["parent"] == "Pick a type scale"

    def test_duplicate_title_is_409(self, client):
        r = client.post("/notes", json={"kind": "doc", "title": "Studio"})
        assert r.status_code == 409

    def test_invalid_vocabulary_is_422_with_the_field(self, client):
        r = client.post("/notes", json={
            "kind": "task", "title": "Bad", "status": "in-progress"})
        assert r.status_code == 422
        assert r.json()["field"] == "status"

    def test_priority_out_of_range_is_rejected_by_the_model(self, client):
        assert client.post("/notes", json={
            "kind": "task", "title": "Bad", "priority": 9}).status_code == 422

    def test_unknown_field_is_rejected(self, client):
        assert client.post("/notes", json={
            "kind": "task", "title": "Bad", "nonsense": 1}).status_code == 422

    def test_get_one(self, client):
        assert client.get("/notes/Design system").json()["kind"] == "epic"

    def test_get_missing_is_404(self, client):
        assert client.get("/notes/Nope").status_code == 404

    def test_patch_changes_only_what_is_sent(self, client):
        client.patch("/notes/Pick a type scale", json={"status": "review"})
        body = client.get("/notes/Pick a type scale").json()
        assert body["status"] == "review" and body["priority"] == 1

    def test_patch_with_null_removes(self, client):
        client.patch("/notes/Pick a type scale", json={"due": None})
        assert "due" not in client.get("/notes/Pick a type scale").json()

    def test_delete_then_404(self, client):
        assert client.delete("/notes/Test at 320px").status_code == 204
        assert client.get("/notes/Test at 320px").status_code == 404


class TestClose:
    def test_sets_the_three_fields_together(self, client):
        body = client.post("/notes/Pick a type scale/close").json()
        assert body["status"] == "done"
        assert body["done"] is True
        assert "closed" in body

    def test_cancelled(self, client):
        body = client.post("/notes/Pick a type scale/close",
                           params={"status": "cancelled"}).json()
        assert body["status"] == "cancelled" and body["done"] is False

    def test_non_closing_status_is_422(self, client):
        assert client.post("/notes/Pick a type scale/close",
                           params={"status": "doing"}).status_code == 422


class TestProblems:
    def test_clean_vault_is_empty(self, client):
        assert client.get("/problems").json() == []

    def test_reports_a_hand_edited_typo(self, client, populated):
        (populated.repo.root / "Items" / "Typo.md").write_text(
            "---\nkind: task\nstatus: in-progress\n---\n")
        found = client.get("/problems").json()
        assert any(p["title"] == "Typo" for p in found)


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


class TestMiddleware:
    def test_request_id_is_returned(self, client):
        assert client.get("/notes").headers["x-request-id"]

    def test_supplied_request_id_is_echoed(self, client):
        r = client.get("/notes", headers={"x-request-id": "abc123"})
        assert r.headers["x-request-id"] == "abc123"

    def test_timing_header(self, client):
        assert float(client.get("/notes").headers["x-response-time-ms"]) >= 0

    def test_errors_carry_the_request_id_too(self, client):
        r = client.get("/notes/Nope", headers={"x-request-id": "trace-me"})
        assert r.status_code == 404 and r.headers["x-request-id"] == "trace-me"


class TestHierarchy:
    def test_direct_children(self, client):
        body = client.get("/notes/Design system/children").json()
        assert [n["title"] for n in body] == ["Pick a type scale"]

    def test_recursive_children(self, client):
        body = client.get("/notes/Design system/children",
                          params={"recursive": True}).json()
        assert {n["title"] for n in body} == {"Pick a type scale", "Test at 320px"}

    def test_missing_parent_is_404_not_an_empty_list(self, client):
        assert client.get("/notes/Nope/children").status_code == 404


class TestReopen:
    def test_clears_closed_and_done(self, client):
        client.post("/notes/Pick a type scale/close")
        body = client.post("/notes/Pick a type scale/reopen",
                           params={"status": "doing"}).json()
        assert body["status"] == "doing"
        assert body["done"] is False
        assert "closed" not in body


class TestHealth:
    def test_reports_the_vault(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok" and body["vault"]
