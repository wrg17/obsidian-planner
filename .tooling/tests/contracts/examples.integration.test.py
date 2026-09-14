"""The values Swagger pre-fills.

A parameter with no example is a form a reader has to fill in before they can learn
anything -- and filling it in means knowing a note title nobody has told them. So the
examples name real demo notes, and these tests keep them naming real demo notes: one
that quietly stopped resolving would be worse than none, because the reader would blame
themselves for the 404.
"""

import importlib.util
import pathlib
import sys

import pytest

from planner.contracts.note import CREATE_EXAMPLE, NoteIn
from planner.contracts.operations import DEMO


def _demo_module():
    """Load demo/demo.py, which is a script beside the package rather than in it."""
    path = pathlib.Path(__file__).resolve().parents[2] / "demo" / "demo.py"
    spec = importlib.util.spec_from_file_location("_demo", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_demo"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def demo_titles():
    module = _demo_module()
    return {title for _folder, title, _fields, _body in module.NOTES}


@pytest.fixture(scope="module")
def demo_notes():
    module = _demo_module()
    return {title: fields for _folder, title, fields, _body in module.NOTES}


class TestTheExamplesResolve:
    @pytest.mark.parametrize(
        "name,value", [(n, v) for n, v in DEMO.items() if n != "new_title"]
    )
    def test_every_named_example_is_a_note_the_demo_creates(
        self, name, value, demo_titles
    ):
        assert value in demo_titles, f"DEMO[{name!r}] = {value!r} is not generated"

    def test_the_create_example_uses_a_title_that_does_not_exist(self, demo_titles):
        """It would 409 on the first click otherwise, which teaches the wrong lesson
        about the endpoint.
        """
        assert DEMO["new_title"] not in demo_titles

    def test_the_parent_example_actually_has_children(self, demo_notes):
        """GET /notes/{title}/children returning [] would look broken."""
        children = [
            t
            for t, f in demo_notes.items()
            if f.get("parent") == f"[[{DEMO['parent']}]]"
        ]
        assert children, f"{DEMO['parent']!r} has no children in the demo data"

    def test_the_task_example_is_a_ticket(self):
        """Close and reopen use it, and only tickets track completion."""
        from planner.domain import schema as S

        assert "task" in S.TICKET_KINDS

    def test_the_task_example_has_children(self, demo_notes):
        """GET /notes/{title}/children and the subtask relationship both want one
        that does.
        """
        children = [
            t for t, f in demo_notes.items() if f.get("parent") == f"[[{DEMO['task']}]]"
        ]
        assert children

    def test_the_delete_example_is_a_leaf(self, demo_notes):
        """A note with children is refused, so using one would show a reader the guard
        rail rather than the endpoint. Hence a second example for delete.
        """
        children = [
            t for t, f in demo_notes.items() if f.get("parent") == f"[[{DEMO['leaf']}]]"
        ]
        assert not children

    def test_the_delete_example_is_not_the_one_other_endpoints_use(self):
        """Sharing it would mean a reader who tried DELETE first found every other
        example broken.
        """
        assert DEMO["leaf"] != DEMO["task"]


class TestTheCreateExampleIsValid:
    def test_it_passes_the_request_model(self):
        NoteIn(**CREATE_EXAMPLE)

    def test_it_names_a_parent_that_exists(self, demo_titles):
        assert CREATE_EXAMPLE["parent"] in demo_titles

    def test_the_parent_may_hold_a_task(self, demo_notes):
        from planner.domain import schema as S

        parent_kind = demo_notes[CREATE_EXAMPLE["parent"]]["kind"]
        assert parent_kind in S.KINDS["task"].parent_kinds

    def test_every_field_it_sets_is_legal_for_the_kind(self):
        from planner.domain import schema as S

        allowed = set(S.allowed_fields(CREATE_EXAMPLE["kind"]))
        assert set(CREATE_EXAMPLE) - {"title"} <= allowed


class TestTheyReachSwagger:
    def test_the_create_body_is_pre_filled(self, client):
        schema = client.get("/openapi.json").json()["components"]["schemas"]["NoteIn"]
        assert schema["examples"][0]["title"] == DEMO["new_title"]

    @pytest.mark.parametrize(
        "path,method",
        [
            ("/notes/{title}", "get"),
            ("/notes/{title}", "patch"),
            ("/notes/{title}", "delete"),
            ("/notes/{title}/children", "get"),
            ("/notes/{title}/close", "post"),
            ("/notes/{title}/reopen", "post"),
        ],
    )
    def test_every_title_parameter_is_pre_filled(self, client, path, method):
        operation = client.get("/openapi.json").json()["paths"][path][method]
        title = next(p for p in operation["parameters"] if p["name"] == "title")
        rendered = title.get("examples") or title["schema"].get("examples")
        assert rendered, f"{method.upper()} {path} leaves `title` blank"

    def test_the_listing_filters_are_pre_filled(self, client):
        operation = client.get("/openapi.json").json()["paths"]["/notes"]["get"]
        filled = {
            p["name"]
            for p in operation["parameters"]
            if p.get("examples") or p["schema"].get("examples")
        }
        assert {"project", "parent"} <= filled


class TestAgainstTheRunningApi:
    """The examples are only useful if clicking Execute actually returns something."""

    def test_the_get_example_resolves(self, client, populated):
        """Uses the test fixture, which shares the demo's names for these notes."""
        assert client.get(f"/notes/{DEMO['task']}").status_code == 200

    def test_the_children_example_returns_children(self, client):
        body = client.get(f"/notes/{DEMO['parent']}/children").json()
        assert body

    def test_the_project_filter_matches_something(self, client):
        assert client.get("/notes", params={"project": DEMO["project"]}).json()

    def test_the_create_example_succeeds(self, client):
        assert client.post("/notes", json=CREATE_EXAMPLE).status_code == 201

    def test_the_delete_example_is_not_refused(self, client, populated):
        """The point of choosing a leaf: Execute deletes, rather than 409ing."""
        populated.create(kind="task", title=DEMO["leaf"], project=DEMO["project"])
        assert client.delete(f"/notes/{DEMO['leaf']}").status_code == 204
