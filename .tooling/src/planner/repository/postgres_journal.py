"""An append-only audit log in Postgres, doubling as the crash-recovery journal.

Same decision table as the file journal -- see journal.py, which is the canonical
explanation of why recovery compares hashes rather than trusting provenance. What this
adds is retention: operations are kept after they finish, with their outcome, so the
log answers three questions at once.

    RECOVERY    which operations were in flight when we died, and what did they
                intend? (status = 'in_progress')
    PROVENANCE  what did *we* last write to this path? Compare `intended_hash` of the
                latest committed operation against the file: equal means ours, different
                means Obsidian's. This is the "who changed it" question made decidable
                without needing provenance the filesystem does not store.
    HISTORY     what changed, when, and at whose request -- and `prior_content` makes
                an undo stack possible rather than merely an audit trail.

WHAT POSTGRES DOES NOT BUY

A database transaction covers rows, not files. `COMMIT` is a promise about this log; it
cannot roll back a write to the vault, and there is no two-phase commit available
because the filesystem cannot prepare. The commit-record window documented in
journal.py is therefore unchanged -- it sits between the file write and the commit
record, wherever that record lives.

What Postgres genuinely improves is the durability of the record itself: its WAL has had
far more scrutiny than a hand-rolled write-temp-fsync-rename ever will.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from .journal import Conflict, Entry, RecoveryReport, digest

log = logging.getLogger("planner.repository")

#: Committed operations older than this are pruned. `prior_content` means the table
#: grows with the volume of text edited, not merely the number of operations, so
#: unbounded retention would eventually cost more than the history is worth.
DEFAULT_RETENTION = timedelta(days=30)

SCHEMA = """
CREATE TABLE IF NOT EXISTS planner_operations (
    id           bigserial PRIMARY KEY,
    vault        text        NOT NULL,
    status       text        NOT NULL,
    summary      text        NOT NULL DEFAULT '',
    actor        text        NOT NULL DEFAULT '',
    request_id   text        NOT NULL DEFAULT '',
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    CONSTRAINT planner_operations_status_check
        CHECK (status IN ('in_progress','committed','rolled_back','recovered','conflicted'))
);

CREATE TABLE IF NOT EXISTS planner_operation_files (
    id            bigserial PRIMARY KEY,
    operation_id  bigint NOT NULL REFERENCES planner_operations(id) ON DELETE CASCADE,
    path          text   NOT NULL,
    prior_hash    text,
    intended_hash text,
    prior_content text
);

-- Recovery reads only in-flight rows, and does so on every startup.
CREATE INDEX IF NOT EXISTS planner_operations_pending
    ON planner_operations (vault) WHERE status = 'in_progress';

-- Provenance asks "what did we last write to this path", which is a lookup by path
-- ordered by recency.
CREATE INDEX IF NOT EXISTS planner_operation_files_path
    ON planner_operation_files (path, operation_id DESC);

CREATE INDEX IF NOT EXISTS planner_operations_finished
    ON planner_operations (finished_at) WHERE finished_at IS NOT NULL;
"""


class PostgresJournal:
    def __init__(self, root, dsn: str, retention: timedelta = DEFAULT_RETENTION):
        self.root = Path(root)
        self.dsn = dsn
        self.retention = retention
        # Connect eagerly: resolve_journal treats a failure here as "degrade to the
        # file journal", and that decision has to be made before the first write, not
        # discovered halfway through one.
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._operation_id: int | None = None
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # --- recording ----------------------------------------------------------------

    def begin(self, summary: str = "", actor: str = "", request_id: str = "") -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO planner_operations (vault, status, summary, actor,"
                " request_id) VALUES (%s, 'in_progress', %s, %s, %s) RETURNING id",
                (str(self.root), summary, actor, request_id))
            self._operation_id = cur.fetchone()[0]

    def record(self, entry: Entry) -> None:
        """Durably record one file's before-and-after, before that change is applied.

        Autocommit means this row is on disk when the statement returns, which is the
        whole point -- an entry that is still buffered when the process dies records
        nothing.
        """
        if self._operation_id is None:
            self.begin()
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO planner_operation_files (operation_id, path, prior_hash,"
                " intended_hash, prior_content) VALUES (%s, %s, %s, %s, %s)",
                (self._operation_id, entry.path, entry.prior_hash,
                 entry.intended_hash, entry.prior_content))

    def commit(self) -> None:
        self._finish("committed")

    def rollback(self) -> None:
        """Mark abandoned. The caller has already undone the work in memory, so there
        is nothing for recovery to do -- but the attempt is kept, because "we tried
        this and backed out" is exactly the kind of thing an audit log exists for."""
        self._finish("rolled_back")

    def _finish(self, status: str) -> None:
        if self._operation_id is None:
            return
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE planner_operations SET status = %s, finished_at = now()"
                " WHERE id = %s", (status, self._operation_id))
        self._operation_id = None

    def conflicted(self, paths) -> None:
        """Record that the rollback could not complete.

        Kept forever -- `prune` never touches a conflicted row. A vault left in a
        mixed state is exactly the thing someone will ask about months later.
        """
        if self._operation_id is None:
            return
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE planner_operations SET status = 'conflicted',"
                " finished_at = now(), summary = summary || %s WHERE id = %s",
                (f" [not restored: {', '.join(paths)}]", self._operation_id))
        self._operation_id = None

    def has_pending(self) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM planner_operations WHERE vault = %s"
                " AND status = 'in_progress' LIMIT 1", (str(self.root),))
            return cur.fetchone() is not None

    # --- recovery -----------------------------------------------------------------

    def recover(self) -> RecoveryReport:
        """Undo every operation left in flight, newest first.

        Newest first for the same reason the in-memory rollback reverses: a later
        operation may have built on an earlier one, and undoing forwards can leave the
        earlier undo with nothing to restore.
        """
        report = RecoveryReport()
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM planner_operations WHERE vault = %s"
                " AND status = 'in_progress' ORDER BY id DESC", (str(self.root),))
            operation_ids = [row[0] for row in cur.fetchall()]

        for operation_id in operation_ids:
            self._recover_one(operation_id, report)
        self.prune()
        return report

    def _recover_one(self, operation_id: int, report: RecoveryReport) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT path, prior_hash, intended_hash, prior_content"
                " FROM planner_operation_files WHERE operation_id = %s"
                " ORDER BY id DESC", (operation_id,))
            rows = cur.fetchall()

        had_conflict = False
        for path, prior_hash, intended_hash, prior_content in rows:
            entry = Entry(path, prior_hash, intended_hash, prior_content)
            target = self.root / path
            current = target.read_bytes() if target.is_file() else None
            current_hash = digest(current)

            if current_hash == entry.prior_hash:
                report.untouched.append(path)
            elif current_hash == entry.intended_hash:
                from .journal import Journal
                Journal._restore(target, entry)
                report.restored.append(path)
            else:
                report.conflicts.append(Conflict(path))
                had_conflict = True

        self._mark(operation_id, "conflicted" if had_conflict else "recovered")

    def _mark(self, operation_id: int, status: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE planner_operations SET status = %s, finished_at = now()"
                " WHERE id = %s", (status, operation_id))

    # --- history ------------------------------------------------------------------

    def last_written(self, path: str) -> str | None:
        """The hash this journal last committed for `path`, or None.

        Compare it with the file to answer "has Obsidian touched this since we wrote
        it" -- equal means the file is still ours, different means it is not. Only
        committed operations count: an abandoned one never became the truth.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT f.intended_hash FROM planner_operation_files f"
                " JOIN planner_operations o ON o.id = f.operation_id"
                " WHERE f.path = %s AND o.vault = %s AND o.status = 'committed'"
                " ORDER BY f.operation_id DESC, f.id DESC LIMIT 1",
                (path, str(self.root)))
            row = cur.fetchone()
            return row[0] if row else None

    def history(self, limit: int = 50) -> list[dict]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, status, summary, actor, request_id, started_at,"
                " finished_at FROM planner_operations WHERE vault = %s"
                " ORDER BY id DESC LIMIT %s", (str(self.root), limit))
            columns = [c.name for c in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    # --- retention ----------------------------------------------------------------

    def prune(self, now: datetime | None = None) -> int:
        """Drop committed operations past the retention window.

        Only `committed` ones. An operation that was rolled back, recovered or left
        conflicted is evidence about something that went wrong, and the whole reason to
        keep a log is to still have it when someone finally asks. Files cascade with
        their operation.
        """
        cutoff = (now or datetime.now(timezone.utc)) - self.retention
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM planner_operations WHERE vault = %s"
                " AND status = 'committed' AND finished_at < %s",
                (str(self.root), cutoff))
            return cur.rowcount
