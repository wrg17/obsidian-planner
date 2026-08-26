"""Note CRUD, closing, and hierarchy over HTTP."""

import pytest


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
