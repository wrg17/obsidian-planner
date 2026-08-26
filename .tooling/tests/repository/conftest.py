"""A Postgres instance for the audit-log tests.

Two ways in, because the suite has to run in two places:

    locally      pytest-postgresql starts a throwaway server using the postgres
                 binaries on the machine, and tears it down afterwards
    in a container
                 there are no server binaries in a slim python image, so
                 PLANNER_TEST_DSN points at the one compose already runs

Real Postgres either way. These tests are about the SQL, and a fake connection would
only prove the fake agrees with itself.
"""

import os

import pytest
from pytest_postgresql import factories

EXTERNAL_DSN = os.environ.get("PLANNER_TEST_DSN")

if EXTERNAL_DSN:
    from urllib.parse import urlparse

    _url = urlparse(EXTERNAL_DSN)
    postgresql_proc = factories.postgresql_noproc(
        host=_url.hostname, port=_url.port,
        user=_url.username, password=_url.password,
        dbname=(_url.path.lstrip("/") or "planner"),
    )
else:
    postgresql_proc = factories.postgresql_proc(port=None)

postgresql_db = factories.postgresql("postgresql_proc")


@pytest.fixture
def postgresql_dsn(postgresql_db):
    info = postgresql_db.info
    password = f":{info.password}" if getattr(info, "password", None) else ""
    return f"postgresql://{info.user}{password}@{info.host}:{info.port}/{info.dbname}"


@pytest.fixture
def pg_journal(postgresql_dsn, tmp_path):
    from planner.repository.postgres_journal import PostgresJournal

    journal = PostgresJournal(tmp_path, postgresql_dsn)
    yield journal
    journal.close()
