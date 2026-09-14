"""The routing table.

routes.py is the file you read to learn what this API exposes, so what matters is that
it stays honest: everything declared is reachable, everything reachable is declared,
and the metadata it carries matches what the server actually does.
"""

import pytest

from planner.api.routes import ROUTES, build_router


class TestTheTableIsComplete:
    def test_every_declared_route_is_served(self, client):
        """A row here with no working endpoint would be documentation that lies."""
        served = set(client.get("/openapi.json").json()["paths"])
        assert {r.path for r in ROUTES} <= served

    def test_every_served_route_is_declared(self, client):
        """The inverse, and the one that matters: an endpoint registered somewhere
        else would be invisible to anyone reading this file."""
        documented = {r.path for r in ROUTES}
        served = {p for p in client.get("/openapi.json").json()["paths"]}
        assert served - documented == set()

    def test_methods_match(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        for route in ROUTES:
            assert route.method.lower() in paths[route.path], \
                f"{route.method} {route.path} declared but not served"

    def test_no_duplicate_method_and_path(self):
        pairs = [(r.method, r.path) for r in ROUTES]
        assert len(pairs) == len(set(pairs))


class TestMetadata:
    @pytest.mark.parametrize("route", ROUTES, ids=lambda r: f"{r.method} {r.path}")
    def test_every_route_is_summarised_and_tagged(self, route):
        assert route.summary.strip()
        assert route.tags

    @pytest.mark.parametrize("route", ROUTES, ids=lambda r: f"{r.method} {r.path}")
    def test_tags_come_from_the_documented_set(self, route):
        """A stray tag creates a phantom section in Swagger that nothing describes."""
        assert set(route.tags) <= {"notes", "hierarchy", "tickets", "meta"}

    @pytest.mark.parametrize("route", ROUTES, ids=lambda r: f"{r.method} {r.path}")
    def test_the_operation_documents_its_invariants(self, route):
        """The contract becomes the OpenAPI description, so an operation without one
        has rules that live only in its implementation.

        Asserted on `route.docs`, not on the handler docstring. The handler used to
        carry a second copy, and this test passed on it -- which is exactly how a
        duplicate survives: something keeps checking it.
        """
        assert "INVARIANTS" in route.docs.invariants.upper()

    @pytest.mark.parametrize("route", ROUTES, ids=lambda r: f"{r.method} {r.path}")
    def test_the_handler_points_at_the_contract(self, route):
        """A developer who opens the handler should be told where the rules are rather
        than left to discover that the docstring is only half the story."""
        doc = route.handler.__doc__ or ""
        assert "contracts/operations.py" in doc

    def test_writes_declare_their_validation_failure(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        for route in ROUTES:
            if route.method in ("POST", "PATCH"):
                assert "422" in paths[route.path][route.method.lower()]["responses"]

    def test_operations_on_a_named_note_declare_404(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        for route in ROUTES:
            if "{title}" in route.path:
                assert "404" in paths[route.path][route.method.lower()]["responses"], \
                    f"{route.method} {route.path}"

    def test_status_codes_are_what_the_server_returns(self, client):
        assert client.post("/notes", json={"kind": "task", "title": "RT"}).status_code \
            == next(r.status_code for r in ROUTES
                    if r.method == "POST" and r.path == "/notes")
        assert client.delete("/notes/RT").status_code \
            == next(r.status_code for r in ROUTES
                    if r.method == "DELETE" and r.path == "/notes/{title}")


class TestHandlersAreDecoupled:
    def test_handlers_declare_no_routes_of_their_own(self):
        """The point of the split: a handler that carried its own decorator would be
        reachable without appearing in the table."""
        import inspect
        from planner.api.handlers import meta, notes

        for module in (notes, meta):
            source = inspect.getsource(module)
            assert "@router." not in source
            assert "APIRouter(" not in source

    def test_the_router_is_built_from_the_table(self):
        built = build_router()
        assert len(built.routes) == len(ROUTES)

    def test_building_twice_gives_independent_routers(self):
        """create_app() is called per test; a shared mutable router would accumulate."""
        assert len(build_router().routes) == len(build_router().routes) == len(ROUTES)


class TestTheDocsAreNotDuplicated:
    """The invariants were extracted into contracts/operations.py and the handler
    docstrings kept a byte-identical copy for several commits. Nothing read it, and it
    had not drifted yet -- but two copies of twelve paragraphs is a drift waiting for
    the first person who edits the one they happened to open."""

    @pytest.mark.parametrize("route", ROUTES, ids=lambda r: f"{r.method} {r.path}")
    def test_the_handler_does_not_restate_the_invariants(self, route):
        doc = route.handler.__doc__ or ""
        assert "INVARIANTS\n" not in doc, (
            f"{route.method} {route.path}: the invariants belong in "
            "contracts/operations.py, which is what both transports publish")

    @pytest.mark.parametrize("route", ROUTES, ids=lambda r: f"{r.method} {r.path}")
    def test_the_handler_docstring_stays_short(self, route):
        """A pointer, not a second contract. The threshold is arbitrary; exceeding it
        means prose is accumulating somewhere nothing reads."""
        assert len(route.handler.__doc__ or "") < 500

    def test_the_published_text_comes_from_contracts_alone(self):
        """What a reader or a model sees is assembled from one place."""
        from planner.contracts.operations import OPERATIONS

        for route in ROUTES:
            assert route.description == OPERATIONS[(route.method, route.path)].description
