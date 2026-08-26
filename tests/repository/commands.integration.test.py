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
