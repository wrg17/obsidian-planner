"""The CI step that guards the notes themselves.

Every other test builds its own fixtures, so a schema change that invalidates notes
already committed to the vault passes the entire suite and breaks the product. This
script is the only check that reads the real thing -- which makes it worth testing.
"""

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_vault.py"
    spec = importlib.util.spec_from_file_location("_check_vault", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_check_vault"] = module
    spec.loader.exec_module(module)
    return module


class TestExitCode:
    def test_a_clean_vault_passes(self, script, vault, capsys):
        assert script.main([str(vault.repo.root)]) == 0

    def test_a_vault_with_a_bad_note_fails(self, script, vault):
        (vault.repo.root / "Items" / "Bad.md").write_text(
            "---\nkind: task\nstatus: not-a-status\n---\n"
        )
        assert script.main([str(vault.repo.root)]) == 1

    def test_the_real_vault_is_valid(self, script, capsys):
        """The one committed here. If this fails, the repo ships a broken example."""
        root = Path(__file__).resolve().parents[3]
        assert script.main([str(root)]) == 0


class TestOutput:
    def test_it_names_the_note_and_the_reason(self, script, vault, capsys):
        (vault.repo.root / "Items" / "Bad.md").write_text(
            "---\nkind: task\nstatus: not-a-status\n---\n"
        )
        script.main([str(vault.repo.root)])
        out = capsys.readouterr().out
        assert "Bad" in out
        assert "not-a-status" in out

    def test_it_annotates_when_running_in_actions(
        self, script, vault, capsys, monkeypatch
    ):
        """::error:: puts the failure on the pull request rather than in a log nobody
        opens.
        """
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        (vault.repo.root / "Items" / "Bad.md").write_text(
            "---\nkind: task\nstatus: not-a-status\n---\n"
        )
        script.main([str(vault.repo.root)])
        assert "::error::" in capsys.readouterr().out

    def test_it_does_not_annotate_locally(self, script, vault, capsys, monkeypatch):
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        (vault.repo.root / "Items" / "Bad.md").write_text(
            "---\nkind: task\nstatus: not-a-status\n---\n"
        )
        script.main([str(vault.repo.root)])
        assert "::error::" not in capsys.readouterr().out
