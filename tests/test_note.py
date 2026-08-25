"""The note as plain data: markdown <-> object <-> JSON."""

from datetime import date

import pytest

from planner import Note, ValidationError
from planner.note import unwrap_link, wrap_link


class TestLinks:
    """The API speaks titles; the vault speaks [[wikilinks]]."""

    @pytest.mark.parametrize("raw,expected", [
        ("[[Design system]]", "Design system"),
        ("[[Design system|the system]]", "Design system"),
        ("  [[Spaced]]  ", "Spaced"),
        ("Design system", "Design system"),
        ("", ""),
    ])
    def test_unwrap(self, raw, expected):
        assert unwrap_link(raw) == expected

    def test_wrap_is_idempotent(self):
        assert wrap_link("A") == "[[A]]"
        assert wrap_link("[[A]]") == "[[A]]"

    def test_round_trip_through_markdown(self):
        note = Note(kind="task", title="T", fields={"parent": "Design system"})
        assert 'parent: "[[Design system]]"' in note.to_markdown()
        back = Note.from_markdown(note.to_markdown(), "T")
        assert back.fields["parent"] == "Design system"


class TestCoercion:
    def test_dates_become_date_objects(self):
        note = Note(kind="task", title="T", fields={"due": "2026-08-24"})
        assert note.fields["due"] == date(2026, 8, 24)

    def test_priority_becomes_int(self):
        assert Note(kind="task", title="T", fields={"priority": "2"}).fields["priority"] == 2

    def test_bad_date_is_rejected(self):
        with pytest.raises(ValidationError, match="not a YYYY-MM-DD date"):
            Note(kind="task", title="T", fields={"due": "24/08/2026"})

    def test_empty_values_are_dropped(self):
        """Templates ship keys with no value (`due:`), which must not become empty
        strings that then fail date coercion."""
        note = Note(kind="task", title="T", fields={"due": None, "scheduled": ""})
        assert "due" not in note.fields and "scheduled" not in note.fields

    def test_scalar_becomes_list_for_list_fields(self):
        note = Note(kind="task", title="T", fields={"blocked_by": "[[A]]"})
        assert note.fields["blocked_by"] == ["A"]


class TestValidation:
    def test_unknown_kind(self):
        with pytest.raises(ValidationError, match="unknown kind"):
            Note(kind="epicc", title="T")

    def test_title_may_not_contain_a_slash(self):
        with pytest.raises(ValidationError):
            Note(kind="task", title="a/b")

    @pytest.mark.parametrize("field,value", [
        ("status", "in-progress"),      # the classic typo: not in the vocabulary
        ("type", "cleanup"),
        ("recur", "fortnightly"),
        ("priority", 9),
    ])
    def test_vocabulary_violations(self, field, value):
        with pytest.raises(ValidationError):
            Note(kind="task", title="T", fields={field: value}).validate()

    def test_field_not_on_this_kind(self):
        """An area has no `recur`; catching that is the whole point of typed kinds."""
        with pytest.raises(ValidationError, match="not a field of kind"):
            Note(kind="area", title="A", fields={"recur": "daily"}).validate()

    def test_kind_without_status_rejects_one(self):
        """A meeting has no status vocabulary. Strictly, `status` is not one of its
        fields at all, so the field check fires first; in lenient mode -- which is how
        an existing vault is read -- the status check catches it instead. Both paths
        must reject it, which is why both are asserted."""
        with pytest.raises(ValidationError, match="not a field of kind"):
            Note(kind="meeting", title="M", fields={"status": "todo"}).validate()
        with pytest.raises(ValidationError, match="has no status"):
            Note(kind="meeting", title="M",
                 fields={"status": "todo"}).validate(strict_fields=False)

    def test_lenient_mode_tolerates_extra_fields(self):
        Note(kind="task", title="T", fields={"whatever": 1}).validate(strict_fields=False)


class TestOpenness:
    """`done` and `status` are additive -- ticking either closes the ticket. This
    mirrors the `open` formula in the bases, and the two must not disagree."""

    @pytest.mark.parametrize("fields,expected", [
        ({"status": "doing"}, True),
        ({"status": "done"}, False),
        ({"status": "cancelled"}, False),
        ({"done": True}, False),
        ({"done": True, "status": "doing"}, False),
        ({"done": False, "status": "todo"}, True),
    ])
    def test_is_open(self, fields, expected):
        assert Note(kind="task", title="T", fields=fields).is_open is expected


class TestMarkdown:
    def test_frontmatter_must_start_at_byte_zero(self):
        """Obsidian only recognises frontmatter at the start of the file. A Templater
        block above the `---` once made ten templates propertyless and invisible."""
        text = "<%* await tp.file.move('x') -%>\n---\nkind: task\n---\n"
        with pytest.raises(ValidationError, match="no frontmatter"):
            Note.from_markdown(text, "T")

    def test_icon_and_colour_come_from_the_kind(self):
        md = Note(kind="epic", title="E").to_markdown()
        assert 'icon: "LiLayers2"' in md and 'iconColor: "#14B8A6"' in md

    def test_hex_colour_is_quoted(self):
        """Unquoted `#14B8A6` is a YAML comment, which silently empties the value."""
        assert 'iconColor: "#' in Note(kind="task", title="T").to_markdown()

    def test_empty_list_renders_as_flow(self):
        md = Note(kind="task", title="T", fields={"blocked_by": []}).to_markdown()
        assert "blocked_by: []" in md

    def test_body_is_preserved(self):
        note = Note(kind="doc", title="D", body="\n# D\n\nText.\n")
        assert Note.from_markdown(note.to_markdown(), "D").body.strip().endswith("Text.")

    def test_full_round_trip_is_stable(self):
        original = Note(kind="task", title="T", fields={
            "status": "blocked", "type": "chore", "priority": 3,
            "due": date(2026, 8, 24), "blocked_by": ["A", "B"], "done": False,
        }, body="\n# T\n")
        once = original.to_markdown()
        twice = Note.from_markdown(once, "T").to_markdown()
        assert once == twice


class TestJson:
    def test_dates_serialise_as_iso_strings(self):
        note = Note(kind="task", title="T", fields={"due": date(2026, 8, 24)})
        assert note.to_dict()["due"] == "2026-08-24"

    def test_links_serialise_as_bare_titles(self):
        note = Note(kind="task", title="T", fields={"parent": "[[E]]"})
        assert note.to_dict()["parent"] == "E"

    def test_presentation_fields_are_omitted(self):
        """icon/iconColor are derived from kind; echoing them back invites a client
        to send one that disagrees."""
        out = Note(kind="task", title="T").to_dict()
        assert "icon" not in out and "iconColor" not in out

    def test_dict_round_trip(self):
        note = Note(kind="task", title="T", fields={"priority": 1, "parent": "E"})
        assert Note.from_dict(note.to_dict()).to_dict() == note.to_dict()

    def test_from_dict_requires_kind_and_title(self):
        with pytest.raises(ValidationError):
            Note.from_dict({"title": "T"})
        with pytest.raises(ValidationError):
            Note.from_dict({"kind": "task"})
