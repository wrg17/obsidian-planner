import os
from datetime import date

import pytest

from planner import MarkdownNoteRepository, NoteService
from planner.repository import CONTENT_FOLDERS


@pytest.fixture
def repo(tmp_path):
    """An empty vault with the folder layout the real one has."""
    for folder in CONTENT_FOLDERS:
        (tmp_path / folder).mkdir()
    return MarkdownNoteRepository(tmp_path)


@pytest.fixture
def vault(repo):
    """The service, which is what callers actually use. Named `vault` because that is
    what the tests read as: the thing you do planner things to."""
    return NoteService(repo)


@pytest.fixture
def populated(vault):
    """A small hierarchy: area -> project -> epic -> task -> subtask, plus a routine.

    Deliberately built through the API rather than written as fixture text, so the
    tests exercise creation as well as the thing under test.
    """
    vault.create(kind="area", title="Studio")
    vault.create(kind="project", title="Website relaunch", area="Studio", priority=2)
    vault.create(kind="epic", title="Design system", parent="Website relaunch",
                 project="Website relaunch", type="feature", status="doing")
    vault.create(kind="task", title="Pick a type scale", parent="Design system",
                 project="Website relaunch", type="feature", priority=1,
                 due=date(2026, 8, 24), status="doing")
    vault.create(kind="subtask", title="Test at 320px", parent="Pick a type scale",
                 project="Website relaunch", type="feature")
    vault.create(kind="routine", title="Inbox to zero", recur="weekdays",
                 area="Studio", last_done=date(2026, 8, 21))
    return vault


@pytest.fixture
def client(populated, monkeypatch):
    from fastapi.testclient import TestClient
    from planner.api import app

    monkeypatch.setenv("PLANNER_VAULT", str(populated.repo.root))
    with TestClient(app) as c:
        yield c
