"""Crash recovery via the write-ahead journal.

Crashes are simulated by writing a journal and then leaving files in whatever state a
death at that instant would have left them -- which is exactly what recovery has to
reason about, since after a real crash the command objects are gone and only the
journal and the bytes on disk remain.

The question these tests exist to settle: after a crash, a file either holds what we
put there, what was there before, or something else entirely. Only the third case is
ambiguous, and it is the one where the user's edit must win.
"""

import json

import pytest

from planner.domain.note import Note
from planner.repository.journal import (
    JOURNAL_NAME,
    Entry,
    Journal,
    RecoveryReport,
    digest,
)
from planner.repository.markdown import MarkdownNoteRepository


def crashed_after_writing(root, path, prior: str | None, intended: str | None):
    """Leave the vault as a crash between flush and commit would have.

    Writes the journal, then applies the intended change without clearing it.
    """
    journal = Journal(root)
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    if prior is not None:
        target.write_text(prior)
    journal.record(
        Entry(
            path=path,
            prior_hash=digest(prior.encode() if prior is not None else None),
            intended_hash=digest(intended.encode() if intended is not None else None),
            prior_content=prior,
        )
    )
    if intended is None:
        target.unlink(missing_ok=True)
    else:
        target.write_text(intended)
    return journal


class TestNothingToDo:
    def test_no_journal_means_no_recovery(self, tmp_path):
        report = Journal(tmp_path).recover()
        assert not report and report.clean

    def test_recovery_is_cheap_when_idle(self, tmp_path):
        """Called on every startup, so the common case must cost one stat."""
        assert not (tmp_path / JOURNAL_NAME).exists()
        Journal(tmp_path).recover()

    def test_an_unparseable_journal_is_ignored(self, tmp_path):
        """A journal that will not parse is itself evidence of a crash, possibly during
        its own write. Nothing safe can be inferred from it, and acting on a guess is
        worse than leaving the vault as the user finds it.
        """
        (tmp_path / JOURNAL_NAME).write_text("{ truncated")
        report = Journal(tmp_path).recover()
        assert not report.restored and report.clean

    def test_a_journal_missing_its_entries_key_is_ignored(self, tmp_path):
        (tmp_path / JOURNAL_NAME).write_text(json.dumps({"started": "now"}))
        assert not Journal(tmp_path).recover()


class TestRecoveryDecisionTable:
    """The four states a file can be in when recovery finds it."""

    def test_our_write_landed_so_it_is_undone(self, tmp_path):
        crashed_after_writing(tmp_path, "Items/T.md", prior="original", intended="new")
        report = Journal(tmp_path).recover()
        assert (tmp_path / "Items/T.md").read_text() == "original"
        assert report.restored == ["Items/T.md"]
        assert report.clean

    def test_our_write_never_landed_so_nothing_is_done(self, tmp_path):
        """Crash between flushing the journal and applying the change."""
        journal = Journal(tmp_path)
        (tmp_path / "Items").mkdir()
        (tmp_path / "Items/T.md").write_text("original")
        journal.record(
            Entry("Items/T.md", digest(b"original"), digest(b"new"), "original")
        )
        report = Journal(tmp_path).recover()
        assert (tmp_path / "Items/T.md").read_text() == "original"
        assert report.untouched == ["Items/T.md"]

    def test_our_delete_landed_so_the_file_comes_back(self, tmp_path):
        crashed_after_writing(tmp_path, "Items/T.md", prior="precious", intended=None)
        assert not (tmp_path / "Items/T.md").exists()
        report = Journal(tmp_path).recover()
        assert (tmp_path / "Items/T.md").read_text() == "precious"
        assert report.restored == ["Items/T.md"]

    def test_a_created_file_is_removed_again(self, tmp_path):
        crashed_after_writing(tmp_path, "Items/T.md", prior=None, intended="brand new")
        report = Journal(tmp_path).recover()
        assert not (tmp_path / "Items/T.md").exists()
        assert report.restored == ["Items/T.md"]

    def test_an_unexplained_change_is_left_alone(self, tmp_path):
        """The case the whole design turns on. The file holds content we never wrote,
        so the only thing that can have produced it is a person editing their own
        notes after the crash -- and their edit is newer than our abandoned
        transaction.
        """
        crashed_after_writing(tmp_path, "Items/T.md", prior="original", intended="ours")
        (tmp_path / "Items/T.md").write_text("what the user typed in Obsidian")

        report = Journal(tmp_path).recover()
        assert (
            tmp_path / "Items/T.md"
        ).read_text() == "what the user typed in Obsidian"
        assert not report.restored
        assert [c.path for c in report.conflicts] == ["Items/T.md"]
        assert not report.clean

    def test_a_conflict_explains_itself(self, tmp_path):
        crashed_after_writing(tmp_path, "Items/T.md", prior="a", intended="b")
        (tmp_path / "Items/T.md").write_text("c")
        conflict = Journal(tmp_path).recover().conflicts[0]
        assert "outside this process" in conflict.reason

    def test_a_deleted_file_the_user_recreated_is_left_alone(self, tmp_path):
        crashed_after_writing(tmp_path, "Items/T.md", prior="ours", intended=None)
        (tmp_path / "Items/T.md").write_text("the user made a new note with this name")
        report = Journal(tmp_path).recover()
        assert (tmp_path / "Items/T.md").read_text().startswith("the user made")
        assert report.conflicts


class TestMultiFileRecovery:
    def test_the_whole_transaction_is_undone(self, tmp_path):
        journal = Journal(tmp_path)
        items = tmp_path / "Items"
        items.mkdir()
        for name, prior in (("a.md", "A"), ("b.md", "B"), ("c.md", "C")):
            (items / name).write_text(prior)
            journal.record(
                Entry(
                    f"Items/{name}", digest(prior.encode()), digest(b"changed"), prior
                )
            )
            (items / name).write_text("changed")

        report = Journal(tmp_path).recover()
        assert [(items / n).read_text() for n in ("a.md", "b.md", "c.md")] == [
            "A",
            "B",
            "C",
        ]
        assert len(report.restored) == 3

    def test_one_conflict_does_not_block_the_rest(self, tmp_path):
        journal = Journal(tmp_path)
        items = tmp_path / "Items"
        items.mkdir()
        for name in ("a.md", "b.md"):
            (items / name).write_text("original")
            journal.record(
                Entry(f"Items/{name}", digest(b"original"), digest(b"ours"), "original")
            )
            (items / name).write_text("ours")
        (items / "b.md").write_text("user's edit")

        report = Journal(tmp_path).recover()
        assert (items / "a.md").read_text() == "original"
        assert (items / "b.md").read_text() == "user's edit"
        assert report.restored == ["Items/a.md"]
        assert [c.path for c in report.conflicts] == ["Items/b.md"]


class TestJournalLifecycle:
    def test_the_journal_is_removed_after_recovery(self, tmp_path):
        crashed_after_writing(tmp_path, "Items/T.md", prior="a", intended="b")
        Journal(tmp_path).recover()
        assert not (tmp_path / JOURNAL_NAME).exists()

    def test_recovery_is_idempotent(self, tmp_path):
        crashed_after_writing(tmp_path, "Items/T.md", prior="original", intended="new")
        Journal(tmp_path).recover()
        second = Journal(tmp_path).recover()
        assert not second
        assert (tmp_path / "Items/T.md").read_text() == "original"

    def test_clear_removes_the_file(self, tmp_path):
        journal = Journal(tmp_path)
        journal.record(Entry("Items/T.md", None, digest(b"x"), None))
        assert (tmp_path / JOURNAL_NAME).exists()
        journal.clear()
        assert not (tmp_path / JOURNAL_NAME).exists()

    def test_no_temporary_journal_files_are_left(self, tmp_path):
        journal = Journal(tmp_path)
        journal.record(Entry("Items/T.md", None, digest(b"x"), None))
        assert [p.name for p in tmp_path.iterdir()] == [JOURNAL_NAME]


class TestThroughTheRepository:
    def test_a_committed_transaction_leaves_no_journal(self, repo):
        with repo.unit_of_work():
            repo.save(Note(kind="task", title="T"))
        assert not (repo.root / JOURNAL_NAME).exists()
        assert not repo.recover()

    def test_an_in_process_rollback_leaves_no_journal(self, repo):
        class Boom(Exception):
            pass

        with pytest.raises(Boom), repo.unit_of_work():
            repo.save(Note(kind="task", title="T"))
            raise Boom()
        assert not (repo.root / JOURNAL_NAME).exists()

    def test_recovery_undoes_a_simulated_crash(self, repo):
        """The end-to-end property: kill the process mid-transaction and the next
        startup puts the vault back.
        """
        repo.save(Note(kind="task", title="T", fields={"priority": 1}))
        original = repo.find("T").read_bytes()

        # Journal an overwrite and apply it, then "die" without clearing.
        entry = Entry(
            "Items/T.md", digest(original), digest(b"corrupted"), original.decode()
        )
        Journal(repo.root).record(entry)
        repo.find("T").write_bytes(b"corrupted")

        report = MarkdownNoteRepository(repo.root).recover()
        assert report.restored == ["Items/T.md"]
        assert repo.find("T").read_bytes() == original
        assert repo.get("T").fields["priority"] == 1

    def test_the_journal_is_never_mistaken_for_a_note(self, repo):
        """It lives at the vault root and starts with a dot, but a listing that picked
        it up would report it as an unparseable note forever.
        """
        Journal(repo.root).record(Entry("Items/T.md", None, digest(b"x"), None))
        assert "planner-journal" not in " ".join(repo.titles())
        assert list(repo.iter_all()) == []


class TestRecoveryReport:
    def test_falsy_when_there_was_nothing_to_do(self):
        assert not RecoveryReport()

    def test_truthy_when_anything_happened(self):
        assert RecoveryReport(restored=["a"])
        assert RecoveryReport(untouched=["a"])

    def test_clean_means_no_conflicts(self, tmp_path):
        assert RecoveryReport(restored=["a"]).clean
        crashed_after_writing(tmp_path, "Items/T.md", prior="a", intended="b")
        (tmp_path / "Items/T.md").write_text("c")
        assert not Journal(tmp_path).recover().clean


class TestJournalWriteFailure:
    def test_a_failed_flush_leaves_no_temporary_file(self, tmp_path, monkeypatch):
        """The journal lives at the vault root, where Obsidian would index litter."""
        import os

        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        journal = Journal(tmp_path)
        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            journal.record(Entry("Items/T.md", None, digest(b"x"), None))
        assert list(tmp_path.iterdir()) == []

    def test_a_failed_flush_propagates_rather_than_writing_blind(
        self, tmp_path, monkeypatch
    ):
        """If intent cannot be recorded, the change must not happen -- an unjournalled
        write is exactly the crash case recovery cannot reason about.
        """
        import os

        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            Journal(tmp_path).record(Entry("Items/T.md", None, digest(b"x"), None))


class TestCommitRecordWindow:
    """A crash between the last file write and clearing the journal is indistinguishable
    from a transaction that never completed: journal present, file holding what we
    intended. Recovery undoes it.

    That means a transaction which actually succeeded can be rolled back. It is the
    conservative choice -- a consistent vault and a retryable caller, rather than a
    half-applied transaction presented as whole -- and it cannot be closed without
    two-phase commit, which the filesystem cannot participate in. These tests pin the
    behaviour so nobody later mistakes it for a bug and "fixes" it into the other one.
    """

    def test_a_committed_transaction_is_undone_if_the_journal_survived(self, tmp_path):
        crashed_after_writing(tmp_path, "Items/T.md", prior="original", intended="new")
        # The write landed and the transaction was, in truth, complete -- only the
        # journal never got cleared.
        assert (tmp_path / "Items/T.md").read_text() == "new"

        report = Journal(tmp_path).recover()

        assert (tmp_path / "Items/T.md").read_text() == "original"
        assert report.restored == ["Items/T.md"]

    def test_the_result_is_still_a_state_the_api_would_accept(self, repo):
        """Why undoing a good transaction is tolerable: what you are left with is a
        vault that validates, not a broken one.
        """
        from planner.service.notes import NoteService

        service = NoteService(repo)
        service.create(kind="task", title="T", priority=1)
        original = repo.find("T").read_bytes()

        Journal(repo.root).record(
            Entry(
                "Items/T.md", digest(original), digest(b"whatever"), original.decode()
            )
        )
        repo.find("T").write_bytes(b"whatever")

        MarkdownNoteRepository(repo.root).recover()
        assert service.problems() == []
        assert service.get("T").fields["priority"] == 1

    def test_clearing_happens_after_the_writes_so_the_window_is_as_small_as_possible(
        self, repo
    ):
        """It cannot be eliminated, only narrowed: the journal is cleared once, at the
        end, rather than progressively as commands land.
        """
        seen = []
        real_clear = repo.journal.clear

        def spy():
            seen.append(repo.find("Two") is not None)
            return real_clear()

        repo.journal.clear = spy
        with repo.unit_of_work():
            repo.save(Note(kind="task", title="One"))
            repo.save(Note(kind="task", title="Two"))
        assert seen == [True]  # every write had landed before the single clear


class TestBrokenRollbackWithoutADatabase:
    def test_the_file_journal_can_only_shout(self, tmp_path, caplog):
        """It keeps nothing after a transaction, so a mixed state cannot be recorded
        here -- which is one of the things the Postgres backend is for.
        """
        import logging

        journal = Journal(tmp_path)
        with caplog.at_level(logging.ERROR, logger="planner.repository"):
            journal.conflicted(["Items/T.md"])
        assert "mixed state" in caplog.text
        assert "Items/T.md" in caplog.text

    def test_it_still_clears_so_startup_does_not_re_recover(self, tmp_path):
        journal = Journal(tmp_path)
        journal.record(Entry("Items/T.md", None, digest(b"x"), None))
        journal.conflicted(["Items/T.md"])
        assert not journal.has_pending()
