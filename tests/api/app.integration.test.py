"""System invariants S1-S9, and the OpenAPI document the app publishes about itself.

Per-endpoint rules are tested next to their routers. These are the cross-cutting ones:
properties that must hold at *every* endpoint, so they are asserted by sweeping the
whole surface rather than by picking examples. A new endpoint that violates one fails
here without anyone having to remember to test it.

The identifiers match the module docstring of src/planner/api/app.py.
"""

import pytest


def _all_operations(client):
    """(method, path, operation) for every documented route."""
    doc = client.get("/openapi.json").json()
    for path, ops in doc["paths"].items():
        for verb, op in ops.items():
            yield verb, path, op


# =====================================================================================
# S1  CLOSURE -- no operation may produce a state another would refuse
# =====================================================================================

class TestS1Closure:
    def test_no_sequence_of_writes_leaves_a_dangling_parent(self, client):
        """The property DELETE's 409 exists to protect."""
        client.delete("/notes/Design system")                       # refused
        client.delete("/notes/Website relaunch")                    # refused
        client.patch("/notes/Pick a type scale", json={"parent": "Nope"})  # refused
        assert client.get("/problems").json() == []

    def test_cascade_leaves_no_structural_break(self, client):
        """Closure is absolute for structural links: after a cascade, nothing points
        at a parent/project/area that is gone."""
        client.delete("/notes/Design system", params={"cascade": True})
        structural = [p for p in client.get("/problems").json()
                      if any(f in p["message"] for f in ("parent", "project", "area"))]
        assert structural == []

    def test_reference_links_are_the_one_documented_exception(self, client):
        """Deleting a blocker is legitimate, so `blocked_by` may be left dangling --
        and is reported rather than silently rewritten. This is the sole way a
        well-behaved client can put a row in /problems."""
        client.delete("/notes/Design system", params={"cascade": True})
        reported = client.get("/problems").json()
        assert [p["title"] for p in reported] == ["Export old posts"]
        assert "blocked_by" in reported[0]["message"]

    def test_reference_links_cannot_be_created_dangling(self, client):
        """The write side is still closed: POST must not return 201 for something
        /problems would flag in the same breath."""
        r = client.post("/notes", json={
            "kind": "task", "title": "S1 ref", "blocked_by": ["Ghost"]})
        assert r.status_code == 422 and r.json()["field"] == "blocked_by"
        assert client.get("/problems").json() == []

    def test_patch_cannot_introduce_a_dangling_reference(self, client):
        r = client.patch("/notes/Pick a type scale", json={"blocked_by": ["Ghost"]})
        assert r.status_code == 422 and r.json()["field"] == "blocked_by"

    def test_what_the_api_writes_it_will_accept_back(self, client, other_vault):
        """Every note the API produces can be recreated from its own output."""
        from planner.domain.note import Note

        for note in client.get("/notes").json():
            detached = {k: v for k, v in note.items()
                        if k not in ("parent", "project", "area", "blocked_by")}
            other_vault.create(Note.from_dict(detached))
        assert other_vault.problems() == []


# =====================================================================================
# S2  PURITY OF READS
# =====================================================================================

class TestS2ReadsArePure:
    @pytest.mark.parametrize("path", [
        "/notes", "/notes/Design system", "/notes/Design system/children",
        "/schema", "/problems", "/health",
    ])
    def test_get_does_not_change_the_vault(self, client, populated, path):
        before = {t: (populated.repo.root / f).read_bytes()
                  for f in ("Items/Design system.md", "Items/Pick a type scale.md")
                  for t in [f]}
        client.get(path)
        after = {t: (populated.repo.root / t).read_bytes() for t in before}
        assert after == before

    @pytest.mark.parametrize("path", ["/notes", "/notes/Design system", "/problems"])
    def test_get_does_not_touch_mtime(self, client, populated, path):
        """mtime is load-bearing: Triage's "stale" view reads it and Iconize repaints
        on it, so a read that bumped it would corrupt both."""
        target = populated.repo.root / "Items" / "Design system.md"
        before = target.stat().st_mtime_ns
        client.get(path)
        assert target.stat().st_mtime_ns == before


# =====================================================================================
# S3  ATOMICITY OF WRITES
# =====================================================================================

class TestS3WritesAreAtomic:
    @pytest.mark.parametrize("payload", [
        {"kind": "task", "title": "Atomic", "status": "in-progress"},
        {"kind": "task", "title": "Atomic", "priority": 99},
        {"kind": "task", "title": "Atomic", "parent": "Ghost"},
        {"kind": "area", "title": "Atomic", "recur": "daily"},
    ])
    def test_a_rejected_create_writes_nothing(self, client, populated, payload):
        before = set(populated.repo.titles())
        assert client.post("/notes", json=payload).status_code == 422
        assert set(populated.repo.titles()) == before

    @pytest.mark.parametrize("changes", [
        {"status": "in-progress"}, {"priority": 99}, {"parent": "Ghost"},
    ])
    def test_a_rejected_patch_leaves_the_file_byte_identical(self, client, populated,
                                                             changes):
        target = populated.repo.root / "Items" / "Pick a type scale.md"
        before = target.read_bytes()
        assert client.patch("/notes/Pick a type scale", json=changes).status_code == 422
        assert target.read_bytes() == before

    def test_a_refused_delete_leaves_the_subtree_intact(self, client, populated):
        before = set(populated.repo.titles())
        assert client.delete("/notes/Design system").status_code == 409
        assert set(populated.repo.titles()) == before


# =====================================================================================
# S4  ONE ERROR SHAPE
# =====================================================================================

class TestS4OneErrorShape:
    @pytest.mark.parametrize("method,path,kwargs,expected", [
        ("get", "/notes/Ghost", {}, 404),
        ("delete", "/notes/Ghost", {}, 404),
        ("post", "/notes/Ghost/close", {}, 404),
        ("post", "/notes", {"json": {"kind": "task", "title": "Studio"}}, 409),
        ("delete", "/notes/Design system", {}, 409),
        ("post", "/notes", {"json": {"kind": "Epic", "title": "X"}}, 422),
        ("post", "/notes", {"json": {"kind": "task", "title": "X", "priority": 9}}, 422),
        ("post", "/notes", {"json": {"kind": "task", "title": "X", "parent": "G"}}, 422),
        ("post", "/notes", {"json": {"title": "no kind"}}, 422),
        ("patch", "/notes/Pick a type scale", {"json": {"kind": "epic"}}, 422),
        ("post", "/notes/Worktop options/close", {}, 422),
    ])
    def test_every_deliberate_4xx_has_the_same_shape(self, client, method, path,
                                                     kwargs, expected):
        """Which validation layer fired -- the DTO enum or the domain -- is an
        implementation detail no client should have to model."""
        r = getattr(client, method)(path, **kwargs)
        assert r.status_code == expected
        assert set(r.json()) == {"detail", "field"}
        assert isinstance(r.json()["detail"], str) and r.json()["detail"]

    def test_the_error_model_is_declared_in_openapi(self, client):
        doc = client.get("/openapi.json").json()
        assert "ErrorOut" in doc["components"]["schemas"]
        assert set(doc["components"]["schemas"]["ErrorOut"]["properties"]) == {
            "detail", "field"}


# =====================================================================================
# S5  STORAGE IS NOT THE CONTRACT
# =====================================================================================

class TestS5StorageIsHidden:
    def test_no_response_leaks_wikilink_syntax(self, client):
        assert "[[" not in client.get("/notes").text

    def test_no_response_leaks_derived_presentation_fields(self, client):
        for note in client.get("/notes").json():
            assert "icon" not in note and "iconColor" not in note

    def test_no_response_leaks_a_folder_or_path(self, client):
        for note in client.get("/notes").json():
            assert "folder" not in note and "path" not in note

    def test_a_client_cannot_dictate_placement_or_appearance(self, client):
        for field, value in [("folder", "Docs"), ("icon", "LiSkull"),
                             ("iconColor", "#000000"), ("path", "/etc/passwd")]:
            r = client.post("/notes", json={"kind": "task", "title": "S5", field: value})
            assert r.status_code == 422, field


# =====================================================================================
# S6  DECLARED IDEMPOTENCE
# =====================================================================================

class TestS6Idempotence:
    def test_patch_is_idempotent(self, client):
        a = client.patch("/notes/Pick a type scale", json={"priority": 3}).json()
        b = client.patch("/notes/Pick a type scale", json={"priority": 3}).json()
        assert a == b

    def test_close_is_idempotent_in_state(self, client):
        a = client.post("/notes/Pick a type scale/close", params={"on": "2026-08-20"}).json()
        b = client.post("/notes/Pick a type scale/close", params={"on": "2026-08-20"}).json()
        assert a == b

    def test_reopen_is_idempotent(self, client):
        client.post("/notes/Pick a type scale/close")
        a = client.post("/notes/Pick a type scale/reopen").json()
        b = client.post("/notes/Pick a type scale/reopen").json()
        assert a == b

    def test_post_is_not_idempotent_and_says_so(self, client):
        first = client.post("/notes", json={"kind": "task", "title": "S6"})
        second = client.post("/notes", json={"kind": "task", "title": "S6"})
        assert first.status_code == 201 and second.status_code == 409

    def test_delete_answers_404_like_every_other_verb_on_a_missing_note(self, client):
        """Deliberately not idempotent: "does this exist?" gets one answer across the
        API rather than one special case."""
        client.delete("/notes/Test at 320px")
        assert client.delete("/notes/Test at 320px").status_code == 404
        assert client.get("/notes/Test at 320px").status_code == 404
        assert client.patch("/notes/Test at 320px", json={}).status_code == 404


# =====================================================================================
# S7  TRANSPORT PARITY
# =====================================================================================

class TestS7TransportParity:
    def test_rest_and_mcp_close_a_ticket_identically(self, client, populated):
        from planner.mcp import call_tool

        rest = client.post("/notes/Pick a type scale/close").json()
        client.post("/notes/Pick a type scale/reopen", params={"status": "doing"})
        mcp = call_tool("close_note", {"title": "Pick a type scale"}, populated)["result"]
        assert {k: rest[k] for k in ("status", "done", "closed")} == \
               {k: mcp[k] for k in ("status", "done", "closed")}

    def test_rest_and_mcp_reject_the_same_input(self, client, populated):
        from planner.mcp import call_tool

        payload = {"kind": "task", "title": "Parity", "status": "in-progress"}
        rest = client.post("/notes", json=payload)
        mcp = call_tool("create_note", payload, populated)
        assert rest.status_code == 422 and mcp["ok"] is False
        assert rest.json()["field"] == mcp["field"] == "status"

    def test_neither_transport_holds_business_logic(self):
        """Both must delegate; a rule implemented in one would drift from the other."""
        import planner.api.routers.notes as rest
        import planner.mcp.server as mcp

        for module in (rest, mcp):
            source = open(module.__file__).read()
            assert "def _apply_defaults" not in source
            assert "_check_parent" not in source


# =====================================================================================
# S9  ROUND-TRIP FIDELITY
# =====================================================================================

class TestS9RoundTrip:
    @pytest.mark.parametrize("payload", [
        {"kind": "task", "title": "RT plain"},
        {"kind": "task", "title": "RT full", "priority": 2, "type": "bug",
         "due": "2026-09-01", "body": "\n# RT full\n\nSome prose.\n"},
        {"kind": "doc", "title": "RT doc", "status": "current"},
        {"kind": "review", "title": "RT review", "week": "2026-W35"},
    ])
    def test_post_response_equals_the_subsequent_get(self, client, payload):
        created = client.post("/notes", json=payload)
        assert created.status_code == 201
        assert client.get(f"/notes/{payload['title']}").json() == created.json()

    def test_patch_response_equals_the_subsequent_get(self, client):
        patched = client.patch("/notes/Pick a type scale", json={"priority": 4}).json()
        assert client.get("/notes/Pick a type scale").json() == patched

    def test_a_body_survives_a_write_read_cycle_byte_for_byte(self, client):
        body = "\n# Odd\n\n- [ ] a checkbox\n\n```base\nviews: []\n```\n\nTrailing.\n"
        client.post("/notes", json={"kind": "doc", "title": "Odd", "body": body})
        assert client.get("/notes/Odd").json()["body"] == body


# =====================================================================================
# The document the app publishes about itself
# =====================================================================================

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
        for path in ("/notes", "/notes/{title}", "/notes/{title}/children",
                     "/notes/{title}/close", "/notes/{title}/reopen",
                     "/schema", "/problems", "/health"):
            assert path in doc["paths"], f"{path} missing from OpenAPI"

    def test_every_operation_is_tagged_and_summarised(self, client):
        for verb, path, op in _all_operations(client):
            assert op.get("tags"), f"{verb.upper()} {path} has no tag"
            assert op.get("summary") or op.get("description"), \
                f"{verb.upper()} {path} is undocumented"

    def test_every_operation_documents_its_invariants(self, client):
        """The docstrings are the specification; an endpoint without them is one whose
        rules live only in its implementation."""
        for verb, path, op in _all_operations(client):
            text = (op.get("description") or "")
            assert "INVARIANT" in text.upper(), \
                f"{verb.upper()} {path} documents no invariants"

    def test_error_responses_are_declared_where_they_can_occur(self, client):
        doc = client.get("/openapi.json").json()
        assert "409" in doc["paths"]["/notes"]["post"]["responses"]
        assert "409" in doc["paths"]["/notes/{title}"]["delete"]["responses"]
        assert "404" in doc["paths"]["/notes/{title}"]["get"]["responses"]

    def test_system_invariants_are_published_in_the_description(self, client):
        """They are the contract; a client author should not have to read the source."""
        description = client.get("/openapi.json").json()["info"]["description"]
        for marker in ("S1", "S4", "S8", "S9", "CLOSURE", "guarantee", "detection"):
            assert marker in description, f"{marker!r} missing from the published description"
