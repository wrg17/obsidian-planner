"""All-or-nothing filesystem transactions.

The property under test throughout: after a failed transaction the vault is byte-for-
byte what it was before the transaction started (S3), including for operations that
touch several files.
"""

import pytest

from planner.domain.note import Note
from planner.repository.commands import CommandError, DeleteFile, WriteFile
from planner.repository.unit_of_work import RollbackError, UnitOfWork


class Boom(Exception):
    """A failure raised by the caller, not by a command."""


class FakeCommand:
    """A command that touches nothing, for testing ordering and failure handling.

    Implements the whole protocol including the journalling half, so it exercises the
    same path a real command does. `journal_entry` returns None -- it has no file to
    record, like CreateDirectory.
    """

    def prepare(self):
        pass

    def apply(self):
        pass

    def execute(self):
        self.prepare()
        self.apply()

    def journal_entry(self, root):
        return None

    def undo(self):
        pass

    def describe(self):
        return type(self).__name__


class TestCommitPath:
    def test_commands_are_applied_on_a_clean_exit(self, tmp_path):
        with UnitOfWork() as uow:
            uow.execute(WriteFile(tmp_path / "a.md", "A"))
            uow.execute(WriteFile(tmp_path / "b.md", "B"))
        assert (tmp_path / "a.md").read_text() == "A"
        assert (tmp_path / "b.md").read_text() == "B"

    def test_changes_are_visible_inside_the_block(self, tmp_path):
        """Not isolated, and documented as such: Obsidian is reading these files
        throughout, so there is nowhere to hide an uncommitted write.
        """
        with UnitOfWork() as uow:
            uow.execute(WriteFile(tmp_path / "a.md", "A"))
            assert (tmp_path / "a.md").read_text() == "A"

    def test_the_record_is_cleared_after_committing(self, tmp_path):
        """Otherwise a later rollback would try to undo an earlier, committed
        transaction.
        """
        uow = UnitOfWork()
        with uow:
            uow.execute(WriteFile(tmp_path / "a.md", "A"))
        with pytest.raises(Boom), uow:
            raise Boom()
        assert (tmp_path / "a.md").read_text() == "A"


class TestRollback:
    def test_a_failure_undoes_everything_applied(self, tmp_path):
        with pytest.raises(Boom), UnitOfWork() as uow:
            uow.execute(WriteFile(tmp_path / "a.md", "A"))
            uow.execute(WriteFile(tmp_path / "b.md", "B"))
            raise Boom()
        assert not (tmp_path / "a.md").exists()
        assert not (tmp_path / "b.md").exists()

    def test_previous_content_is_restored_not_merely_deleted(self, tmp_path):
        (tmp_path / "a.md").write_text("original")
        with pytest.raises(Boom), UnitOfWork() as uow:
            uow.execute(WriteFile(tmp_path / "a.md", "replacement"))
            raise Boom()
        assert (tmp_path / "a.md").read_text() == "original"

    def test_a_failing_command_rolls_back_the_ones_before_it(self, tmp_path):
        (tmp_path / "a.md").write_text("A")
        with pytest.raises(CommandError), UnitOfWork() as uow:
            uow.execute(DeleteFile(tmp_path / "a.md"))
            uow.execute(DeleteFile(tmp_path / "missing.md"))  # raises
        assert (tmp_path / "a.md").read_text() == "A"

    def test_undo_runs_in_reverse_order(self, tmp_path):
        """A later command may depend on what an earlier one did; undoing forwards can
        leave the earlier undo with nothing to restore.
        """
        order = []

        class Recording(FakeCommand):
            def __init__(self, name):
                self.name = name

            def undo(self):
                order.append(self.name)

            def describe(self):
                return self.name

        with pytest.raises(Boom), UnitOfWork() as uow:
            uow.execute(Recording("first"))
            uow.execute(Recording("second"))
            uow.execute(Recording("third"))
            raise Boom()
        assert order == ["third", "second", "first"]

    def test_the_original_exception_is_not_swallowed(self, tmp_path):
        with pytest.raises(Boom), UnitOfWork() as uow:
            uow.execute(WriteFile(tmp_path / "a.md", "A"))
            raise Boom()

    def test_explicit_rollback_without_an_exception(self, tmp_path):
        uow = UnitOfWork()
        uow.enter()
        uow.execute(WriteFile(tmp_path / "a.md", "A"))
        uow.rollback()
        assert not (tmp_path / "a.md").exists()


class TestRollbackFailure:
    def test_every_command_is_attempted_even_after_one_fails(self, tmp_path):
        """Stopping at the first failure would strand the vault further from where it
        started than finishing does.
        """
        attempted = []

        class Stubborn(FakeCommand):
            def undo(self):
                attempted.append("stubborn")
                raise OSError("permission denied")

            def describe(self):
                return "stubborn"

        class Fine(FakeCommand):
            def undo(self):
                attempted.append("fine")

            def describe(self):
                return "fine"

        with pytest.raises(RollbackError), UnitOfWork() as uow:
            uow.execute(Fine())
            uow.execute(Stubborn())
            raise Boom()
        assert attempted == ["stubborn", "fine"]

    def test_the_error_carries_both_faults(self, tmp_path):
        """The original explains what was attempted; the rollback failure explains
        what is now inconsistent. Someone has to reconcile that by hand.
        """

        class Stubborn(FakeCommand):
            def undo(self):
                raise OSError("permission denied")

            def describe(self):
                return "stubborn command"

        with pytest.raises(RollbackError) as caught, UnitOfWork() as uow:
            uow.execute(Stubborn())
            raise Boom("the original problem")
        assert isinstance(caught.value.cause, Boom)
        assert "the original problem" in str(caught.value)
        assert "stubborn command" in str(caught.value)
        assert "permission denied" in str(caught.value)


class TestNesting:
    def test_an_inner_block_joins_rather_than_committing(self, tmp_path):
        """`close()` calls `update()`, which saves -- so a wrapped operation calling
        another wrapped operation is routine. An inner commit would let half an outer
        operation survive its failure.
        """
        uow = UnitOfWork()
        with pytest.raises(Boom), uow:
            uow.execute(WriteFile(tmp_path / "outer.md", "O"))
            with uow:
                uow.execute(WriteFile(tmp_path / "inner.md", "I"))
            # inner scope exited cleanly, but the outer one fails
            raise Boom()
        assert not (tmp_path / "outer.md").exists()
        assert not (tmp_path / "inner.md").exists()

    def test_active_reflects_depth(self, tmp_path):
        uow = UnitOfWork()
        assert not uow.active
        with uow:
            assert uow.active
            with uow:
                assert uow.active
            assert uow.active
        assert not uow.active

    def test_a_failure_inside_an_inner_block_rolls_the_whole_thing_back(self, tmp_path):
        uow = UnitOfWork()
        with pytest.raises(Boom), uow:
            uow.execute(WriteFile(tmp_path / "outer.md", "O"))
            with uow:
                uow.execute(WriteFile(tmp_path / "inner.md", "I"))
                raise Boom()
        assert not (tmp_path / "outer.md").exists()
        assert not (tmp_path / "inner.md").exists()


class TestThroughTheRepository:
    def test_a_single_save_outside_a_transaction_still_works(self, repo):
        repo.save(Note(kind="task", title="Solo"))
        assert repo.exists("Solo")

    def test_saves_inside_a_transaction_are_grouped(self, repo):
        with pytest.raises(Boom), repo.unit_of_work():
            repo.save(Note(kind="task", title="One"))
            repo.save(Note(kind="task", title="Two"))
            raise Boom()
        assert not repo.exists("One")
        assert not repo.exists("Two")

    def test_a_rolled_back_overwrite_restores_the_original_note(self, repo):
        repo.save(Note(kind="task", title="T", fields={"priority": 1}))
        original = repo.find("T").read_bytes()
        with pytest.raises(Boom), repo.unit_of_work():
            repo.save(Note(kind="task", title="T", fields={"priority": 4}))
            raise Boom()
        assert repo.find("T").read_bytes() == original

    def test_a_rolled_back_delete_restores_the_note(self, repo):
        repo.save(Note(kind="task", title="T"))
        with pytest.raises(Boom), repo.unit_of_work():
            repo.delete("T")
            raise Boom()
        assert repo.exists("T")

    def test_no_temporary_files_survive_a_rollback(self, repo):
        with pytest.raises(Boom), repo.unit_of_work():
            repo.save(Note(kind="task", title="T"))
            raise Boom()
        leftovers = [
            p.name
            for p in (repo.root / "Items").iterdir()
            if p.name.startswith(".planner-")
        ]
        assert leftovers == []


class TestCascadeDeleteIsAtomic:
    """The operation the unit of work was built for. Before it, a failure part-way
    through left some children deleted and the rest pointing at a parent that was
    about to be gone -- the state D2 exists to prevent, reached by another road.
    """

    def test_a_failure_mid_cascade_restores_the_whole_subtree(
        self, populated, monkeypatch
    ):
        before = {
            t: populated.repo.find(t).read_bytes() for t in populated.repo.titles()
        }
        real_delete = populated.repo.delete
        calls = {"n": 0}

        def failing_delete(title):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("device disappeared")
            return real_delete(title)

        monkeypatch.setattr(populated.repo, "delete", failing_delete)
        with pytest.raises(OSError):
            populated.delete("Design system", cascade=True)

        after = {
            t: populated.repo.find(t).read_bytes() for t in populated.repo.titles()
        }
        assert after == before

    def test_a_successful_cascade_still_removes_everything(self, populated):
        removed = populated.delete("Design system", cascade=True)
        assert "Design system" in removed
        for title in removed:
            assert not populated.exists(title)


class TestBulkCreate:
    def test_all_or_nothing(self, populated):
        from planner.domain.errors import ValidationError

        before = set(populated.repo.titles())
        with pytest.raises(ValidationError):
            populated.create_many(
                [
                    Note(kind="task", title="Bulk one"),
                    Note(kind="task", title="Bulk two", fields={"status": "nonsense"}),
                ]
            )
        assert set(populated.repo.titles()) == before

    def test_a_clean_batch_is_written(self, populated):
        created = populated.create_many(
            [
                Note(kind="task", title="Bulk one"),
                Note(kind="task", title="Bulk two"),
            ]
        )
        assert [n.title for n in created] == ["Bulk one", "Bulk two"]
        assert populated.exists("Bulk one") and populated.exists("Bulk two")

    def test_order_is_the_callers_responsibility(self, populated):
        """A child before its parent fails, because validation runs against what is on
        disk rather than against a promise about the rest of the batch.
        """
        from planner.domain.errors import ValidationError

        with pytest.raises(ValidationError, match="parent"):
            populated.create_many(
                [
                    Note(kind="task", title="Child", fields={"parent": "New epic"}),
                    Note(kind="epic", title="New epic"),
                ]
            )
        assert not populated.exists("Child")


class TestRollbackPreservesConcurrentEdits:
    """A rollback that clobbers the user's edit to tidy up after a transaction they
    never knew about is worse than an incomplete rollback.
    """

    def test_the_edit_survives_and_the_rest_is_still_undone(self, tmp_path):
        (tmp_path / "a.md").write_text("A original")
        (tmp_path / "b.md").write_text("B original")
        with pytest.raises(Boom), UnitOfWork() as uow:
            uow.execute(WriteFile(tmp_path / "a.md", "A ours"))
            uow.execute(WriteFile(tmp_path / "b.md", "B ours"))
            (tmp_path / "b.md").write_text("B edited in obsidian")
            raise Boom()
        assert (tmp_path / "a.md").read_text() == "A original"
        assert (tmp_path / "b.md").read_text() == "B edited in obsidian"

    def test_conflicts_are_recorded_on_the_unit_of_work(self, tmp_path):
        uow = UnitOfWork()
        with pytest.raises(Boom), uow:
            uow.execute(WriteFile(tmp_path / "a.md", "ours"))
            (tmp_path / "a.md").write_text("theirs")
            raise Boom()
        assert [c.path.name for c in uow.conflicts] == ["a.md"]

    def test_a_conflict_does_not_replace_the_original_exception(self, tmp_path):
        """The caller needs to know why the transaction failed. A rollback that
        deliberately preserved someone's edit is not the reason.
        """
        with pytest.raises(Boom), UnitOfWork() as uow:
            uow.execute(WriteFile(tmp_path / "a.md", "ours"))
            (tmp_path / "a.md").write_text("theirs")
            raise Boom()

    def test_a_conflict_is_logged_loudly(self, tmp_path, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="planner.repository"):
            with pytest.raises(Boom):
                with UnitOfWork() as uow:
                    uow.execute(WriteFile(tmp_path / "a.md", "ours"))
                    (tmp_path / "a.md").write_text("theirs")
                    raise Boom()
        assert "modified by something else" in caplog.text

    def test_a_conflict_is_not_counted_as_a_rollback_failure(self, tmp_path):
        """Nothing went wrong -- the command declined to act, which is correct."""
        uow = UnitOfWork()
        with pytest.raises(Boom), uow:
            uow.execute(WriteFile(tmp_path / "a.md", "ours"))
            (tmp_path / "a.md").write_text("theirs")
            raise Boom()
        # RollbackError would have replaced Boom; it did not.

    def test_conflicts_reset_between_transactions(self, tmp_path):
        uow = UnitOfWork()
        with pytest.raises(Boom), uow:
            uow.execute(WriteFile(tmp_path / "a.md", "ours"))
            (tmp_path / "a.md").write_text("theirs")
            raise Boom()
        with pytest.raises(Boom), uow:
            uow.execute(WriteFile(tmp_path / "b.md", "ours"))
            raise Boom()
        assert uow.conflicts == []
