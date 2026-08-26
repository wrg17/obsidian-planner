"""Invariants of the schema, triage and health endpoints.

Identifiers match those documented on the routes in src/planner/api/routers/meta.py.
"""

import pytest

from planner.domain import schema as S


# =====================================================================================
# GET /schema  --  M1..M6
# =====================================================================================

class TestSchemaEndpoint:
    def test_M1_values_are_generated_from_the_enforcing_module(self, client):
        """Not "these happen to agree" but "there is only one of them"."""
        body = client.get("/schema").json()
        assert {k["name"] for k in body["kinds"]} == set(S.KIND_NAMES)
        assert body["vocabularies"]["issue_type"] == list(S.ISSUE_TYPE)
        assert body["vocabularies"]["ticket_status"] == list(S.TICKET_STATUS)

    def test_M1_cannot_promise_what_a_write_would_reject(self, client):
        """Every status the schema advertises for a kind is actually accepted."""
        for kind in client.get("/schema").json()["kinds"]:
            if not kind["statuses"] or kind["name"] not in ("task", "doc"):
                continue
            for status in kind["statuses"]:
                r = client.post("/notes", json={
                    "kind": kind["name"], "title": f"M1 {kind['name']} {status}",
                    "status": status})
                assert r.status_code == 201, (kind["name"], status, r.json())

    def test_M2_every_kind_is_fully_described(self, client):
        for kind in client.get("/schema").json()["kinds"]:
            assert kind["folder"]
            assert kind["fields"]
            assert "kind" in kind["fields"]
            assert isinstance(kind["parent_kinds"], list)

    def test_M3_answers_without_a_vault(self, client, tmp_path, monkeypatch):
        """Usable as a discovery call before anything exists."""
        monkeypatch.setenv("PLANNER_VAULT", str(tmp_path / "does-not-exist"))
        r = client.get("/schema")
        assert r.status_code == 200 and len(r.json()["kinds"]) == 10

    def test_M4_is_stable_across_calls(self, client):
        assert client.get("/schema").json() == client.get("/schema").json()

    def test_M4_is_pure(self, client, populated):
        before = set(populated.repo.titles())
        client.get("/schema")
        assert set(populated.repo.titles()) == before

    def test_M5_every_default_status_is_in_its_own_vocabulary(self, client):
        """Otherwise a newly created note lands in Triage the instant it is made."""
        for kind in client.get("/schema").json()["kinds"]:
            if kind["default_status"] is not None:
                assert kind["default_status"] in kind["statuses"], kind["name"]

    def test_M6_is_sufficient_to_build_a_valid_note_of_any_kind(self, client):
        """What an MCP model does with it: read the rules, then act without guessing."""
        for kind in client.get("/schema").json()["kinds"]:
            payload = {"kind": kind["name"], "title": f"M6 {kind['name']}"}
            if kind["default_status"] is None and kind["statuses"]:
                payload["status"] = kind["statuses"][0]
            r = client.post("/notes", json=payload)
            assert r.status_code == 201, (kind["name"], r.json())
        assert client.get("/problems").json() == []


# =====================================================================================
# GET /problems  --  P1..P7
# =====================================================================================

class TestProblems:
    def test_P1_is_not_defeated_by_the_input_it_reports_on(self, client, populated):
        """An endpoint whose job is finding malformed notes must survive them."""
        items = populated.repo.root / "Items"
        (items / "NoFrontmatter.md").write_text("just prose")
        (items / "ListFrontmatter.md").write_text("---\n- a\n- b\n---\n")
        (items / "NoKind.md").write_text("---\nstatus: todo\n---\n")
        (items / "Empty.md").write_text("")
        (items / "Binary.md").write_bytes(b"\xff\xfe\x00bad")
        r = client.get("/problems")
        assert r.status_code == 200 and len(r.json()) >= 4

    def test_P1_is_pure(self, client, populated):
        (populated.repo.root / "Items" / "Typo.md").write_text(
            "---\nkind: task\nstatus: nonsense\n---\n")
        before = set(populated.repo.titles())
        client.get("/problems")
        assert set(populated.repo.titles()) == before

    def test_P3_empty_on_a_vault_built_only_through_the_api(self, client):
        """The property that makes a non-empty result meaningful."""
        assert client.get("/problems").json() == []

    def test_P3_stays_empty_across_a_full_lifecycle(self, client):
        client.post("/notes", json={"kind": "epic", "title": "P3 epic",
                                    "parent": "Website relaunch",
                                    "project": "Website relaunch"})
        client.post("/notes", json={"kind": "task", "title": "P3 task",
                                    "parent": "P3 epic"})
        client.patch("/notes/P3 task", json={"priority": 1})
        client.post("/notes/P3 task/close")
        client.post("/notes/P3 task/reopen")
        client.delete("/notes/P3 task")
        client.delete("/notes/P3 epic")
        assert client.get("/problems").json() == []

    @pytest.mark.parametrize("frontmatter,expected", [
        ("---\nkind: task\nstatus: in-progress\n---\n", "status"),
        ("---\nkind: task\ntype: cleanup\n---\n", "type"),
        ("---\nkind: routine\nrecur: fortnightly\n---\n", "recur"),
        ("---\nkind: task\npriority: 9\n---\n", "priority"),
    ])
    def test_P4_catches_bad_values(self, client, populated, frontmatter, expected):
        (populated.repo.root / "Items" / "Bad.md").write_text(frontmatter)
        found = [p for p in client.get("/problems").json() if p["title"] == "Bad"]
        assert found and expected in found[0]["message"]

    @pytest.mark.parametrize("field,frontmatter", [
        ("parent", '---\nkind: task\nparent: "[[Ghost]]"\n---\n'),
        ("project", '---\nkind: task\nproject: "[[Ghost]]"\n---\n'),
        ("blocked_by", '---\nkind: task\nblocked_by:\n  - "[[Ghost]]"\n---\n'),
    ])
    def test_P4_catches_structural_links_that_do_not_resolve(self, client, populated,
                                                             field, frontmatter):
        """Bases cannot follow a link to check it resolves, so a parent pointing at a
        deleted note looks exactly like one that works. This is the only place it
        surfaces."""
        (populated.repo.root / "Items" / "Dangling.md").write_text(frontmatter)
        found = [p for p in client.get("/problems").json() if p["title"] == "Dangling"]
        assert found and field in found[0]["message"] and "Ghost" in found[0]["message"]

    def test_P5_reports_without_repairing(self, client, populated):
        """Silently rewriting someone's notes is worse than the fault being reported,
        and Obsidian is editing the same files."""
        path = populated.repo.root / "Items" / "Typo.md"
        original = "---\nkind: task\nstatus: in-progress\n---\n"
        path.write_text(original)
        client.get("/problems")
        client.get("/problems")
        assert path.read_text() == original

    def test_P6_link_checking_ignores_case(self, client, populated):
        """Matching how notes are found (G2) and created (C4)."""
        (populated.repo.root / "Items" / "Caselink.md").write_text(
            '---\nkind: task\nparent: "[[design SYSTEM]]"\n---\n')
        titles = [p["title"] for p in client.get("/problems").json()]
        assert "Caselink" not in titles

    def test_P7_order_is_deterministic(self, client, populated):
        items = populated.repo.root / "Items"
        (items / "Zed.md").write_text("---\nkind: task\nstatus: bad\n---\n")
        (items / "Alpha.md").write_text("---\nkind: task\nstatus: bad\n---\n")
        first = client.get("/problems").json()
        assert first == client.get("/problems").json()
        assert [p["title"] for p in first] == sorted(p["title"] for p in first)


# =====================================================================================
# GET /health  --  N1..N4
# =====================================================================================

class TestHealth:
    def test_N1_is_200_when_the_vault_is_present(self, client):
        r = client.get("/health")
        assert r.status_code == 200 and r.json()["status"] == "ok"

    def test_N1_is_still_200_when_the_vault_is_missing(self, client, tmp_path,
                                                       monkeypatch):
        """"Up but misconfigured" and "down" are different conditions; a load balancer
        has to be able to tell them apart."""
        monkeypatch.setenv("PLANNER_VAULT", str(tmp_path / "gone"))
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "vault-missing"

    def test_N2_does_not_read_notes(self, client, populated):
        """Cheap enough to poll on a large vault: it stats a directory, nothing more."""
        (populated.repo.root / "Items" / "Unparseable.md").write_text("garbage")
        assert client.get("/health").json()["status"] == "ok"

    def test_N3_does_not_create_the_missing_vault(self, client, tmp_path, monkeypatch):
        absent = tmp_path / "never-created"
        monkeypatch.setenv("PLANNER_VAULT", str(absent))
        client.get("/health")
        assert not absent.exists()

    def test_N4_discloses_the_resolved_path(self, client, populated):
        """The commonest deployment mistake is PLANNER_VAULT pointing somewhere
        unexpected; hiding the answer makes that harder to find."""
        assert client.get("/health").json()["vault"] == str(populated.repo.root)
