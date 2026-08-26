"""Generated documentation.

The point of this file is the first test: prose that restates code must be checked
against it, or it drifts. When this was written README listed seven endpoints against
twelve in the routing table, and claimed 664 tests against 847. Both had been edited by
hand on every change; hand editing is the process that loses.
"""

import re

import pytest

from planner import docsgen
from planner.api.routes import ROUTES
from planner.domain import schema as S


class TestTheDocsAreCurrent:
    def test_no_generated_section_is_stale(self):
        """Run `python -m planner.docsgen --write` from .tooling/ to fix."""
        assert docsgen.stale() == [], (
            f"stale generated sections in {docsgen.stale()}; "
            "run `python -m planner.docsgen --write`")

    @pytest.mark.parametrize("name", docsgen.FILES)
    def test_the_file_exists_where_the_generator_looks(self, name):
        assert (docsgen.REPO / name).is_file()

    def test_rendering_is_idempotent(self):
        """Otherwise --check would report drift immediately after --write."""
        for name in docsgen.FILES:
            text = (docsgen.REPO / name).read_text()
            assert docsgen.render(docsgen.render(text)) == docsgen.render(text)


class TestMarkers:
    def test_every_marker_in_the_docs_has_a_generator(self):
        """A typo'd marker would silently never be filled in."""
        for name in docsgen.FILES:
            text = (docsgen.REPO / name).read_text()
            for found in re.findall(r"<!-- generated:([\w-]+) -->", text):
                assert found in docsgen.SECTIONS, f"{name}: no generator for {found!r}"

    def test_every_generator_is_used_somewhere(self):
        """A generator nothing references is dead code pretending to be documentation."""
        combined = "".join((docsgen.REPO / n).read_text() for n in docsgen.FILES)
        for name in docsgen.SECTIONS:
            assert f"<!-- generated:{name} -->" in combined

    def test_an_unknown_marker_is_an_error_not_a_silent_skip(self):
        with pytest.raises(KeyError):
            docsgen.render("<!-- generated:invented -->\n<!-- /generated:invented -->")

    def test_prose_around_a_marker_survives(self):
        text = ("Before.\n\n<!-- generated:endpoints -->\nstale\n"
                "<!-- /generated:endpoints -->\n\nAfter.\n")
        out = docsgen.render(text)
        assert out.startswith("Before.") and out.endswith("After.\n")
        assert "stale" not in out


class TestTheSectionsMatchTheCode:
    def test_endpoints_lists_every_route(self):
        table = docsgen.endpoints()
        for route in ROUTES:
            assert f"`{route.method} {route.path}`" in table

    def test_endpoints_lists_nothing_extra(self):
        rows = re.findall(r"\| `(\w+ [^`]+)`", docsgen.endpoints())
        assert len(rows) == len(ROUTES)

    def test_vocabularies_carry_every_value(self):
        table = docsgen.vocabularies()
        for vocabulary in (S.TICKET_STATUS, S.ISSUE_TYPE, S.RECUR, S.DOC_STATUS):
            for value in vocabulary:
                assert f"`{value}`" in table

    def test_kinds_lists_every_kind_with_its_folder(self):
        table = docsgen.kinds()
        for kind in S.KINDS.values():
            assert f"`{kind.name}`" in table
            assert f"`{kind.folder}/`" in table

    def test_layers_reflects_the_packages_on_disk(self):
        diagram = docsgen.layers()
        src = docsgen.REPO / ".tooling" / "src" / "planner"
        for package in ("domain", "repository", "service", "contracts", "api", "mcp"):
            assert (src / package).is_dir()
            assert f"{package}/" in diagram

    def test_adding_a_route_would_change_the_output(self):
        """The property that makes generating worth it: the table cannot lag."""
        before = docsgen.endpoints()
        from planner.api.routes import Route
        ROUTES_PATCHED = ROUTES + (Route("GET", "/invented", lambda: None,
                                         ("meta",), "Invented"),)
        try:
            docsgen.ROUTES = ROUTES_PATCHED
            assert docsgen.endpoints() != before
            assert "/invented" in docsgen.endpoints()
        finally:
            docsgen.ROUTES = ROUTES


class TestWhatIsNotGenerated:
    def test_hand_written_counts_are_gone(self):
        """A test count in prose is a number someone has to maintain and nobody
        benefits from; it was wrong within a day of being written."""
        readme = (docsgen.REPO / "README.md").read_text()
        assert not re.search(r"\b\d{3} tests\b", readme)

    def test_most_of_the_prose_is_still_hand_written(self):
        """Generating explanation would be worse than duplicating it. Only the parts
        that are a second copy of code are generated."""
        readme = (docsgen.REPO / "README.md").read_text()
        generated = sum(len(m.group()) for m in docsgen.MARKER.finditer(readme))
        assert generated < len(readme) * 0.3


class TestTheWriter:
    """Exercised against a temporary directory: a test for the writer that wrote to the
    real README would edit the repository every time the suite ran."""

    @pytest.fixture
    def fake_repo(self, tmp_path):
        (tmp_path / "README.md").write_text(
            "Kept.\n\n<!-- generated:endpoints -->\nout of date\n"
            "<!-- /generated:endpoints -->\n\nAlso kept.\n")
        return tmp_path

    def test_it_reports_stale_files(self, fake_repo):
        assert docsgen.stale(fake_repo) == ["README.md"]

    def test_it_rewrites_them(self, fake_repo):
        assert docsgen.write(fake_repo) == ["README.md"]
        assert docsgen.stale(fake_repo) == []

    def test_the_surrounding_prose_is_untouched(self, fake_repo):
        docsgen.write(fake_repo)
        text = (fake_repo / "README.md").read_text()
        assert text.startswith("Kept.") and text.rstrip().endswith("Also kept.")
        assert "out of date" not in text

    def test_writing_twice_changes_nothing_the_second_time(self, fake_repo):
        docsgen.write(fake_repo)
        assert docsgen.write(fake_repo) == []

    def test_a_missing_file_is_skipped_not_an_error(self, tmp_path):
        """System.md may legitimately be absent from a checkout that only wants the
        package."""
        assert docsgen.stale(tmp_path) == []
        assert docsgen.write(tmp_path) == []

    def test_a_file_with_no_markers_is_left_alone(self, tmp_path):
        (tmp_path / "README.md").write_text("Just prose.\n")
        assert docsgen.write(tmp_path) == []
        assert (tmp_path / "README.md").read_text() == "Just prose.\n"
