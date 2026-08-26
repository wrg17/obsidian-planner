"""The shared wire contract.

What matters is that it stays derived. The model is generated from the domain's field
table precisely because three hand-written copies had already drifted, so the tests
worth having are the ones that fail when a field is added to the domain and forgotten
here -- not restatements of the field list, which would be a fourth copy.
"""

import datetime

import pytest

from planner.contracts import NoteIn, NotePatch, collapse_nullable, note_properties
from planner.domain import schema as S

#: Properties the API owns; a caller may never set them.
WITHHELD = {"icon", "iconColor", "created", "demo"}


class TestTheModelFollowsTheDomain:
    def test_every_writable_domain_field_is_offered(self):
        """The test that would have caught the original drift."""
        expected = set(S.FIELD_TYPES) - WITHHELD
        assert expected <= set(NoteIn.model_fields)

    def test_nothing_is_offered_that_the_domain_does_not_know(self):
        """`title` and `body` are the note's identity and content rather than
        properties, so they are the only additions."""
        extra = set(NoteIn.model_fields) - set(S.FIELD_TYPES)
        assert extra == {"title", "body"}

    def test_derived_properties_are_withheld(self):
        """icon and iconColor follow from kind; accepting them would invite a client
        to send one that disagrees."""
        assert not (WITHHELD & set(NoteIn.model_fields))

    def test_only_kind_and_title_are_required(self):
        required = {n for n, f in NoteIn.model_fields.items() if f.is_required()}
        assert required == {"kind", "title"}

    @pytest.mark.parametrize("field,expected", [
        ("due", datetime.date), ("scheduled", datetime.date),
        ("closed", datetime.date), ("last_done", datetime.date),
        ("date", datetime.date), ("priority", int), ("done", bool),
    ])
    def test_storage_types_become_wire_types(self, field, expected):
        assert NoteIn.model_fields[field].annotation == expected | None

    def test_links_are_plain_strings_on_the_wire(self):
        """A caller should not need to know [[wikilink]] syntax."""
        for field in ("parent", "project", "area"):
            assert NoteIn.model_fields[field].annotation == str | None

    def test_list_fields_are_lists_of_titles(self):
        for field in ("blocked_by", "supersedes", "attendees"):
            assert NoteIn.model_fields[field].annotation == list[str] | None


class TestPrecision:
    """Where the wire says more than the vault can."""

    @pytest.mark.parametrize("field,enum", [
        ("kind", S.KindEnum), ("status", S.StatusEnum),
        ("type", S.IssueTypeEnum), ("recur", S.RecurEnum),
    ])
    def test_vocabularies_are_enums_not_strings(self, field, enum):
        annotation = NoteIn.model_fields[field].annotation
        assert annotation in (enum, enum | None)

    def test_priority_carries_its_range(self):
        """Obsidian sees a number; only here is 1..4 expressible."""
        constraints = str(NoteIn.model_fields["priority"].metadata)
        assert "1" in constraints and "4" in constraints

    def test_every_field_is_described(self):
        undocumented = [n for n, f in NoteIn.model_fields.items() if not f.description]
        assert not undocumented


class TestPatch:
    def test_nothing_is_required(self):
        assert not [n for n, f in NotePatch.model_fields.items() if f.is_required()]

    def test_it_offers_the_same_fields_as_create(self):
        assert set(NotePatch.model_fields) == set(NoteIn.model_fields)

    def test_unknown_fields_are_refused(self):
        for model in (NoteIn, NotePatch):
            assert model.model_config["extra"] == "forbid"


class TestJsonSchema:
    def test_enums_are_inlined(self):
        """FastAPI serves the whole document so a $ref resolves; a model gets one tool
        at a time, so the values have to be where it will look."""
        import json
        assert "$ref" not in json.dumps(note_properties())

    def test_optional_enums_are_flat(self):
        """`anyOf: [enum, null]` is honest but makes a model look one level deeper.
        Optionality is already carried by `required`."""
        assert note_properties()["type"]["enum"] == list(S.ISSUE_TYPE)
        assert note_properties()["recur"]["enum"] == list(S.RECUR)

    def test_required_fields_keep_their_enum_too(self):
        assert note_properties()["kind"]["enum"] == list(S.KIND_NAMES)

    def test_numeric_bounds_survive(self):
        priority = note_properties()["priority"]
        assert priority["minimum"] == 1 and priority["maximum"] == 4

    def test_omit_drops_fields(self):
        assert "body" not in note_properties(omit={"body"})

    def test_collapse_leaves_a_genuine_union_alone(self):
        """Only a two-branch union with null is noise; anything else is meaningful."""
        genuine = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        assert collapse_nullable(genuine) == genuine

    def test_collapse_is_a_no_op_without_anyof(self):
        plain = {"type": "string"}
        assert collapse_nullable(plain) == plain


class TestBothTransportsSeeTheSameFields:
    """The property the shared layer exists for."""

    def test_openapi_and_mcp_offer_the_same_note_fields(self, client):
        from planner.mcp import TOOLS

        served = set(client.get("/openapi.json").json()
                     ["components"]["schemas"]["NoteIn"]["properties"])
        tooled = set(next(t for t in TOOLS
                          if t["name"] == "create_note")["inputSchema"]["properties"])
        assert served == tooled

    def test_neither_transport_defines_the_model_itself(self):
        import inspect
        from planner.api import schemas
        from planner.mcp import server

        for module in (schemas, server):
            source = inspect.getsource(module)
            assert "create_model(" not in source
