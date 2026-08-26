"""Backend selection and the degradation rule.

The decision this file pins: when Postgres is unreachable, writes still happen. A
database being down is not a reason someone cannot write a note in their own vault --
the cost is a gap in the audit trail, taken knowingly.
"""

import logging

import pytest

from planner.repository.audit import JournalBackend, resolve_journal
from planner.repository.journal import Journal as FileJournal
from planner.repository.markdown import MarkdownNoteRepository


class TestPortConformance:
    def test_the_file_journal_satisfies_the_port(self, tmp_path):
        assert isinstance(FileJournal(tmp_path), JournalBackend)

    @pytest.mark.parametrize("method", [
        "begin", "record", "commit", "rollback", "recover", "has_pending"])
    def test_the_port_declares_the_whole_surface(self, method):
        assert hasattr(JournalBackend, method)

    def test_the_postgres_journal_satisfies_the_port(self, postgresql_dsn, tmp_path):
        from planner.repository.postgres_journal import PostgresJournal
        assert isinstance(PostgresJournal(tmp_path, postgresql_dsn), JournalBackend)


class TestSelection:
    def test_no_dsn_means_the_file_journal(self, tmp_path):
        """The default. A vault on a laptop needs no server."""
        assert isinstance(resolve_journal(tmp_path, None), FileJournal)

    def test_an_empty_dsn_is_treated_as_no_dsn(self, tmp_path):
        assert isinstance(resolve_journal(tmp_path, ""), FileJournal)

    def test_a_reachable_dsn_means_postgres(self, tmp_path, postgresql_dsn):
        from planner.repository.postgres_journal import PostgresJournal
        assert isinstance(resolve_journal(tmp_path, postgresql_dsn), PostgresJournal)


class TestDegradation:
    def test_an_unreachable_database_falls_back(self, tmp_path):
        journal = resolve_journal(tmp_path, "postgresql://nobody@127.0.0.1:1/none")
        assert isinstance(journal, FileJournal)

    def test_the_fallback_is_announced_not_silent(self, tmp_path, caplog):
        """A silent downgrade is how you discover months later that the audit log has
        a hole in it."""
        with caplog.at_level(logging.WARNING, logger="planner.repository"):
            resolve_journal(tmp_path, "postgresql://nobody@127.0.0.1:1/none")
        assert "postgres journal unavailable" in caplog.text
        assert "audit log" in caplog.text

    def test_a_caller_can_observe_the_degradation(self, tmp_path):
        seen = []
        resolve_journal(tmp_path, "postgresql://nobody@127.0.0.1:1/none",
                        on_degrade=seen.append)
        assert len(seen) == 1

    def test_writes_still_work_after_degrading(self, tmp_path):
        """The whole point of the rule."""
        from planner.domain.note import Note
        for folder in ("Items", "Docs", "Meetings", "Reviews", "Journal"):
            (tmp_path / folder).mkdir()
        repo = MarkdownNoteRepository(tmp_path, dsn="postgresql://nobody@127.0.0.1:1/x")
        repo.save(Note(kind="task", title="Written anyway"))
        assert repo.exists("Written anyway")

    def test_crash_recovery_still_works_after_degrading(self, tmp_path):
        """Degrading costs history, not safety."""
        from planner.repository.journal import Entry, digest
        for folder in ("Items", "Docs", "Meetings", "Reviews", "Journal"):
            (tmp_path / folder).mkdir()
        repo = MarkdownNoteRepository(tmp_path, dsn="postgresql://nobody@127.0.0.1:1/x")
        (tmp_path / "Items" / "T.md").write_text("ours")
        repo.journal.record(Entry("Items/T.md", digest(b"original"), digest(b"ours"),
                                  "original"))
        assert MarkdownNoteRepository(tmp_path).recover().restored == ["Items/T.md"]
