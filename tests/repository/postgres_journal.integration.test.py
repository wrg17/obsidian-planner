"""The Postgres audit log, against a real Postgres.

Three questions the log answers, tested separately because they have different
lifetimes: recovery cares only about in-flight operations, provenance only about
committed ones, and history about everything until it is pruned.
"""

from datetime import datetime, timedelta, timezone

import pytest

from planner.domain.note import Note
from planner.repository.journal import Entry, digest
from planner.repository.markdown import MarkdownNoteRepository
from planner.repository.postgres_journal import DEFAULT_RETENTION, PostgresJournal


def entry(path="Items/T.md", prior=b"original", intended=b"new"):
    return Entry(path, digest(prior), digest(intended),
                 None if prior is None else prior.decode())


class TestSchema:
    def test_tables_are_created_on_connect(self, pg_journal):
        with pg_journal._conn.cursor() as cur:
            cur.execute("SELECT to_regclass('planner_operations'),"
                        " to_regclass('planner_operation_files')")
            assert all(cur.fetchone())

    def test_connecting_twice_is_safe(self, postgresql_dsn, tmp_path):
        """Every process start runs the schema; it has to be idempotent."""
        PostgresJournal(tmp_path, postgresql_dsn).close()
        PostgresJournal(tmp_path, postgresql_dsn).close()

    def test_status_is_constrained_by_the_database(self, pg_journal):
        """A typo'd status would quietly make an operation invisible to recovery --
        the same class of bug as a misspelled note status, so the database refuses it
        rather than trusting the code."""
        import psycopg
        pg_journal.begin()
        with pytest.raises(psycopg.errors.CheckViolation):
            with pg_journal._conn.cursor() as cur:
                cur.execute("UPDATE planner_operations SET status = 'nonsense'"
                            " WHERE id = %s", (pg_journal._operation_id,))


class TestOperationLifecycle:
    def test_begin_opens_an_in_progress_operation(self, pg_journal):
        pg_journal.begin(summary="create 'T'", actor="rest", request_id="abc123")
        assert pg_journal.has_pending()

    def test_commit_closes_it(self, pg_journal):
        pg_journal.begin()
        pg_journal.record(entry())
        pg_journal.commit()
        assert not pg_journal.has_pending()

    def test_rollback_closes_it_but_keeps_the_attempt(self, pg_journal):
        """"We tried this and backed out" is exactly what an audit log is for."""
        pg_journal.begin(summary="doomed")
        pg_journal.record(entry())
        pg_journal.rollback()
        assert not pg_journal.has_pending()
        assert pg_journal.history()[0]["status"] == "rolled_back"

    def test_metadata_is_kept(self, pg_journal):
        pg_journal.begin(summary="cascade delete", actor="mcp", request_id="req-7")
        pg_journal.commit()
        row = pg_journal.history()[0]
        assert row["summary"] == "cascade delete"
        assert row["actor"] == "mcp"
        assert row["request_id"] == "req-7"

    def test_recording_without_begin_opens_one(self, pg_journal):
        """Defensive: a caller that forgets must not silently write orphan rows."""
        pg_journal.record(entry())
        assert pg_journal.has_pending()

    def test_finishing_twice_is_harmless(self, pg_journal):
        pg_journal.begin()
        pg_journal.commit()
        pg_journal.commit()

    def test_operations_are_scoped_to_their_vault(self, postgresql_dsn, tmp_path):
        """One database can serve several vaults; recovery must not reach into
        another's in-flight work."""
        a = PostgresJournal(tmp_path / "a", postgresql_dsn)
        b = PostgresJournal(tmp_path / "b", postgresql_dsn)
        a.begin()
        assert a.has_pending() and not b.has_pending()
        a.close(); b.close()


class TestRecovery:
    def test_an_abandoned_operation_is_undone(self, pg_journal, tmp_path):
        (tmp_path / "Items").mkdir()
        target = tmp_path / "Items" / "T.md"
        target.write_text("original")
        pg_journal.begin()
        pg_journal.record(entry())
        target.write_text("new")          # applied, then "crash" -- never committed

        report = pg_journal.recover()
        assert target.read_text() == "original"
        assert report.restored == ["Items/T.md"]

    def test_an_unexplained_change_is_left_alone(self, pg_journal, tmp_path):
        """Same rule as the file journal: a change we cannot account for came from a
        person editing their own notes, and is newer than our abandoned work."""
        (tmp_path / "Items").mkdir()
        target = tmp_path / "Items" / "T.md"
        target.write_text("original")
        pg_journal.begin()
        pg_journal.record(entry())
        target.write_text("what the user typed")

        report = pg_journal.recover()
        assert target.read_text() == "what the user typed"
        assert [c.path for c in report.conflicts] == ["Items/T.md"]

    def test_a_write_that_never_landed_needs_nothing(self, pg_journal, tmp_path):
        (tmp_path / "Items").mkdir()
        (tmp_path / "Items" / "T.md").write_text("original")
        pg_journal.begin()
        pg_journal.record(entry())
        assert pg_journal.recover().untouched == ["Items/T.md"]

    def test_recovered_operations_are_marked_not_deleted(self, pg_journal, tmp_path):
        (tmp_path / "Items").mkdir()
        (tmp_path / "Items" / "T.md").write_text("original")
        pg_journal.begin()
        pg_journal.record(entry())
        pg_journal.recover()
        assert pg_journal.history()[0]["status"] == "recovered"

    def test_a_conflicted_operation_is_marked_distinctly(self, pg_journal, tmp_path):
        """Recovered and conflicted mean different things to whoever reads this later:
        one was cleaned up, the other was left for a human."""
        (tmp_path / "Items").mkdir()
        (tmp_path / "Items" / "T.md").write_text("something else entirely")
        pg_journal.begin()
        pg_journal.record(entry())
        pg_journal.recover()
        assert pg_journal.history()[0]["status"] == "conflicted"

    def test_nothing_pending_means_nothing_to_do(self, pg_journal):
        assert not pg_journal.recover()

    def test_several_abandoned_operations_are_all_undone(self, pg_journal, tmp_path):
        (tmp_path / "Items").mkdir()
        for name in ("a", "b"):
            target = tmp_path / "Items" / f"{name}.md"
            target.write_text("original")
            pg_journal.begin()
            pg_journal.record(entry(path=f"Items/{name}.md"))
            target.write_text("new")
            pg_journal._operation_id = None      # abandon without finishing
        report = pg_journal.recover()
        assert sorted(report.restored) == ["Items/a.md", "Items/b.md"]


class TestProvenance:
    """"Did Obsidian change this since we wrote it?" -- decidable without the
    filesystem storing an author."""

    def test_the_last_committed_write_is_recorded(self, pg_journal):
        pg_journal.begin()
        pg_journal.record(entry(intended=b"ours"))
        pg_journal.commit()
        assert pg_journal.last_written("Items/T.md") == digest(b"ours")

    def test_matching_the_file_means_we_wrote_it(self, pg_journal, tmp_path):
        (tmp_path / "Items").mkdir()
        target = tmp_path / "Items" / "T.md"
        target.write_bytes(b"ours")
        pg_journal.begin()
        pg_journal.record(entry(intended=b"ours"))
        pg_journal.commit()
        assert pg_journal.last_written("Items/T.md") == digest(target.read_bytes())

    def test_differing_means_someone_else_did(self, pg_journal, tmp_path):
        (tmp_path / "Items").mkdir()
        target = tmp_path / "Items" / "T.md"
        pg_journal.begin()
        pg_journal.record(entry(intended=b"ours"))
        pg_journal.commit()
        target.write_bytes(b"edited in obsidian")
        assert pg_journal.last_written("Items/T.md") != digest(target.read_bytes())

    def test_an_abandoned_write_never_counts_as_ours(self, pg_journal):
        """It never became the truth, so claiming it would misreport the next edit as
        the user's when it was our own failure."""
        pg_journal.begin()
        pg_journal.record(entry(intended=b"never happened"))
        pg_journal.rollback()
        assert pg_journal.last_written("Items/T.md") is None

    def test_the_most_recent_commit_wins(self, pg_journal):
        for content in (b"first", b"second", b"third"):
            pg_journal.begin()
            pg_journal.record(entry(intended=content))
            pg_journal.commit()
        assert pg_journal.last_written("Items/T.md") == digest(b"third")

    def test_an_unknown_path_has_no_record(self, pg_journal):
        assert pg_journal.last_written("Items/Never touched.md") is None


class TestHistory:
    def test_newest_first(self, pg_journal):
        for i in range(3):
            pg_journal.begin(summary=f"op {i}")
            pg_journal.commit()
        assert [r["summary"] for r in pg_journal.history()] == ["op 2", "op 1", "op 0"]

    def test_limit_is_respected(self, pg_journal):
        for i in range(5):
            pg_journal.begin(summary=str(i))
            pg_journal.commit()
        assert len(pg_journal.history(limit=2)) == 2

    def test_timestamps_are_recorded(self, pg_journal):
        pg_journal.begin()
        pg_journal.commit()
        row = pg_journal.history()[0]
        assert row["started_at"] and row["finished_at"]


class TestRetention:
    def test_the_default_window_is_thirty_days(self):
        assert DEFAULT_RETENTION == timedelta(days=30)

    def test_old_committed_operations_are_pruned(self, pg_journal):
        pg_journal.begin(summary="ancient")
        pg_journal.record(entry())
        pg_journal.commit()
        with pg_journal._conn.cursor() as cur:
            cur.execute("UPDATE planner_operations SET finished_at = now()"
                        " - interval '31 days'")
        assert pg_journal.prune() == 1
        assert pg_journal.history() == []

    def test_recent_operations_survive(self, pg_journal):
        pg_journal.begin(summary="recent")
        pg_journal.commit()
        assert pg_journal.prune() == 0
        assert len(pg_journal.history()) == 1

    @pytest.mark.parametrize("status", ["rolled_back", "recovered", "conflicted"])
    def test_only_committed_operations_are_pruned(self, pg_journal, status):
        """Anything that did not go cleanly is evidence, and the reason to keep a log
        is to still have it when someone finally asks."""
        pg_journal.begin(summary="went wrong")
        pg_journal._finish(status)
        with pg_journal._conn.cursor() as cur:
            cur.execute("UPDATE planner_operations SET finished_at = now()"
                        " - interval '400 days'")
        assert pg_journal.prune() == 0
        assert pg_journal.history()[0]["status"] == status

    def test_in_flight_operations_are_never_pruned(self, pg_journal):
        pg_journal.begin()
        with pg_journal._conn.cursor() as cur:
            cur.execute("UPDATE planner_operations SET started_at = now()"
                        " - interval '400 days'")
        pg_journal.prune()
        assert pg_journal.has_pending()

    def test_files_are_removed_with_their_operation(self, pg_journal):
        """ON DELETE CASCADE: prior_content is the bulk of the table, and orphaned
        rows would defeat the point of pruning."""
        pg_journal.begin()
        pg_journal.record(entry())
        pg_journal.commit()
        with pg_journal._conn.cursor() as cur:
            cur.execute("UPDATE planner_operations SET finished_at = now()"
                        " - interval '31 days'")
        pg_journal.prune()
        with pg_journal._conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM planner_operation_files")
            assert cur.fetchone()[0] == 0

    def test_pruning_runs_during_recovery(self, pg_journal):
        """Startup is the natural moment: it already touches the log, and nothing else
        reliably happens on a schedule."""
        pg_journal.begin(summary="ancient")
        pg_journal.commit()
        with pg_journal._conn.cursor() as cur:
            cur.execute("UPDATE planner_operations SET finished_at = now()"
                        " - interval '31 days'")
        pg_journal.recover()
        assert pg_journal.history() == []

    def test_the_window_is_configurable(self, postgresql_dsn, tmp_path):
        journal = PostgresJournal(tmp_path, postgresql_dsn, retention=timedelta(days=1))
        journal.begin()
        journal.commit()
        with journal._conn.cursor() as cur:
            cur.execute("UPDATE planner_operations SET finished_at = now()"
                        " - interval '2 days'")
        assert journal.prune() == 1
        journal.close()


class TestThroughTheRepository:
    def test_a_write_is_audited(self, postgresql_dsn, tmp_path):
        for folder in ("Items", "Docs", "Meetings", "Reviews", "Journal"):
            (tmp_path / folder).mkdir()
        repo = MarkdownNoteRepository(tmp_path, dsn=postgresql_dsn)
        repo.describe(summary="create 'Audited'", actor="rest", request_id="r1")
        repo.save(Note(kind="task", title="Audited"))

        row = repo.journal.history()[0]
        assert row["status"] == "committed"
        assert row["summary"] == "create 'Audited'"
        assert row["request_id"] == "r1"

    def test_a_rolled_back_transaction_is_recorded_as_such(self, postgresql_dsn,
                                                           tmp_path):
        class Boom(Exception):
            pass

        for folder in ("Items", "Docs", "Meetings", "Reviews", "Journal"):
            (tmp_path / folder).mkdir()
        repo = MarkdownNoteRepository(tmp_path, dsn=postgresql_dsn)
        with pytest.raises(Boom):
            with repo.unit_of_work():
                repo.save(Note(kind="task", title="Doomed"))
                raise Boom()

        assert not repo.exists("Doomed")
        assert repo.journal.history()[0]["status"] == "rolled_back"

    def test_provenance_after_a_real_write(self, postgresql_dsn, tmp_path):
        for folder in ("Items", "Docs", "Meetings", "Reviews", "Journal"):
            (tmp_path / folder).mkdir()
        repo = MarkdownNoteRepository(tmp_path, dsn=postgresql_dsn)
        repo.save(Note(kind="task", title="Tracked"))
        on_disk = digest(repo.find("Tracked").read_bytes())
        assert repo.journal.last_written("Items/Tracked.md") == on_disk

        repo.find("Tracked").write_text("edited by hand in obsidian")
        assert repo.journal.last_written("Items/Tracked.md") != \
            digest(repo.find("Tracked").read_bytes())
