"""Correlation ids, timing headers, and the single error shape."""

import pytest


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


class TestErrorNormalisation:
    def test_a_failure_with_no_input_value_still_reports(self, client):
        """Pydantic omits `input` for a missing required field, so the detail must
        not depend on it being there."""
        r = client.post("/notes", json={"title": "no kind given"})
        assert r.status_code == 422
        body = r.json()
        assert set(body) == {"detail", "field"}
        assert body["field"] == "kind"
        assert body["detail"]

    def test_a_failure_with_an_input_value_quotes_it(self, client):
        r = client.post("/notes", json={"kind": "Epic", "title": "X"})
        assert "Epic" in r.json()["detail"]

    def test_domain_and_dto_errors_are_indistinguishable_in_shape(self, client):
        dto = client.post("/notes", json={"kind": "task", "title": "A",
                                          "priority": 99}).json()
        domain = client.post("/notes", json={"kind": "subtask", "title": "B",
                                             "parent": "Nope"}).json()
        assert set(dto) == set(domain) == {"detail", "field"}
