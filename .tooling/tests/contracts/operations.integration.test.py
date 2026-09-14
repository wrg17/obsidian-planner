"""What each operation promises, shared by every transport.

This table exists because the same prose was being written twice: the route handlers
carried the invariants, the MCP tools carried the operational guidance, and each surface
was missing what the other had. The tests worth having are the ones that fail when the
two drift apart again.
"""

import pytest

from planner.api.routes import ROUTES
from planner.contracts.operations import OPERATIONS, Operation
from planner.mcp import COVERS, TOOLS


class TestCoverage:
    def test_every_route_is_documented(self):
        for route in ROUTES:
            assert (route.method, route.path) in OPERATIONS, (
                f"{route.method} {route.path} has no entry"
            )

    def test_nothing_is_documented_that_is_not_served(self):
        """A stale entry describes an endpoint nobody can call."""
        served = {(r.method, r.path) for r in ROUTES}
        assert set(OPERATIONS) <= served

    def test_an_undocumented_route_raises_rather_than_publishing_a_blank(self):
        from planner.api.routes import Route

        stray = Route("GET", "/never-documented", lambda: None, ("meta",))
        with pytest.raises(KeyError, match=r"operations\.py"):
            _ = stray.summary


class TestEachEntry:
    @pytest.mark.parametrize("key", OPERATIONS, ids=lambda k: f"{k[0]} {k[1]}")
    def test_it_has_a_summary_and_guidance(self, key):
        operation = OPERATIONS[key]
        assert operation.summary.strip()
        assert operation.guidance.strip()

    @pytest.mark.parametrize("key", OPERATIONS, ids=lambda k: f"{k[0]} {k[1]}")
    def test_the_summary_is_a_label_not_a_paragraph(self, key):
        assert len(OPERATIONS[key].summary) < 60

    @pytest.mark.parametrize("key", OPERATIONS, ids=lambda k: f"{k[0]} {k[1]}")
    def test_guidance_says_more_than_the_summary(self, key):
        """If they are the same length, one of them is not doing its job."""
        operation = OPERATIONS[key]
        assert len(operation.guidance) > len(operation.summary)

    @pytest.mark.parametrize("key", OPERATIONS, ids=lambda k: f"{k[0]} {k[1]}")
    def test_it_documents_its_invariants(self, key):
        assert "INVARIANT" in OPERATIONS[key].invariants.upper()

    def test_description_puts_guidance_first(self):
        """A reader meets the advice before the contract; the contract is longer and
        less use to someone deciding whether this is the operation they want.
        """
        operation = OPERATIONS[("POST", "/notes")]
        assert operation.description.startswith(operation.guidance.strip())

    def test_description_is_empty_only_if_both_parts_are(self):
        assert Operation(summary="s", guidance="").description == ""


class TestBothTransportsShowTheSameText:
    """The point of the move. A developer new to the repo needs the same thing a model
    needs -- neither knows to read GET /schema before creating a note.
    """

    @pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["name"])
    def test_the_tool_description_is_the_operation_description(self, tool):
        assert tool["description"] == OPERATIONS[COVERS[tool["name"]]].description

    def test_openapi_shows_the_same(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        for key, operation in OPERATIONS.items():
            method, path = key
            served = paths[path][method.lower()]["description"]
            assert served.strip() == operation.description.strip()

    def test_a_model_is_told_about_the_cascade_rule(self):
        """Concretely: delete refuses a parent. A model that has not been told will
        simply try it and get an error it could not have anticipated.
        """
        delete = next(t for t in TOOLS if t["name"] == "delete_note")
        assert "cascade" in delete["description"]

    def test_a_swagger_reader_is_told_to_read_the_schema_first(self, client):
        """The advice that used to exist only in the tool descriptions."""
        create = client.get("/openapi.json").json()["paths"]["/notes"]["post"]
        assert "/schema" in create["description"]


class TestLayering:
    def test_neither_transport_defines_the_prose(self):
        import inspect

        from planner.api import routes
        from planner.mcp import server

        for module in (routes, server):
            assert "INVARIANTS" not in inspect.getsource(module)

    def test_mcp_does_not_reach_into_the_api_for_it(self):
        import inspect

        from planner.mcp import server

        source = inspect.getsource(server)
        assert "api.routes" not in source
        assert "contracts.operations" in source
