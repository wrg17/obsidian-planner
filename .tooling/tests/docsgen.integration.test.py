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
            f"stale: {docsgen.stale()}; run `python -m planner.docsgen --write`"
        )

    @pytest.mark.parametrize("name", docsgen.FILES)
    def test_the_file_exists_where_the_generator_looks(self, name):
        assert (docsgen.REPO / name).is_file()

    @pytest.mark.parametrize("name,template", docsgen.TEMPLATES.items())
    def test_each_template_and_its_output_exist(self, name, template):
        assert (docsgen.REPO / template).is_file()
        assert (docsgen.REPO / name).is_file()

    def test_rendering_is_idempotent(self):
        """Otherwise --check would report drift immediately after --write."""
        for name in docsgen.FILES:
            text = (docsgen.REPO / name).read_text()
            assert docsgen.render(docsgen.render(text)) == docsgen.render(text)


class TestMarkers:
    def test_every_marker_in_the_docs_has_a_generator(self):
        """A typo'd marker would silently never be filled in."""
        sources = list(docsgen.FILES) + list(docsgen.TEMPLATES.values())
        for name in sources:
            text = (docsgen.REPO / name).read_text()
            for found in re.findall(r"<!-- generated:([\w-]+) -->", text):
                assert found in docsgen.SECTIONS, f"{name}: no generator for {found!r}"

    def test_every_generator_is_used_somewhere(self):
        """A generator nothing references is dead code pretending to be
        documentation.
        """
        sources = list(docsgen.FILES) + list(docsgen.TEMPLATES.values())
        combined = "".join((docsgen.REPO / n).read_text() for n in sources)
        for name in docsgen.SECTIONS:
            assert (
                f"<!-- generated:{name} -->" in combined
                or f"%%generated:{name}%%" in combined
            ), name

    def test_an_unknown_marker_is_an_error_not_a_silent_skip(self):
        with pytest.raises(KeyError):
            docsgen.render("<!-- generated:invented -->\n<!-- /generated:invented -->")

    def test_prose_around_a_marker_survives(self):
        text = (
            "Before.\n\n<!-- generated:endpoints -->\nstale\n"
            "<!-- /generated:endpoints -->\n\nAfter.\n"
        )
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
        from planner.api.routes import Route
        from planner.contracts.operations import OPERATIONS, Operation

        before = docsgen.endpoints()
        key = ("GET", "/invented")
        OPERATIONS[key] = Operation(summary="Invented", guidance="For the test.")
        try:
            docsgen.ROUTES = (*ROUTES, Route(*key, lambda: None, ("meta",)))
            assert docsgen.endpoints() != before
            assert "/invented" in docsgen.endpoints()
        finally:
            docsgen.ROUTES = ROUTES
            del OPERATIONS[key]


class TestWhatIsNotGenerated:
    def test_most_of_the_prose_is_still_hand_written(self):
        """Generating explanation would be worse than duplicating it."""
        template = (docsgen.REPO / docsgen.TEMPLATES["README.md"]).read_text()
        generated = sum(len(m.group()) for m in docsgen.MARKER.finditer(template))
        assert generated < len(template) * 0.3

    def test_hand_written_counts_are_gone(self):
        """A test count in prose is a number someone has to maintain and nobody
        benefits from; it was wrong within a day of being written.
        """
        readme = (docsgen.REPO / "README.md").read_text()
        assert not re.search(r"\b\d{3} tests\b", readme)


class TestTheWriter:
    """Exercised against a temporary directory: a test for the writer that wrote to the
    real README would edit the repository every time the suite ran.
    """

    @pytest.fixture
    def fake_repo(self, tmp_path):
        """A miniature of the real layout: an in-place file with markers, and a
        template whose output carries none.
        """
        (tmp_path / "System.md").write_text(
            "Kept.\n\n%%generated:vocabularies%%\nout of date\n"
            "%%/generated:vocabularies%%\n\nAlso kept.\n"
        )
        template = tmp_path / docsgen.TEMPLATES["README.md"]
        template.parent.mkdir(parents=True)
        template.write_text(
            "<!-- editor note -->\n\nIntro.\n\n<!-- generated:endpoints -->\n"
            "<!-- /generated:endpoints -->\n\nOutro.\n"
        )
        return tmp_path

    def test_it_reports_both_kinds_of_staleness(self, fake_repo):
        assert set(docsgen.stale(fake_repo)) == {"System.md", "README.md"}

    def test_it_rewrites_them(self, fake_repo):
        assert set(docsgen.write(fake_repo)) == {"System.md", "README.md"}
        assert docsgen.stale(fake_repo) == []

    def test_prose_around_an_in_place_section_is_untouched(self, fake_repo):
        docsgen.write(fake_repo)
        text = (fake_repo / "System.md").read_text()
        assert text.startswith("Kept.") and text.rstrip().endswith("Also kept.")
        assert "out of date" not in text

    def test_a_rendered_file_keeps_its_prose_and_loses_its_plumbing(self, fake_repo):
        docsgen.write(fake_repo)
        text = (fake_repo / "README.md").read_text()
        assert text.startswith("Intro.") and text.rstrip().endswith("Outro.")
        assert "generated:" not in text and "editor note" not in text

    def test_writing_twice_changes_nothing_the_second_time(self, fake_repo):
        docsgen.write(fake_repo)
        assert docsgen.write(fake_repo) == []

    def test_a_missing_file_is_skipped_not_an_error(self, tmp_path):
        """System.md may legitimately be absent from a checkout that only wants the
        package.
        """
        assert docsgen.stale(tmp_path) == []
        assert docsgen.write(tmp_path) == []

    def test_a_file_with_no_markers_is_left_alone(self, tmp_path):
        (tmp_path / "README.md").write_text("Just prose.\n")
        assert docsgen.write(tmp_path) == []
        assert (tmp_path / "README.md").read_text() == "Just prose.\n"


class TestNothingLeaksIntoObsidian:
    """Both docs sit inside the vault, so anything Obsidian does not recognise as a
    comment is visible in Live Preview. That is how `<!-- generated:layers -->` ended up
    on screen in the manual.
    """

    def test_the_readme_carries_no_markers_at_all(self):
        """It is rendered whole from a template, so the reader never sees plumbing."""
        text = (docsgen.REPO / "README.md").read_text()
        assert "generated:" not in text

    def test_the_template_header_does_not_reach_the_output(self):
        """The template opens with a note to whoever edits it; that is about the
        template, not part of the document.
        """
        template = (docsgen.REPO / docsgen.TEMPLATES["README.md"]).read_text()
        assert template.lstrip().startswith("<!--")
        assert not (docsgen.REPO / "README.md").read_text().lstrip().startswith("<!--")

    def test_system_md_uses_obsidian_comment_syntax(self):
        """`%%` is Obsidian's comment token -- confirmed in its own markdown token
        table. HTML comments are not, and show as literal text.
        """
        text = (docsgen.REPO / "System.md").read_text()
        assert "%%generated:" in text
        assert "<!-- generated:" not in text

    def test_no_html_comments_anywhere_in_the_vault_docs(self):
        for name in ("README.md", "System.md"):
            assert "<!--" not in (docsgen.REPO / name).read_text(), name

    def test_the_template_lives_outside_the_vault(self):
        """Dot-prefixed, so Obsidian never indexes the file that does carry markers."""
        assert str(docsgen.TEMPLATES["README.md"]).startswith(".tooling")


class TestGeneratedMarkdownActuallyRenders:
    """A generated block is markdown, and markdown is whitespace-sensitive. A table
    written directly beneath its marker is folded into the preceding paragraph and
    renders as literal pipes -- which is exactly what happened in System.md.
    """

    def test_a_kept_marker_is_separated_from_its_content_by_a_blank_line(self):
        rendered = docsgen.render(
            "Prose.\n\n%%generated:kinds%%\n%%/generated:kinds%%\n"
        )
        lines = rendered.splitlines()
        opening = lines.index("%%generated:kinds%%")
        assert lines[opening + 1] == "", "no blank line after the opening marker"
        closing = lines.index("%%/generated:kinds%%")
        assert lines[closing - 1] == "", "no blank line before the closing marker"

    @pytest.mark.parametrize("name", ["kinds", "vocabularies", "endpoints"])
    def test_every_table_section_starts_a_block(self, name):
        """Each of these renders a table, so each needs the separation."""
        assert docsgen.SECTIONS[name]().startswith("|")

    def test_the_tables_in_the_docs_have_a_blank_line_above_them(self):
        """The property as it exists on disk, not merely in the renderer."""
        for filename in ("System.md", "README.md"):
            lines = (docsgen.REPO / filename).read_text().splitlines()
            for index, line in enumerate(lines):
                if (
                    line.startswith("|")
                    and index
                    and not lines[index - 1].startswith("|")
                ):
                    assert lines[index - 1].strip() == "", (
                        f"{filename}:{index + 1} table has no blank line above it"
                    )

    def test_rendering_stays_idempotent_with_the_padding(self):
        """The padding must not accumulate on repeated writes."""
        once = docsgen.render("%%generated:kinds%%\n%%/generated:kinds%%\n")
        assert docsgen.render(once) == once
