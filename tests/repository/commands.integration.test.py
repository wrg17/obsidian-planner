"""Reversible filesystem commands.

Each command is tested for the two things it promises: that it does what it says, and
that undo restores exactly the state that existed immediately before it ran.
"""

import os
import stat

import pytest

from planner.repository.commands import (
    Command, CommandError, CreateDirectory, DeleteFile, WriteFile, _atomic_write,
)


@pytest.fixture
def target(tmp_path):
    return tmp_path / "note.md"


class TestConformance:
    @pytest.mark.parametrize("factory", [
        lambda p: WriteFile(p, "x"),
        lambda p: DeleteFile(p),
        lambda p: CreateDirectory(p),
    ])
    def test_every_command_satisfies_the_protocol(self, factory, target):
        assert isinstance(factory(target), Command)

    @pytest.mark.parametrize("factory", [
        lambda p: WriteFile(p, "x"),
        lambda p: DeleteFile(p),
        lambda p: CreateDirectory(p),
    ])
    def test_every_command_describes_itself(self, factory, target):
        """The description ends up in rollback errors, where "a command failed" would
        be useless."""
        assert factory(target).describe().strip()


class TestWriteFile:
    def test_creates_a_file(self, target):
        WriteFile(target, "hello").execute()
        assert target.read_text() == "hello"

    def test_overwrites_an_existing_file(self, target):
        target.write_text("old")
        WriteFile(target, "new").execute()
        assert target.read_text() == "new"

    def test_undo_restores_the_previous_content(self, target):
        target.write_text("old")
        command = WriteFile(target, "new")
        command.execute()
        command.undo()
        assert target.read_text() == "old"

    def test_undo_removes_a_file_that_did_not_exist_before(self, target):
        command = WriteFile(target, "new")
        command.execute()
        command.undo()
        assert not target.exists()

    def test_undo_before_execute_is_a_no_op(self, target):
        target.write_text("untouched")
        WriteFile(target, "new").undo()
        assert target.read_text() == "untouched"

    def test_running_twice_is_refused(self, target):
        """Re-running would capture the state it created as the state to restore,
        making undo a no-op that silently keeps the change."""
        command = WriteFile(target, "x")
        command.execute()
        with pytest.raises(CommandError, match="already run"):
            command.execute()

    def test_undo_is_idempotent(self, target):
        target.write_text("old")
        command = WriteFile(target, "new")
        command.execute()
        command.undo()
        command.undo()
        assert target.read_text() == "old"

    def test_creates_missing_parent_directories(self, tmp_path):
        nested = tmp_path / "a" / "b" / "note.md"
        WriteFile(nested, "x").execute()
        assert nested.read_text() == "x"

    def test_prior_state_is_captured_at_execute_not_construction(self, target):
        """The rule that makes undo trustworthy inside a transaction: an earlier
        command may already have changed the file, and a snapshot taken when the
        command was built would restore bytes that were never current."""
        target.write_text("first")
        command = WriteFile(target, "third")     # built now...
        target.write_text("second")              # ...but the world moves on
        command.execute()
        command.undo()
        assert target.read_text() == "second"

    def test_unicode_survives(self, target):
        WriteFile(target, "— naïve café 🎯\n").execute()
        assert target.read_text(encoding="utf-8") == "— naïve café 🎯\n"


class TestAtomicWrite:
    def test_no_temporary_files_are_left_behind(self, tmp_path):
        WriteFile(tmp_path / "a.md", "x").execute()
        assert [p.name for p in tmp_path.iterdir()] == ["a.md"]

    def test_temporary_file_is_removed_when_the_write_fails(self, tmp_path, monkeypatch):
        """Otherwise a failed write litters the vault with .planner-*.tmp files that
        Obsidian would happily index."""
        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            _atomic_write(tmp_path / "a.md", b"x")
        assert list(tmp_path.iterdir()) == []

    def test_the_target_is_untouched_when_the_write_fails(self, tmp_path, monkeypatch):
        target = tmp_path / "a.md"
        target.write_text("original")

        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            _atomic_write(target, b"replacement")
        assert target.read_text() == "original"

    def test_temporary_file_shares_the_target_directory(self, tmp_path, monkeypatch):
        """os.replace is only atomic within one filesystem; a temp file elsewhere
        would silently degrade to a copy."""
        seen = {}
        real = os.replace

        def spy(src, dst):
            seen["src_parent"] = os.path.dirname(src)
            return real(src, dst)

        monkeypatch.setattr(os, "replace", spy)
        _atomic_write(tmp_path / "a.md", b"x")
        assert seen["src_parent"] == str(tmp_path)


class TestDeleteFile:
    def test_removes_the_file(self, target):
        target.write_text("x")
        DeleteFile(target).execute()
        assert not target.exists()

    def test_undo_restores_the_bytes(self, target):
        target.write_text("precious")
        command = DeleteFile(target)
        command.execute()
        command.undo()
        assert target.read_text() == "precious"

    def test_deleting_a_missing_file_is_an_error(self, target):
        with pytest.raises(CommandError, match="missing file"):
            DeleteFile(target).execute()

    def test_running_twice_is_refused(self, target):
        target.write_text("x")
        command = DeleteFile(target)
        command.execute()
        with pytest.raises(CommandError):
            command.execute()

    def test_undo_restores_binary_content_faithfully(self, target):
        target.write_bytes(b"\x00\xff\xfe binary")
        command = DeleteFile(target)
        command.execute()
        command.undo()
        assert target.read_bytes() == b"\x00\xff\xfe binary"


class TestCreateDirectory:
    def test_creates_a_missing_directory(self, tmp_path):
        CreateDirectory(tmp_path / "new").execute()
        assert (tmp_path / "new").is_dir()

    def test_existing_directory_is_left_alone_and_not_undone(self, tmp_path):
        """Undo may only remove what this command created; removing a pre-existing
        directory would destroy something the caller never asked to touch."""
        existing = tmp_path / "Items"
        existing.mkdir()
        command = CreateDirectory(existing)
        command.execute()
        command.undo()
        assert existing.is_dir()

    def test_undo_removes_a_directory_it_created(self, tmp_path):
        command = CreateDirectory(tmp_path / "new")
        command.execute()
        command.undo()
        assert not (tmp_path / "new").exists()

    def test_undo_keeps_a_directory_that_is_no_longer_empty(self, tmp_path):
        """Something else started using it between execute and undo."""
        created = tmp_path / "new"
        command = CreateDirectory(created)
        command.execute()
        (created / "someone-elses-file").write_text("x")
        command.undo()
        assert created.is_dir()

    def test_undo_survives_an_unremovable_directory(self, tmp_path):
        created = tmp_path / "new"
        command = CreateDirectory(created)
        command.execute()
        created.rmdir()                     # already gone; undo must not raise
        command.undo()

    def test_undo_is_idempotent(self, tmp_path):
        command = CreateDirectory(tmp_path / "new")
        command.execute()
        command.undo()
        command.undo()
        assert not (tmp_path / "new").exists()

    def test_creates_nested_paths(self, tmp_path):
        CreateDirectory(tmp_path / "a" / "b" / "c").execute()
        assert (tmp_path / "a" / "b" / "c").is_dir()


class TestPrepareApplySplit:
    """Execution is split so the journal can record intent between reading the world
    and changing it. Applying without preparing would write with no undo captured."""

    def test_write_refuses_to_apply_unprepared(self, target):
        with pytest.raises(CommandError, match="not prepared"):
            WriteFile(target, "x").apply()

    def test_delete_refuses_to_apply_unprepared(self, target):
        target.write_text("x")
        with pytest.raises(CommandError, match="not prepared"):
            DeleteFile(target).apply()

    def test_prepare_changes_nothing(self, target):
        target.write_text("original")
        WriteFile(target, "new").prepare()
        assert target.read_text() == "original"

    def test_journal_entry_describes_both_ends(self, tmp_path):
        target = tmp_path / "a.md"
        target.write_text("before")
        command = WriteFile(target, "after")
        command.prepare()
        entry = command.journal_entry(tmp_path)
        assert entry.path == "a.md"
        assert entry.prior_content == "before"
        assert entry.prior_hash != entry.intended_hash

    def test_journal_entry_for_a_new_file_has_no_prior(self, tmp_path):
        command = WriteFile(tmp_path / "a.md", "new")
        command.prepare()
        entry = command.journal_entry(tmp_path)
        assert entry.prior_hash is None and entry.prior_content is None

    def test_journal_entry_for_a_delete_intends_absence(self, tmp_path):
        target = tmp_path / "a.md"
        target.write_text("doomed")
        command = DeleteFile(target)
        command.prepare()
        entry = command.journal_entry(tmp_path)
        assert entry.intended_hash is None and entry.prior_content == "doomed"

    def test_a_directory_needs_no_journal_entry(self, tmp_path):
        """It holds no content to lose, and undo already refuses to remove one it did
        not create or one that is no longer empty."""
        command = CreateDirectory(tmp_path / "new")
        command.prepare()
        assert command.journal_entry(tmp_path) is None


class TestUndoRefusesToClobber:
    """Undo restores the prior state only while the file still holds what we wrote.

    The same rule crash recovery applies, and the reason it matters more here: a crash
    is rare, but a rollback happens whenever a request fails, and Obsidian writes
    continuously. This was the more dangerous of the two paths and was missing the
    check entirely.
    """

    def test_a_concurrently_edited_file_is_not_restored(self, target):
        from planner.repository.commands import ConcurrentModification

        target.write_text("original")
        command = WriteFile(target, "ours")
        command.execute()
        target.write_text("edited in obsidian")

        with pytest.raises(ConcurrentModification):
            command.undo()
        assert target.read_text() == "edited in obsidian"

    def test_the_error_names_the_file_and_says_what_was_left(self, target):
        from planner.repository.commands import ConcurrentModification

        target.write_text("original")
        command = WriteFile(target, "ours")
        command.execute()
        target.write_text("theirs")
        with pytest.raises(ConcurrentModification) as caught:
            command.undo()
        assert target.name in str(caught.value)
        assert "left in place" in str(caught.value)
        assert caught.value.path == target

    def test_an_untouched_file_is_still_restored(self, target):
        target.write_text("original")
        command = WriteFile(target, "ours")
        command.execute()
        command.undo()
        assert target.read_text() == "original"

    def test_a_recreated_file_is_not_deleted_again(self, target):
        """We deleted it; the user made a new note with the same name. Undoing our
        delete would restore our content over theirs."""
        from planner.repository.commands import ConcurrentModification

        target.write_text("ours")
        command = DeleteFile(target)
        command.execute()
        target.write_text("a new note the user just made")

        with pytest.raises(ConcurrentModification):
            command.undo()
        assert target.read_text() == "a new note the user just made"

    def test_an_undone_delete_still_works_when_nothing_intervened(self, target):
        target.write_text("precious")
        command = DeleteFile(target)
        command.execute()
        command.undo()
        assert target.read_text() == "precious"

    def test_a_created_file_edited_before_rollback_is_kept(self, target):
        """We created it, the user typed into it, then our transaction failed.
        Deleting it would throw away work they can see on screen."""
        from planner.repository.commands import ConcurrentModification

        command = WriteFile(target, "our skeleton")
        command.execute()
        target.write_text("our skeleton plus their notes")

        with pytest.raises(ConcurrentModification):
            command.undo()
        assert target.exists()
