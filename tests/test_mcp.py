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
        assert out["ok"] and [n["title"] for n in out["result"]] == ["Design system"]

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
