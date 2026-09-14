"""CRUD against a real directory tree."""

from datetime import date

import pytest

from planner import NoteExistsError, NoteNotFoundError, ValidationError
from planner.domain.schema import KINDS


class TestCreate:
    @pytest.mark.parametrize(
        "kind,folder", [(k.name, k.folder) for k in KINDS.values()]
    )
    def test_folder_is_derived_from_kind(self, vault, kind, folder):
        """Callers never choose the folder. The Templater filing block applies the
        same rule when you create a note by hand; two mechanisms disagreeing about
        where a doc lives is how notes go missing.
        """
        vault.create(kind=kind, title=f"A {kind}")
        assert (vault.repo.root / folder / f"A {kind}.md").is_file()

    def test_defaults_are_applied(self, vault):
        note = vault.create(kind="task", title="T")
        assert note.fields["status"] == "todo"
        assert note.fields["done"] is False
        assert note.fields["created"] == date.today()

    def test_explicit_status_wins(self, vault):
        assert (
            vault.create(kind="task", title="T", status="doing").fields["status"]
            == "doing"
        )

    def test_titles_are_unique_vault_wide(self, vault):
        """Items/ is flat and Obsidian links by name, so a doc and a task may not
        share a title even though they live in different folders.
        """
        vault.create(kind="task", title="Clash")
        with pytest.raises(NoteExistsError):
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
        so nothing catches it in the app -- the tree just renders wrongly.
        """
        with pytest.raises(ValidationError, match="may not hang off"):
            populated.create(kind="subtask", title="S", parent="Website relaunch")

    def test_valid_parent_is_accepted(self, populated):
        note = populated.create(kind="subtask", title="S", parent="Pick a type scale")
        assert note.fields["parent"] == "Pick a type scale"

    def test_task_may_hang_off_a_meeting(self, populated):
        """Meeting action items become real tickets; that is the point of the
        Actions block on the meeting template.
        """
        populated.create(kind="meeting", title="Kickoff")
        populated.create(kind="task", title="Action", parent="Kickoff")


class TestRead:
    def test_get_round_trips_through_disk(self, populated):
        note = populated.get("Pick a type scale")
        assert note.kind == "task"
        assert note.fields["parent"] == "Design system"
        assert note.fields["due"] == date(2026, 8, 24)

    def test_get_missing_raises(self, vault):
        with pytest.raises(NoteNotFoundError):
            vault.get("Nope")

    def test_list_by_kind(self, populated):
        titles = {n.title for n in populated.find(kind="epic")}
        assert titles == {"Design system", "Content migration"}
        assert all(n.kind == "epic" for n in populated.find(kind="epic"))

    def test_list_by_field(self, populated):
        titles = [n.title for n in populated.find(project="Website relaunch")]
        assert "Pick a type scale" in titles and "Studio" not in titles

    def test_list_is_sorted_by_title(self, populated):
        titles = [n.title for n in populated.find()]
        assert titles == sorted(titles)

    def test_malformed_notes_are_skipped_not_raised(self, populated):
        """A vault is hand-editable text; a broken note is an expected state, not an
        exception that should take down a listing.
        """
        (populated.repo.root / "Items" / "Broken.md").write_text("no frontmatter here")
        assert "Broken" not in [n.title for n in populated.find()]


class TestProblems:
    def test_reports_malformed_and_invalid(self, populated):
        (populated.repo.root / "Items" / "Broken.md").write_text("no frontmatter")
        (populated.repo.root / "Items" / "Typo.md").write_text(
            "---\nkind: task\nstatus: in-progress\n---\n"
        )
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
        Triage carries a 'Done but no closed date' view because they often don't.
        """
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
        with pytest.raises(NoteNotFoundError):
            vault.delete("Nope")


class TestTitleUniquenessIsCaseInsensitive:
    """macOS is case-insensitive by default, Linux is not. An exact-match check would
    create two notes on one machine and silently overwrite on the other.
    """

    def test_same_title_different_case_is_refused(self, vault):
        vault.create(kind="task", title="Design System")
        with pytest.raises(NoteExistsError, match="differ only by case"):
            vault.create(kind="task", title="design system")

    def test_the_message_names_the_existing_title(self, vault):
        vault.create(kind="task", title="Design System")
        with pytest.raises(NoteExistsError, match="Design System"):
            vault.create(kind="doc", title="DESIGN SYSTEM")

    def test_exact_duplicate_message_omits_the_case_note(self, vault):
        vault.create(kind="task", title="Exact")
        with pytest.raises(NoteExistsError) as caught:
            vault.create(kind="task", title="Exact")
        assert "differ only by case" not in str(caught.value)

    def test_genuinely_different_titles_are_fine(self, vault):
        vault.create(kind="task", title="Alpha")
        vault.create(kind="task", title="Alpha two")


class TestServiceGuards:
    def test_unknown_kind_in_a_filter(self, vault):
        with pytest.raises(ValidationError, match="unknown kind"):
            vault.find(kind="epicc")

    def test_a_note_cannot_be_its_own_parent(self, populated):
        with pytest.raises(ValidationError, match="own parent"):
            populated.update("Pick a type scale", parent="Pick a type scale")

    def test_kind_cannot_be_changed(self, populated):
        """A kind change would move the folder and invalidate the field set; delete
        and recreate is the honest operation.
        """
        with pytest.raises(ValidationError, match="cannot be changed"):
            populated.update("Pick a type scale", kind="epic")

    def test_updating_with_the_same_kind_is_a_no_op(self, populated):
        populated.update("Pick a type scale", kind="task", priority=2)
        assert populated.get("Pick a type scale").fields["priority"] == 2


class TestReopen:
    def test_clears_closed_and_done(self, populated):
        populated.close("Pick a type scale")
        note = populated.reopen("Pick a type scale", status="doing")
        assert note.fields["status"] == "doing"
        assert note.fields["done"] is False
        assert "closed" not in note.fields
        assert note.is_open

    def test_rejects_a_status_outside_the_kind_vocabulary(self, populated):
        with pytest.raises(ValidationError, match="not one of"):
            populated.reopen("Pick a type scale", status="active")


class TestDescendants:
    def test_walks_the_whole_subtree(self, populated):
        found = {n.title for n in populated.descendants_of("Website relaunch")}
        assert {"Design system", "Pick a type scale", "Test at 320px"} <= found
        assert "Website relaunch" not in found
        assert "Studio" not in found  # upward, not downward

    def test_direct_children_are_one_level_only(self, populated):
        found = {n.title for n in populated.children_of("Website relaunch")}
        assert found == {"Design system", "Content migration"}
        assert "Pick a type scale" not in found  # a grandchild

    def test_a_hand_edited_cycle_does_not_hang(self, populated):
        """Nothing in Obsidian prevents two notes pointing at each other; a naive
        walk would spin forever.
        """
        a = populated.repo.root / "Items" / "Loop A.md"
        b = populated.repo.root / "Items" / "Loop B.md"
        a.write_text('---\nkind: task\nparent: "[[Loop B]]"\n---\n')
        b.write_text('---\nkind: task\nparent: "[[Loop A]]"\n---\n')
        assert {n.title for n in populated.descendants_of("Loop A")} == {
            "Loop A",
            "Loop B",
        } - {"Loop A"} | {"Loop B", "Loop A"} - {"Loop A"}

    def test_leaf_has_no_descendants(self, populated):
        assert populated.descendants_of("Test at 320px") == []


class TestLinkFiltersIgnoreCase:
    """Consistent with lookup (G2), uniqueness (C4) and link checking (P6). A
    case-sensitive filter returns an empty list, which reads as "no children" rather
    than "you spelled it differently" -- the worst kind of wrong answer.
    """

    def test_children_of_ignores_case(self, populated):
        assert {n.title for n in populated.children_of("DESIGN SYSTEM")} == {
            n.title for n in populated.children_of("Design system")
        }

    def test_descendants_of_ignores_case(self, populated):
        assert {n.title for n in populated.descendants_of("website RELAUNCH")} == {
            n.title for n in populated.descendants_of("Website relaunch")
        }

    def test_project_filter_ignores_case(self, populated):
        assert {n.title for n in populated.find(project="WEBSITE RELAUNCH")} == {
            n.title for n in populated.find(project="Website relaunch")
        }

    def test_non_link_filters_stay_exact(self, populated):
        """Only links are case-insensitive; a status is a vocabulary term and must
        match exactly, or the Triage view would stop catching typos.
        """
        assert populated.find(status="DOING") == []
        assert populated.find(status="doing")
