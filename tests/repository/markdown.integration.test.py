"""The markdown adapter against a real directory tree.

Persistence only. Anything about defaults or relationships is the service's job and is
tested there; what matters here is that a note survives a round trip through disk, that
placement follows kind, and that a half-written file does not break a listing.
"""

import pytest

from planner.domain.errors import NoteNotFound
from planner.domain.note import Note
from planner.domain.schema import KINDS
from planner.repository.markdown import CONTENT_FOLDERS, MarkdownNoteRepository


class TestPlacement:
    @pytest.mark.parametrize("kind,folder", [(k.name, k.folder) for k in KINDS.values()])
    def test_folder_is_derived_from_kind(self, repo, kind, folder):
        repo.save(Note(kind=kind, title=f"A {kind}"))
        assert (repo.root / folder / f"A {kind}.md").is_file()

    def test_path_for_does_not_touch_disk(self, repo):
        path = repo.path_for("task", "Nothing")
        assert path.name == "Nothing.md" and not path.exists()

    def test_save_creates_missing_folders(self, tmp_path):
        """A clone that has not been opened in Obsidian yet may be missing them."""
        bare = MarkdownNoteRepository(tmp_path / "fresh")
        bare.save(Note(kind="task", title="T"))
        assert (bare.root / "Items" / "T.md").is_file()

    def test_overwrite_keeps_the_original_location(self, repo):
        """A note moved by hand in Obsidian must not jump back on the next write."""
        stray = repo.root / "Journal" / "Wandered.md"
        stray.write_text(Note(kind="task", title="Wandered").to_markdown())
        repo.save(Note(kind="task", title="Wandered", fields={"priority": 1}))
        assert stray.is_file()
        assert not (repo.root / "Items" / "Wandered.md").exists()


class TestFind:
    def test_locates_across_folders(self, repo):
        repo.save(Note(kind="decision", title="D"))
        assert repo.find("D").parent.name == "Docs"

    def test_missing_returns_none(self, repo):
        assert repo.find("Nope") is None

    def test_exists(self, repo):
        repo.save(Note(kind="task", title="T"))
        assert repo.exists("T")

    def test_exists_is_as_case_sensitive_as_the_filesystem(self, repo, tmp_path):
        """Not a guarantee this layer makes. macOS is case-insensitive by default and
        Linux is not, so `exists("t")` for a file named T.md differs by machine. The
        service does not rely on it -- uniqueness is checked with casefold there."""
        repo.save(Note(kind="task", title="T"))
        probe = tmp_path / "CaseProbe"
        probe.write_text("x")
        insensitive = (tmp_path / "caseprobe").exists()
        assert repo.exists("t") is insensitive

    def test_find_falls_back_to_a_case_insensitive_scan(self, repo):
        """So lookup does not depend on the filesystem. On a case-sensitive volume the
        exact-path probe misses and this fallback is what answers; on macOS the probe
        already matched. Either way the application decides, not the disk."""
        repo.save(Note(kind="task", title="MixedCase Title"))
        assert repo.find("mixedcase title") is not None

    def test_find_returns_the_stored_spelling_not_the_requested_one(self, repo):
        """On a case-insensitive volume the exact-path probe matches a differently
        cased file, and Path.stem would echo the caller's spelling -- yielding a title
        no note has, which would then 409 as a case clash if fed back."""
        repo.save(Note(kind="task", title="MixedCase Title"))
        for spelling in ("mixedcase title", "MIXEDCASE TITLE", "MixedCase Title"):
            assert repo.find(spelling).stem == "MixedCase Title"

    def test_get_returns_the_canonical_title(self, repo):
        repo.save(Note(kind="task", title="MixedCase Title"))
        assert repo.get("MIXEDCASE TITLE").title == "MixedCase Title"

    def test_scan_finds_by_case_regardless_of_filesystem(self, repo):
        """The branch that only executes on a case-sensitive volume. macOS matches on
        the exact-path probe first, so exercising it directly is the only way to cover
        it on a developer machine as well as in production."""
        repo.save(Note(kind="task", title="MixedCase Title"))
        assert repo._scan_for("mixedcase title").stem == "MixedCase Title"
        assert repo._scan_for("nothing here") is None

    def test_find_still_returns_none_for_a_genuine_miss(self, repo):
        repo.save(Note(kind="task", title="Present"))
        assert repo.find("Absent") is None

    def test_titles_lists_without_parsing(self, repo):
        repo.save(Note(kind="task", title="One"))
        (repo.root / "Items" / "Unparseable.md").write_text("no frontmatter")
        assert set(repo.titles()) == {"One", "Unparseable"}

    def test_searches_every_content_folder(self, repo):
        for folder in CONTENT_FOLDERS:
            (repo.root / folder / f"In {folder}.md").write_text(
                Note(kind="task", title=f"In {folder}").to_markdown())
        for folder in CONTENT_FOLDERS:
            assert repo.exists(f"In {folder}")


class TestRoundTrip:
    def test_note_survives_disk(self, repo):
        original = Note(kind="task", title="T", fields={
            "status": "blocked", "priority": 2, "blocked_by": ["A"]}, body="\n# T\n\nX\n")
        repo.save(original)
        back = repo.get("T")
        assert back.kind == "task"
        assert back.fields["status"] == "blocked"
        assert back.fields["blocked_by"] == ["A"]
        assert "X" in back.body

    def test_get_missing_raises(self, repo):
        with pytest.raises(NoteNotFound):
            repo.get("Nope")


class TestIteration:
    def test_iter_all_skips_unreadable(self, repo):
        """A vault is hand-editable text and Obsidian writes to it too, so a file may
        be mid-edit. One bad note must not take down a listing."""
        repo.save(Note(kind="task", title="Good"))
        (repo.root / "Items" / "Bad.md").write_text("no frontmatter here")
        assert [n.title for n in repo.iter_all()] == ["Good"]

    def test_iter_raw_includes_unreadable(self, repo):
        repo.save(Note(kind="task", title="Good"))
        (repo.root / "Items" / "Bad.md").write_text("no frontmatter")
        assert {t for t, _ in repo.iter_raw()} == {"Good", "Bad"}

    def test_iteration_is_sorted_within_a_folder(self, repo):
        for title in ("Charlie", "Alpha", "Bravo"):
            repo.save(Note(kind="task", title=title))
        assert [n.title for n in repo.iter_all()] == ["Alpha", "Bravo", "Charlie"]

    def test_missing_folders_are_tolerated(self, tmp_path):
        bare = MarkdownNoteRepository(tmp_path)
        assert list(bare.iter_all()) == []

    def test_non_markdown_files_are_ignored(self, repo):
        (repo.root / "Items" / "notes.txt").write_text("not a note")
        (repo.root / "Items" / "image.png").write_bytes(b"\x89PNG")
        assert list(repo.iter_all()) == []


class TestDelete:
    def test_removes_the_file(self, repo):
        repo.save(Note(kind="task", title="T"))
        repo.delete("T")
        assert not repo.exists("T")

    def test_missing_raises(self, repo):
        with pytest.raises(NoteNotFound):
            repo.delete("Nope")


class TestRootHandling:
    def test_names_in_tolerates_a_missing_directory(self, tmp_path):
        """find() probes folders that a fresh clone may not have yet."""
        from planner.repository.markdown import _names_in
        assert _names_in(tmp_path / "absent") == set()

    def test_accepts_a_string_path(self, tmp_path):
        assert MarkdownNoteRepository(str(tmp_path)).root == tmp_path


class TestBinaryFiles:
    def test_undecodable_file_is_skipped_by_both_iterators(self, repo):
        """Someone drops a renamed image into Items/. Neither listing may explode."""
        (repo.root / "Items" / "Binary.md").write_bytes(b"\xff\xfe\x00\x80bad")
        repo.save(Note(kind="task", title="Fine"))
        assert [n.title for n in repo.iter_all()] == ["Fine"]
        assert [t for t, _ in repo.iter_raw()] == ["Fine"]
