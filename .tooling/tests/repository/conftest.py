"""A real Postgres instance for the audit-log tests.

Spun up per session by pytest-postgresql rather than mocked: the point of these tests
is the SQL, and a fake connection would only prove the fake agrees with itself.
"""

import pytest
from pytest_postgresql import factories

postgresql_proc = factories.postgresql_proc(port=None)
postgresql_db = factories.postgresql("postgresql_proc")


@pytest.fixture
def postgresql_dsn(postgresql_db):
    info = postgresql_db.info
    return (f"postgresql://{info.user}@{info.host}:{info.port}/{info.dbname}")


@pytest.fixture
def pg_journal(postgresql_dsn, tmp_path):
    from planner.repository.postgres_journal import PostgresJournal
    journal = PostgresJournal(tmp_path, postgresql_dsn)
    yield journal
    journal.close()
