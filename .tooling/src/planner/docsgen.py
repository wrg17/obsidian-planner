"""Render the parts of the prose docs that restate code.

    python -m planner.docsgen --check     # fail if the files are stale
    python -m planner.docsgen --write     # bring them up to date

Not everything in README.md and System.md should be generated -- most of both is
explanation, which is the part worth writing by hand. What is generated is the part
that is a *second copy*: the endpoint table, the layer diagram, the vocabularies.

The audit that prompted this found all three had already drifted. README listed seven
endpoints when routes.py declared twelve, and claimed 664 tests when there were 847.
Neither was neglect: they were edited by hand every time the code changed, and hand
editing is exactly the process that loses.

Both files live inside the vault, which constrains how the sections can be delimited --
Obsidian shows anything it does not recognise as a comment, and it recognises `%%`, not
HTML. So the two are handled differently, according to who reads them:

    System.md      edited in place, markers written as %%generated:name%%
                   It is a note. Someone reads and edits it inside Obsidian, so it has
                   to stay directly editable, and `%%` is invisible there.

    README.md      generated whole from .tooling/docs/README.template.md
                   It is a repository document that happens to sit in the vault. The
                   template carries the markers and lives outside the vault; the file
                   Obsidian sees is finished output with no markers in it at all.
                   Edit the template, not the README.

The first attempt put HTML comments in both, and they showed up as literal text in
Obsidian's Live Preview -- in the manual, which is the one file guaranteed to be read
in the app.

A test runs --check, so a stale file fails the suite rather than being noticed by a
reader who then believes it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from .api.routes import ROUTES
from .domain import schema as S

REPO = Path(__file__).resolve().parents[3]

#: HTML comments for files read on GitHub, `%%` for files read in Obsidian. The body is
#: allowed to be empty -- which it is the first time a marker is added, and a pattern
#: requiring content there would silently never fill it in.
STYLES = {
    "html": ("<!-- generated:{name} -->", "<!-- /generated:{name} -->"),
    "obsidian": ("%%generated:{name}%%", "%%/generated:{name}%%"),
}

MARKER = re.compile(
    r"(?:<!-- generated:(?P<html>[\w-]+) -->.*?<!-- /generated:(?P=html) -->)"
    r"|(?:%%generated:(?P<obs>[\w-]+)%%.*?%%/generated:(?P=obs)%%)",
    re.S,
)


# --- the generated sections ---------------------------------------------------------


def endpoints() -> str:
    """The routing table, as the README's API reference.

    Grouped by tag rather than listed in declaration order, because a reader wants
    "what can I do with a note" and the file wants "what order do these register in".
    """
    lines = ["| | |", "|---|---|"]
    for tag in ("notes", "hierarchy", "tickets", "meta"):
        for route in ROUTES:
            if tag in route.tags:
                path = route.path.replace("{title}", "{title}")
                lines.append(f"| `{route.method} {path}` | {route.summary} |")
    return "\n".join(lines)


def layers() -> str:
    """The package layout, read off the filesystem rather than remembered."""
    described = {
        "domain": "entities, vocabularies, validation — no IO, no framework",
        "repository": "persistence port, markdown adapter, reversible commands, "
        "unit of work, journals",
        "service": "business rules, transport-agnostic",
        "contracts": "wire shapes shared by every transport",
        "api": "FastAPI: routes, middleware, controllers, DTOs",
        "mcp": "MCP tools over the same service",
    }
    src = REPO / ".tooling" / "src" / "planner"
    present = [
        d.name for d in sorted(src.iterdir()) if d.is_dir() and d.name in described
    ]
    width = max(len(name) for name in present) + 2
    body = "\n".join(f"{name + '/':<{width}} {described[name]}" for name in present)
    return "```\n" + body + "\n```"


def vocabularies() -> str:
    """The value sets, straight from the module that enforces them."""
    rows = [
        ("Ticket status", S.TICKET_STATUS),
        ("Container status", S.CONTAINER_STATUS),
        ("Routine status", S.ROUTINE_STATUS),
        ("Doc status", S.DOC_STATUS),
        ("Decision status", S.DECISION_STATUS),
        ("Issue type", S.ISSUE_TYPE),
        ("Recurrence", S.RECUR),
    ]
    lines = ["| | |", "|---|---|"]
    lines += [
        f"| **{name}** | {' · '.join(f'`{v}`' for v in values)} |"
        for name, values in rows
    ]
    low, high = S.PRIORITY_RANGE
    lines.append(
        f"| **Priority** | `{low}` (highest) … `{high}` — a number, so it "
        f"sorts correctly |"
    )
    return "\n".join(lines)


def kinds() -> str:
    """Each note type, its folder, and the fields it may carry."""
    lines = ["| Kind | Folder | Own fields |", "|---|---|---|"]
    for kind in S.KINDS.values():
        own = [f for f in S.allowed_fields(kind.name) if f not in S.SHARED]
        lines.append(
            f"| `{kind.name}` | `{kind.folder}/` | "
            + (", ".join(f"`{f}`" for f in own) or "—")
            + " |"
        )
    return "\n".join(lines)


SECTIONS = {
    "endpoints": endpoints,
    "layers": layers,
    "vocabularies": vocabularies,
    "kinds": kinds,
}

#: Edited in place: the markers stay in the file.
FILES = ("System.md",)

#: Rendered whole from a template outside the vault. The output carries no markers,
#: because it is read in Obsidian and anything that is not a `%%` comment is visible.
TEMPLATES = {"README.md": Path(".tooling") / "docs" / "README.template.md"}

#: A template may open with a comment addressed to whoever edits it. That is a note
#: about the template, not part of the document, so it is dropped on render.
TEMPLATE_HEADER = re.compile(r"\A<!--.*?-->\s*", re.S)


def render_template(text: str) -> str:
    """Render a template whole, dropping its markers and its editor note."""
    return render(TEMPLATE_HEADER.sub("", text), keep_markers=False)


# --- rendering ----------------------------------------------------------------------


def render(text: str, *, keep_markers: bool = True) -> str:
    """Replace every delimited section, leaving the prose around it alone.

    `keep_markers=False` drops the delimiters from the output, for a file rendered
    whole from a template -- the reader of that file never edits it, so a marker would
    be noise, and in Obsidian it would be *visible* noise.
    """

    def substitute(match):
        style = "html" if match.group("html") else "obsidian"
        name = match.group("html") or match.group("obs")
        if name not in SECTIONS:
            raise KeyError(f"no generator named {name!r}")
        if not keep_markers:
            return SECTIONS[name]()
        opening, closing = STYLES[style]
        # Blank lines on both sides, not just newlines. A markdown table has to be
        # preceded by one or the parser folds it into the previous paragraph and
        # renders it as literal pipes -- which is what happened when the marker sat
        # directly above the table in System.md.
        return (
            opening.format(name=name)
            + "\n\n"
            + SECTIONS[name]()
            + "\n\n"
            + closing.format(name=name)
        )

    return MARKER.sub(substitute, text)


def stale(root: Path | None = None) -> list[str]:
    """Files whose generated sections no longer match the code.

    `root` is injectable so this can be exercised against a temporary directory --
    a test for the writer that wrote to the real README would be a test that edits the
    repository every time it runs.
    """
    root = root or REPO
    out = []
    for name in FILES:
        path = root / name
        if not path.exists():
            continue  # a file may legitimately not carry any markers
        current = path.read_text()
        if render(current) != current:
            out.append(name)
    for name, template in TEMPLATES.items():
        source, target = root / template, root / name
        if not source.exists():
            continue
        expected = render_template(source.read_text())
        if not target.exists() or target.read_text() != expected:
            out.append(name)
    return out


def write(root: Path | None = None) -> list[str]:
    """Bring the generated sections up to date. Returns the files changed."""
    root = root or REPO
    changed = []
    for name in FILES:
        path = root / name
        if not path.exists():
            continue
        current = path.read_text()
        updated = render(current)
        if updated != current:
            path.write_text(updated)
            changed.append(name)
    for name, template in TEMPLATES.items():
        source, target = root / template, root / name
        if not source.exists():
            continue
        expected = render_template(source.read_text())
        if not target.exists() or target.read_text() != expected:
            target.write_text(expected)
            changed.append(name)
    return changed


def main(argv=None) -> int:  # pragma: no cover - exercised through the functions above
    """Command line entry point: --check to verify, --write to regenerate."""
    argv = argv if argv is not None else sys.argv[1:]
    if "--write" in argv:
        changed = write()
        print("updated:", ", ".join(changed) if changed else "nothing to do")
        return 0
    out_of_date = stale()
    if out_of_date:
        print("stale, run --write:", ", ".join(out_of_date))
        return 1
    print("docs are current")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
