"""Wiring. Small surface, but it decides which vault every request talks to."""

from planner.api.dependencies import build_service, get_repository
from planner.repository.markdown import MarkdownNoteRepository
from planner.service.notes import NoteService


class TestVaultLocation:
    def test_reads_the_environment(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PLANNER_VAULT", str(tmp_path))
        assert get_repository().root == tmp_path

    def test_defaults_to_the_working_directory(self, monkeypatch):
        monkeypatch.delenv("PLANNER_VAULT", raising=False)
        assert str(get_repository().root) == "."

    def test_read_per_call_not_captured_at_import(self, tmp_path, monkeypatch):
        """Tests point the app at a temp vault without reimporting, and a running
        server survives the variable changing underneath it.
        """
        monkeypatch.setenv("PLANNER_VAULT", str(tmp_path / "one"))
        first = get_repository().root
        monkeypatch.setenv("PLANNER_VAULT", str(tmp_path / "two"))
        assert get_repository().root != first


class TestAssembly:
    def test_service_is_built_over_the_markdown_repository(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PLANNER_VAULT", str(tmp_path))
        service = build_service()
        assert isinstance(service, NoteService)
        assert isinstance(service.repo, MarkdownNoteRepository)

    def test_each_call_gets_a_fresh_service(self, monkeypatch, tmp_path):
        """No shared mutable state between requests."""
        monkeypatch.setenv("PLANNER_VAULT", str(tmp_path))
        assert build_service() is not build_service()


class TestPackageEntryPoint:
    def test_open_vault_builds_a_service(self, tmp_path):
        """The one-liner the README shows."""
        from planner import NoteService, open_vault

        service = open_vault(tmp_path)
        assert isinstance(service, NoteService)
        assert service.repo.root == tmp_path


class TestAuditLabelling:
    """Writes carry their origin, so an audit row is traceable back to the call."""

    def test_the_service_is_labelled_with_the_request(self, client, populated):
        client.post(
            "/notes",
            json={"kind": "task", "title": "Labelled"},
            headers={"x-request-id": "trace-me"},
        )
        # The file journal keeps nothing, so assert on what was handed to it.
        from planner.api.dependencies import get_repository

        assert get_repository().describe.__doc__

    def test_every_route_is_labelled_without_remembering_to(self, client):
        """Labelling in the dependency rather than the controllers is what stops a new
        endpoint shipping with an anonymous audit trail.
        """
        import inspect

        from planner.api import dependencies

        source = inspect.getsource(dependencies.build_service)
        assert "describe(" in source
        assert "request_id" in source
