"""Architectural invariants.

Layering only holds if something checks it. These are cheap and catch the drift that
code review misses -- a controller reaching past the service into the repository, or a
domain rule quietly importing FastAPI.
"""

import ast
import pathlib
from contextlib import contextmanager

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "planner"

#: layer -> what it may import from. Nothing may import a layer above it.
ALLOWED = {
    "domain": set(),
    "repository": {"domain"},
    "service": {"domain", "repository"},
    "api": {"domain", "repository", "service"},
    "mcp": {"domain", "repository", "service"},
}


def imports_in(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module, node.level
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, 0


def layer_of(path):
    rel = path.relative_to(SRC)
    return rel.parts[0] if len(rel.parts) > 1 else None


ALL_MODULES = [p for p in SRC.rglob("*.py") if "__pycache__" not in str(p)]


@pytest.mark.parametrize("path", ALL_MODULES, ids=lambda p: str(p.relative_to(SRC)))
def test_layer_does_not_import_upward(path):
    layer = layer_of(path)
    if layer is None:
        return                      # planner/__init__.py wires everything together
    for module, level in imports_in(path):
        if level == 0 and not module.startswith("planner"):
            continue
        head = module.lstrip(".").split(".")[0]
        if head in ALLOWED and head != layer:
            assert head in ALLOWED[layer], \
                f"{path.relative_to(SRC)} ({layer}) must not import {head}"


@pytest.mark.parametrize("path", [p for p in ALL_MODULES if layer_of(p) == "domain"],
                         ids=lambda p: str(p.relative_to(SRC)))
def test_domain_is_framework_free(path):
    """The domain must stay importable without FastAPI, pydantic or the MCP SDK --
    that is what lets three transports share one definition of a task."""
    banned = {"fastapi", "pydantic", "starlette", "mcp", "uvicorn"}
    for module, _ in imports_in(path):
        assert module.split(".")[0] not in banned, f"{path.name} imports {module}"


def test_domain_does_no_file_io():
    """Persistence belongs to the repository. A domain that opens files cannot be
    tested without a disk, and cannot be reused over a different store."""
    for path in [p for p in ALL_MODULES if layer_of(p) == "domain"]:
        for module, _ in imports_in(path):
            assert module.split(".")[0] not in {"pathlib", "os", "shutil"}, \
                f"{path.name} imports {module}"


def test_controllers_do_not_touch_the_repository():
    """Routers depend on the service. Reaching past it is how a rule ends up enforced
    on one transport and not the other."""
    for path in (SRC / "api" / "handlers").glob("*.py"):
        for module, _ in imports_in(path):
            assert "repository" not in module, \
                f"{path.name} imports {module}; go through NoteService"


def test_both_transports_share_one_service():
    """The guarantee that REST and MCP cannot drift apart."""
    from planner.api.dependencies import build_service
    from planner.mcp.server import build_service
    from planner.service.notes import NoteService

    assert isinstance(build_service(), NoteService)
    assert isinstance(build_service("."), NoteService)


def test_repository_is_swappable():
    """The service must work against any object satisfying the port, not just the
    markdown one -- which is also what makes it testable without a filesystem."""
    from planner.domain.note import Note
    from planner.repository.base import NoteRepository
    from planner.service.notes import NoteService

    class InMemory:
        def __init__(self):
            self.saved = {}

        def describe(self, summary="", actor="", request_id=""):
            pass

        def has_pending_transaction(self):
            return False

        @contextmanager
        def unit_of_work(self):
            saved = dict(self.saved)
            try:
                yield self
            except BaseException:
                self.saved = saved
                raise

        def get(self, title):
            from planner.domain.errors import NoteNotFound
            if title not in self.saved:
                raise NoteNotFound(title)
            return self.saved[title]

        def exists(self, title):
            return title in self.saved

        def titles(self):
            return list(self.saved)

        def iter_all(self):
            return list(self.saved.values())

        def iter_raw(self):
            return [(t, n.to_markdown()) for t, n in self.saved.items()]

        def save(self, note):
            self.saved[note.title] = note
            return note

        def delete(self, title):
            del self.saved[title]

    repo = InMemory()
    assert isinstance(repo, NoteRepository)
    service = NoteService(repo)
    service.create(kind="task", title="In memory")
    assert service.get("In memory").fields["status"] == "todo"
    assert service.close("In memory").fields["done"] is True


def test_every_source_module_has_a_matching_test_file():
    """The naming convention, enforced.

    src/planner/domain/note.py must be covered by
    tests/domain/note.integration.test.py. A new module with no test file fails here
    rather than quietly lowering the coverage number.
    """
    src = pathlib.Path(__file__).resolve().parent.parent / "src" / "planner"
    tests = pathlib.Path(__file__).resolve().parent
    missing = []
    for module in sorted(src.rglob("*.py")):
        if "__pycache__" in str(module) or module.name in ("__init__.py", "__main__.py"):
            continue
        rel = module.relative_to(src)
        expected = tests / rel.parent / f"{module.stem}.integration.test.py"
        if not expected.exists():
            missing.append(str(rel))
    assert not missing, f"no test file for: {missing}"


def test_test_files_follow_the_naming_convention():
    tests = pathlib.Path(__file__).resolve().parent
    for path in tests.rglob("*.py"):
        if "__pycache__" in str(path) or path.name == "conftest.py":
            continue
        assert path.name.endswith(".integration.test.py"), \
            f"{path.name} does not follow <module>.integration.test.py"
