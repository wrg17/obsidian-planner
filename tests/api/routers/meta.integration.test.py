"""Schema, triage and health endpoints."""

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


class TestProblems:
    def test_clean_vault_is_empty(self, client):
        assert client.get("/problems").json() == []

    def test_reports_a_hand_edited_typo(self, client, populated):
        (populated.repo.root / "Items" / "Typo.md").write_text(
            "---\nkind: task\nstatus: in-progress\n---\n")
        found = client.get("/problems").json()
        assert any(p["title"] == "Typo" for p in found)


class TestHealth:
    def test_reports_the_vault(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok" and body["vault"]
