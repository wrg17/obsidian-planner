"""MCP tools. Dispatch is transport-agnostic, so these need no MCP client."""

import pytest

from planner.mcp import TOOLS, call_tool


class TestToolSchemas:
    def test_every_tool_is_described(self):
        for tool in TOOLS:
            assert tool["description"].strip(), f"{tool['name']} has no description"
            assert tool["inputSchema"]["type"] == "object"

    def test_kind_is_an_enum_not_a_bare_string(self):
        """The whole point. A model given `"type": "string"` will send "Epic"; given
        an enum it sends "epic". The schema is the specification it reads."""
        create = next(t for t in TOOLS if t["name"] == "create_note")
        kind = create["inputSchema"]["properties"]["kind"]
        assert kind["enum"] == ["area", "project", "epic", "task", "subtask",
                                "routine", "doc", "decision", "meeting", "review"]

    @pytest.mark.parametrize("tool,field,expected", [
        ("create_note", "type", ["feature", "bug", "chore", "spike", "research"]),
        ("create_note", "recur", ["daily", "weekdays", "weekly", "monthly"]),
        ("close_note", "status", ["done", "cancelled"]),
    ])
    def test_vocabularies_are_enums(self, tool, field, expected):
        spec = next(t for t in TOOLS if t["name"] == tool)
        assert spec["inputSchema"]["properties"][field]["enum"] == expected

    def test_create_note_offers_every_writable_field(self):
        """It once offered sixteen of twenty -- no attendees, closed, done or
        supersedes -- because the list was maintained by hand in three places."""
        from planner.contracts import NoteIn
        spec = next(t for t in TOOLS if t["name"] == "create_note")
        assert set(spec["inputSchema"]["properties"]) == set(NoteIn.model_fields)

    def test_enums_are_generated_not_duplicated(self):
        """If someone adds a kind to the domain, the tool schema must follow without
        anyone remembering to edit it."""
        from planner.domain import KIND_NAMES
        create = next(t for t in TOOLS if t["name"] == "create_note")
        assert create["inputSchema"]["properties"]["kind"]["enum"] == list(KIND_NAMES)

    def test_required_fields_are_declared(self):
        create = next(t for t in TOOLS if t["name"] == "create_note")
        assert set(create["inputSchema"]["required"]) == {"kind", "title"}


class TestDispatch:
    def test_list(self, populated):
        out = call_tool("list_notes", {"kind": "epic"}, populated)
        assert out["ok"]
        assert {n["title"] for n in out["result"]} == {"Design system", "Content migration"}

    def test_get(self, populated):
        out = call_tool("get_note", {"title": "Design system"}, populated)
        assert out["result"]["kind"] == "epic"

    def test_create(self, populated):
        out = call_tool("create_note", {"kind": "task", "title": "From MCP"}, populated)
        assert out["ok"] and out["result"]["status"] == "todo"
        assert populated.exists("From MCP")

    def test_update(self, populated):
        out = call_tool("update_note",
                        {"title": "Pick a type scale", "changes": {"status": "review"}},
                        populated)
        assert out["result"]["status"] == "review"

    def test_close_matches_the_rest_behaviour(self, populated):
        """Both front ends call the same service, so all three fields move here too."""
        out = call_tool("close_note", {"title": "Pick a type scale"}, populated)
        assert out["result"]["status"] == "done"
        assert out["result"]["done"] is True
        assert "closed" in out["result"]

    def test_delete(self, populated):
        assert call_tool("delete_note", {"title": "Test at 320px"}, populated)["ok"]
        assert not populated.exists("Test at 320px")

    def test_describe_schema(self, populated):
        out = call_tool("describe_schema", {}, populated)
        assert len(out["result"]["kinds"]) == 10

    def test_find_problems(self, populated):
        (populated.repo.root / "Items" / "Typo.md").write_text(
            "---\nkind: task\nstatus: in-progress\n---\n")
        out = call_tool("find_problems", {}, populated)
        assert any(p["title"] == "Typo" for p in out["result"])


class TestErrorsAreReadable:
    """A model has to read the failure and correct itself, so errors come back as
    payloads rather than exceptions."""

    def test_bad_vocabulary_names_the_field(self, populated):
        out = call_tool("create_note",
                        {"kind": "task", "title": "X", "status": "in-progress"}, populated)
        assert out["ok"] is False
        assert out["field"] == "status"
        assert "in-progress" in out["error"]

    def test_missing_note_is_not_an_exception(self, populated):
        out = call_tool("get_note", {"title": "Nope"}, populated)
        assert out["ok"] is False and "Nope" in out["error"]

    def test_duplicate_title(self, populated):
        out = call_tool("create_note", {"kind": "doc", "title": "Studio"}, populated)
        assert out["ok"] is False and "already exists" in out["error"]

    def test_unknown_tool(self, populated):
        assert call_tool("nonsense", {}, populated)["ok"] is False

    def test_wrong_parent_kind(self, populated):
        out = call_tool("create_note",
                        {"kind": "subtask", "title": "S", "parent": "Website relaunch"},
                        populated)
        assert out["ok"] is False and out["field"] == "parent"


class TestEveryRouteIsAccountedFor:
    """The MCP tool list and the routing table were maintained separately and drifted:
    eight tools against twelve routes, with nothing recording which gaps were decided.
    `reopen_note` was missing beside `close_note`, which nobody chose.

    The prose is deliberately not shared -- a model needs to know when to reach for a
    tool, a developer needs to know what an endpoint does, and generating either from
    the other would make both worse. It is the inventory that has to agree.
    """

    def test_no_route_is_silently_absent(self):
        from planner.api.routes import ROUTES
        from planner.mcp import COVERS, NOT_EXPOSED

        accounted = set(COVERS.values()) | set(NOT_EXPOSED)
        missing = [(r.method, r.path) for r in ROUTES
                   if (r.method, r.path) not in accounted]
        assert not missing, (
            f"{missing} is neither exposed as a tool nor listed in NOT_EXPOSED. "
            "Add a tool, or say why not.")

    def test_every_mapping_points_at_a_real_route(self):
        from planner.api.routes import ROUTES
        from planner.mcp import COVERS, NOT_EXPOSED

        real = {(r.method, r.path) for r in ROUTES}
        for name, key in COVERS.items():
            assert key in real, f"{name} maps to {key}, which is not a route"
        for key in NOT_EXPOSED:
            assert key in real, f"{key} is excluded but is not a route"

    def test_covers_and_tools_agree(self):
        from planner.mcp import COVERS, TOOLS
        assert {t["name"] for t in TOOLS} == set(COVERS)

    def test_an_omission_carries_a_reason(self):
        """A blank entry would be a way to silence the test without deciding."""
        from planner.mcp import NOT_EXPOSED
        for key, reason in NOT_EXPOSED.items():
            assert len(reason) > 40, f"{key} has no real justification"

    def test_nothing_is_both_exposed_and_excluded(self):
        from planner.mcp import COVERS, NOT_EXPOSED
        assert not (set(COVERS.values()) & set(NOT_EXPOSED))


class TestTheToolsThatWereMissing:
    def test_reopen_is_reachable(self, populated):
        call_tool("close_note", {"title": "Pick a type scale"}, populated)
        out = call_tool("reopen_note", {"title": "Pick a type scale", "status": "doing"},
                        populated)
        assert out["ok"]
        assert out["result"]["status"] == "doing"
        assert out["result"]["done"] is False
        assert "closed" not in out["result"]

    def test_reopen_enforces_the_same_rules_as_rest(self, populated):
        """Both go through NoteService, so a doc cannot be reopened either way."""
        out = call_tool("reopen_note", {"title": "Worktop options"}, populated)
        assert out["ok"] is False and out["field"] == "kind"

    def test_children_one_level(self, populated):
        out = call_tool("get_children", {"title": "Design system"}, populated)
        assert {n["title"] for n in out["result"]} == {"Pick a type scale",
                                                       "Audit existing components"}

    def test_children_recursive(self, populated):
        out = call_tool("get_children", {"title": "Website relaunch",
                                         "recursive": True}, populated)
        assert "Test at 320px" in {n["title"] for n in out["result"]}

    def test_children_of_a_missing_note_is_an_error_not_an_empty_list(self, populated):
        out = call_tool("get_children", {"title": "Nope"}, populated)
        assert out["ok"] is False
