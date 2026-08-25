"""CRUD against a real directory tree."""

from datetime import date

import pytest

from planner import NoteExists, NoteNotFound, ValidationError
from planner.schema import KINDS


class TestCreate:
    @pytest.mark.parametrize("kind,folder", [(k.name, k.folder) for k in KINDS.values()])
    def test_folder_is_derived_from_kind(self, vault, kind, folder):
        """Callers never choose the folder. The Templater filing block applies the
        same rule when you create a note by hand; two mechanisms disagreeing about
        where a doc lives is how notes go missing."""
        vault.create(kind=kind, title=f"A {kind}")
        assert (vault.root / folder / f"A {kind}.md").is_file()

    def test_defaults_are_applied(self, vault):
        note = vault.create(kind="task", title="T")
        assert note.fields["status"] == "todo"
        assert note.fields["done"] is False
        assert note.fields["created"] == date.today()

    def test_explicit_status_wins(self, vault):
        assert vault.create(kind="task", title="T", status="doing").fields["status"] == "doing"

    def test_titles_are_unique_vault_wide(self, vault):
        """Items/ is flat and Obsidian links by name, so a doc and a task may not
        share a title even though they live in different folders."""
        vault.create(kind="task", title="Clash")
        with pytest.raises(NoteExists):
            vault.create(kind="doc", title="Clash")

    def test_invalid_note_is_not_written(self, vault):
        with pytest.raises(ValidationError):
            vault.create(kind="task", title="T", status="in-progress")
        assert not vault.exists("T")


class TestParents:
    def test_parent_must_exist(self, vault):
        with pytest.raises(ValidationError, match="does not exist"):
            vault.create(kind="task", title="T", parent="Nope")

    def test_parent_kind_is_enforced(self, populated):
        """A subtask hangs off a task, not off a project. Bases cannot express this,
        so nothing catches it in the app -- the tree just renders wrongly."""
        with pytest.raises(ValidationError, match="may not hang off"):
            populated.create(kind="subtask", title="S", parent="Website relaunch")

    def test_valid_parent_is_accepted(self, populated):
        note = populated.create(kind="subtask", title="S", parent="Pick a type scale")
        assert note.fields["parent"] == "Pick a type scale"

    def test_task_may_hang_off_a_meeting(self, populated):
        """Meeting action items become real tickets; that is the point of the
        Actions block on the meeting template."""
        populated.create(kind="meeting", title="Kickoff")
        populated.create(kind="task", title="Action", parent="Kickoff")


class TestRead:
    def test_get_round_trips_through_disk(self, populated):
        note = populated.get("Pick a type scale")
        assert note.kind == "task"
        assert note.fields["parent"] == "Design system"
        assert note.fields["due"] == date(2026, 8, 24)

    def test_get_missing_raises(self, vault):
        with pytest.raises(NoteNotFound):
            vault.get("Nope")

    def test_list_by_kind(self, populated):
        assert [n.title for n in populated.list(kind="epic")] == ["Design system"]

    def test_list_by_field(self, populated):
        titles = [n.title for n in populated.list(project="Website relaunch")]
        assert "Pick a type scale" in titles and "Studio" not in titles

    def test_list_is_sorted_by_title(self, populated):
        titles = [n.title for n in populated.list()]
        assert titles == sorted(titles)

    def test_malformed_notes_are_skipped_not_raised(self, populated):
        """A vault is hand-editable text; a broken note is an expected state, not an
        exception that should take down a listing."""
        (populated.root / "Items" / "Broken.md").write_text("no frontmatter here")
        assert "Broken" not in [n.title for n in populated.list()]


class TestProblems:
    def test_reports_malformed_and_invalid(self, populated):
        (populated.root / "Items" / "Broken.md").write_text("no frontmatter")
        (populated.root / "Items" / "Typo.md").write_text(
            "---\nkind: task\nstatus: in-progress\n---\n")
        found = dict(populated.problems())
        assert "Broken" in found
        assert "in-progress" in found["Typo"]

    def test_clean_vault_has_none(self, populated):
        assert populated.problems() == []


class TestUpdate:
    def test_changes_a_field(self, populated):
        populated.update("Pick a type scale", status="review")
        assert populated.get("Pick a type scale").fields["status"] == "review"

    def test_null_removes_a_field(self, populated):
        populated.update("Pick a type scale", due=None)
        assert "due" not in populated.get("Pick a type scale").fields

    def test_invalid_update_is_rejected_and_disk_untouched(self, populated):
        with pytest.raises(ValidationError):
            populated.update("Pick a type scale", priority=9)
        assert populated.get("Pick a type scale").fields["priority"] == 1

    def test_update_preserves_the_body(self, vault):
        vault.create(kind="doc", title="D", body="\n# D\n\nOriginal prose.\n")
        vault.update("D", status="current")
        assert "Original prose." in vault.get("D").body


class TestClose:
    def test_sets_all_three_fields(self, populated):
        """Status, the done checkbox and the closed date must move together --
        Triage carries a 'Done but no closed date' view because they often don't."""
        note = populated.close("Pick a type scale")
        assert note.fields["status"] == "done"
        assert note.fields["done"] is True
        assert note.fields["closed"] == date.today()
        assert note.is_open is False

    def test_cancelled_does_not_tick_done(self, populated):
        note = populated.close("Pick a type scale", status="cancelled")
        assert note.fields["done"] is False and note.is_open is False

    def test_explicit_date(self, populated):
        note = populated.close("Pick a type scale", on=date(2026, 8, 20))
        assert note.fields["closed"] == date(2026, 8, 20)

    def test_a_non_closing_status_is_refused(self, populated):
        with pytest.raises(ValidationError, match="does not close"):
            populated.close("Pick a type scale", status="doing")


class TestDelete:
    def test_removes_the_file(self, populated):
        populated.delete("Test at 320px")
        assert not populated.exists("Test at 320px")

    def test_missing_raises(self, vault):
        with pytest.raises(NoteNotFound):
            vault.delete("Nope")
