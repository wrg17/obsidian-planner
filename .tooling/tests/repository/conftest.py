"""A Postgres instance for the audit-log tests.

Real Postgres, never a fake: these tests are about the SQL, and a fake connection would
only prove the fake agrees with itself.

It comes from Docker. `make test` starts the compose `db` service and points
PLANNER_TEST_DSN at it, so nothing has to be installed on the machine -- which is the
whole reason the database is a compose service rather than something you set up once and
forget how.

pytest-postgresql can also spawn its own server from local binaries, and that path is
kept for anyone who happens to have them. It is a fallback, not the intended route: it
needs initdb and pg_ctl on PATH, and requiring those is exactly the local dependency
this arrangement exists to avoid.
"""

import os
import shutil
from urllib.parse import urlparse

import pytest
from pytest_postgresql import factories

EXTERNAL_DSN = os.environ.get("PLANNER_TEST_DSN")

if EXTERNAL_DSN:
    _url = urlparse(EXTERNAL_DSN)
    postgresql_proc = factories.postgresql_noproc(
        host=_url.hostname,
        port=_url.port,
        user=_url.username,
        password=_url.password,
        dbname=(_url.path.lstrip("/") or "planner"),
    )
elif shutil.which("initdb"):
    postgresql_proc = factories.postgresql_proc(port=None)
else:

    @pytest.fixture(scope="session")
    def postgresql_proc():
        """Neither route is available, so say which one to take.

        Without this the failure is a stack trace from inside pytest-postgresql about a
        missing executable, which tells you what broke and not what to do.
        """
        pytest.skip(
            "no database for the audit-log tests: run `make test`, which starts the "
            "compose db and sets PLANNER_TEST_DSN. (Set it yourself to point at any "
            "Postgres, or install the postgres binaries to have one spawned.)"
        )


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
