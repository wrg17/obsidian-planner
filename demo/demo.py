#!/usr/bin/env python3
"""Load or clear a throwaway demo dataset.

    python3 demo/demo.py load     # write ~22 notes into Items/, Docs/, ...
    python3 demo/demo.py clear    # delete exactly those files again

The point is that empty views are indistinguishable from broken ones. This fills
every view in the vault -- all seven statuses, all five issue types, priorities 1-4,
a blocked task, an overdue routine, a closed subtask -- so you can see the thing
working before you trust it with real work.

Dates are computed relative to today, so the board always looks alive: something is
due today, something is overdue, something closed last week. Nothing here is tracked
by git; `clear` removes it and leaves a clean tree.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
TODAY = date.today()


def d(offset):
    """A date `offset` days from today, as YYYY-MM-DD."""
    return (TODAY + timedelta(days=offset)).isoformat()


def this_week(day):
    """`day` days after Monday of the current ISO week, never in the future.

    Closed dates have to land inside the current ISO week or the weekly review --
    which pins to its own week rather than a rolling window -- renders empty, and an
    empty view is indistinguishable from a broken one. Clamping to today keeps the
    dates from running ahead when the demo is loaded early in the week.
    """
    monday = TODAY - timedelta(days=TODAY.weekday())
    return min(monday + timedelta(days=day), TODAY).isoformat()


# Icon and colour per kind, matching Templates/.
STYLE = {
    "area":     ("LiLandPlot",        "#8B5CF6"),
    "project":  ("LiFolderKanban",    "#3B82F6"),
    "epic":     ("LiLayers2",         "#14B8A6"),
    "task":     ("LiSquareCheck",     "#D9A21B"),
    "subtask":  ("LiCornerDownRight", "#B4762A"),
    "routine":  ("LiRepeat1",         "#10B981"),
    "doc":      ("LiFileText",        "#64748B"),
    "decision": ("LiGitBranch",       "#EC4899"),
    "meeting":  ("LiUsers2",          "#06B6D4"),
    "review":   ("LiCalendarCheck",   "#6366F1"),
}


def epic_block():
    return """```base
newItemFolder: Items
formulas:
  done_num: 'if(done || status == "done", 1, 0)'
views:
  - type: table
    name: Tasks
    filters:
      and:
        - 'kind == "task"'
        - 'parent == this'
    order:
      - file.name
      - done
      - note.status
      - note.type
      - note.priority
      - note.due
      - formula.done_num
    sort:
      - property: note.priority
        direction: ASC
    summaries:
      formula.done_num: Sum
      note.status: Filled
```"""


def task_block():
    return """```base
newItemFolder: Items
views:
  - type: table
    name: Subtasks
    filters:
      and:
        - 'kind == "subtask"'
        - 'parent == this'
    order:
      - file.name
      - done
      - note.status
      - note.priority
      - note.due
    sort:
      - property: note.priority
        direction: ASC
```"""


def project_blocks():
    return """## Epics

```base
newItemFolder: Items
views:
  - type: table
    name: Epics
    filters:
      and:
        - 'kind == "epic"'
        - 'parent == this'
    order:
      - file.name
      - done
      - note.status
      - note.priority
      - note.due
```

## All work

```base
newItemFolder: Items
formulas:
  done_num: 'if(done || status == "done", 1, 0)'
views:
  - type: table
    name: All work
    filters:
      and:
        - 'project == this'
        - 'kind == "epic" || kind == "task" || kind == "subtask"'
    groupBy:
      property: note.parent
      direction: ASC
    order:
      - file.name
      - note.kind
      - done
      - note.status
      - note.priority
      - note.due
      - formula.done_num
    summaries:
      formula.done_num: Sum
      note.status: Filled
```"""


def review_block(name, date_filter, order, sort_by, direction):
    """A weekly-review view pinned to the note's own week rather than a rolling window."""
    cols = "\n".join(f"      - {c}" for c in order)
    return f"""```base
newItemFolder: Items
formulas:
  wk: 'if(this.week, this.week, this.file.basename)'
  done_num: 'if(done || status == "done", 1, 0)'
views:
  - type: table
    name: {name}
    filters:
      and:
        - '{date_filter}'
    order:
{cols}
    sort:
      - property: {sort_by}
        direction: {direction}
    summaries:
      formula.done_num: Sum
```"""


def area_block():
    return """```base
newItemFolder: Items
views:
  - type: table
    name: Projects
    filters:
      and:
        - 'kind == "project"'
        - 'area == this'
    order:
      - file.name
      - note.status
      - note.priority
      - note.due
  - type: table
    name: Routines
    filters:
      and:
        - 'kind == "routine"'
        - 'area == this'
    order:
      - file.name
      - note.recur
      - note.last_done
```"""


# (folder, title, frontmatter fields, body)
NOTES = [
    # ---- areas -------------------------------------------------------------
    ("Items", "Studio", {"kind": "area", "status": "active"},
     "Creative and client work. Areas never finish; projects inside them do.\n\n"
     "## Projects and routines\n\n" + area_block()),

    ("Items", "Household", {"kind": "area", "status": "active"},
     "Anything to do with the flat.\n\n## Projects and routines\n\n" + area_block()),

    # ---- projects ----------------------------------------------------------
    ("Items", "Website relaunch", {
        "kind": "project", "status": "active", "area": "[[Studio]]",
        "priority": 2, "due": d(45)},
     "## Goal\n\nNew site live, old posts migrated, nothing 404ing.\n\n" + project_blocks()),

    ("Items", "Kitchen refit", {
        "kind": "project", "status": "active", "area": "[[Household]]",
        "priority": 1, "due": d(21)},
     "## Goal\n\nWorktop replaced and the alcove shelved out.\n\n" + project_blocks()),

    # ---- epics -------------------------------------------------------------
    ("Items", "Design system", {
        "kind": "epic", "status": "doing", "done": False, "type": "feature",
        "parent": "[[Website relaunch]]", "project": "[[Website relaunch]]",
        "priority": 2, "due": d(30)},
     "## Scope\n\nType, colour and the component set. Not page layouts.\n\n"
     "## Done when\n\n- Every component has one documented state\n\n## Tasks\n\n" + epic_block()),

    ("Items", "Content migration", {
        "kind": "epic", "status": "backlog", "done": False, "type": "chore",
        "parent": "[[Website relaunch]]", "project": "[[Website relaunch]]",
        "priority": 3},
     "## Scope\n\nMoving old posts across with redirects intact.\n\n## Tasks\n\n" + epic_block()),

    # ---- tasks: Design system ---------------------------------------------
    ("Items", "Pick a type scale", {
        "kind": "task", "status": "doing", "done": False, "type": "feature",
        "parent": "[[Design system]]", "project": "[[Website relaunch]]",
        "priority": 1, "due": d(0), "scheduled": d(0)},
     "Due **today**, so it shows up in Today and in today's daily note.\n\n"
     "## Subtasks\n\n" + task_block()),

    ("Items", "Audit existing components", {
        "kind": "task", "status": "todo", "done": False, "type": "spike",
        "parent": "[[Design system]]", "project": "[[Website relaunch]]",
        "priority": 2, "due": d(5)},
     "Timeboxed look at what already exists before deciding what to keep.\n\n"
     "## Subtasks\n\n" + task_block()),

    ("Items", "Fix button contrast", {
        "kind": "task", "status": "backlog", "done": False, "type": "bug",
        "parent": "[[Design system]]", "project": "[[Website relaunch]]",
        "priority": 2},
     "Fails contrast against the accent background. The only `bug` in the demo, so "
     "**Board -> Bugs** shows exactly this.\n\n## Subtasks\n\n" + task_block()),

    ("Items", "Rebuild the footer", {
        "kind": "task", "status": "cancelled", "done": False, "type": "feature",
        "parent": "[[Design system]]", "project": "[[Website relaunch]]",
        "priority": 4, "closed": this_week(1)},
     "Dropped from scope. Cancelled work leaves the board without being deleted.\n"),

    # ---- subtasks ----------------------------------------------------------
    ("Items", "Collect reference sites", {
        "kind": "subtask", "status": "doing", "done": False, "type": "research",
        "parent": "[[Pick a type scale]]", "project": "[[Website relaunch]]",
        "priority": 2, "due": d(1), "created": this_week(0)},
     "Ten sites whose typography holds up on a phone.\n"),

    ("Items", "Test at 320px", {
        "kind": "subtask", "status": "done", "done": True, "type": "feature",
        "parent": "[[Pick a type scale]]", "project": "[[Website relaunch]]",
        "priority": 1, "due": this_week(0), "closed": this_week(0)},
     "Closed inside the current ISO week, so it counts toward the `Sum` in the parent's "
     "group header and shows up in this week's review.\n"),

    # ---- tasks: Content migration -----------------------------------------
    ("Items", "Export old posts", {
        "kind": "task", "status": "blocked", "done": False, "type": "chore",
        "parent": "[[Content migration]]", "project": "[[Website relaunch]]",
        "priority": 3, "due": d(10), "blocked_by": ["[[Pick a type scale]]"]},
     "Blocked, with `blocked_by` pointing at the thing in the way.\n\n"
     "## Subtasks\n\n" + task_block()),

    ("Items", "Proofread the about page", {
        "kind": "task", "status": "review", "done": False, "type": "chore",
        "parent": "[[Content migration]]", "project": "[[Website relaunch]]",
        "priority": 2, "due": d(3), "created": this_week(0)},
     "In review -- written, not yet signed off.\n\n## Subtasks\n\n" + task_block()),

    # ---- tasks: Kitchen refit ---------------------------------------------
    ("Items", "Measure the alcove", {
        "kind": "task", "status": "todo", "done": False, "type": "chore",
        "parent": "[[Kitchen refit]]", "project": "[[Kitchen refit]]",
        "priority": 1, "due": d(2), "scheduled": d(2), "created": this_week(0)},
     "## Subtasks\n\n" + task_block()),

    ("Items", "Compare worktop quotes", {
        "kind": "task", "status": "backlog", "done": False, "type": "research",
        "parent": "[[Kitchen refit]]", "project": "[[Kitchen refit]]",
        "priority": 3},
     "No date and no priority pressure -- sits in Backlog until it earns one.\n\n"
     "## Subtasks\n\n" + task_block()),

    ("Items", "Cancel the old delivery slot", {
        "kind": "task", "status": "todo", "done": False, "type": "chore",
        "parent": "[[Kitchen refit]]", "project": "[[Kitchen refit]]",
        "priority": 2, "due": d(-6)},
     "Deliberately **overdue**, so Today -> Overdue and the daily note's "
     "*Carried over* section both have something in them.\n",),

    # ---- routines ----------------------------------------------------------
    ("Items", "Morning review", {
        "kind": "routine", "status": "active", "recur": "daily",
        "area": "[[Studio]]", "last_done": d(-1)},
     "Open Today, pick the one thing that matters. Check off by setting `last_done` "
     "to today.\n"),

    ("Items", "Inbox to zero", {
        "kind": "routine", "status": "active", "recur": "weekdays",
        "area": "[[Studio]]", "last_done": d(-1)},
     "`weekdays`, so it hides itself on Saturday and Sunday.\n"),

    ("Items", "Pay bills", {
        "kind": "routine", "status": "active", "recur": "monthly",
        "area": "[[Household]]", "last_done": d(-38)},
     "Monthly and **overdue by about a week** -- the thing a plain checkbox can "
     "never tell you.\n"),

    # ---- docs / decisions / meetings / reviews -----------------------------
    ("Docs", "Design system principles", {
        "kind": "doc", "status": "current", "project": "[[Website relaunch]]"},
     "## Summary\n\nOne scale, one accent, no exceptions without a decision record.\n\n"
     "## Detail\n\nType scale is a 1.25 ratio from 16px.\n\n## Open questions\n\n- Dark mode?\n"),

    ("Docs", "Worktop options", {
        "kind": "doc", "status": "draft", "project": "[[Kitchen refit]]"},
     "## Summary\n\nLaminate, solid oak, or composite.\n\n## Detail\n\nOak needs oiling "
     "twice a year.\n\n## Open questions\n\n- Does the sink cutout change the price?\n"),

    ("Docs", "Use system fonts", {
        "kind": "decision", "status": "accepted", "date": d(-7),
        "project": "[[Website relaunch]]", "supersedes": []},
     "## Context\n\nWebfonts were costing about 400ms on first paint.\n\n"
     "## Options\n\n1. Keep the webfont\n2. System font stack\n3. Subset the webfont\n\n"
     "## Decision\n\nSystem font stack.\n\n## Consequences\n\nFaster, slightly less "
     "distinctive. Revisit if branding objects.\n"),

    ("Meetings", f"{d(-5)} Website kickoff", {
        "kind": "meeting", "date": d(-5), "project": "[[Website relaunch]]",
        "attendees": []},
     "## Agenda\n\n- Scope\n- Timeline\n\n## Notes\n\nAgreed to cut the blog redesign "
     "from phase one.\n\n## Actions\n\nAction items become real tickets here:\n\n"
     "```base\nnewItemFolder: Items\nviews:\n  - type: table\n    name: Actions\n"
     "    filters:\n      and:\n        - 'kind == \"task\"'\n        - 'parent == this'\n"
     "    order:\n      - file.name\n      - done\n      - note.status\n      - note.due\n```\n"),
]


def frontmatter(fields, kind):
    icon, colour = STYLE[kind]
    lines = ["---", f"kind: {kind}", f"icon: {icon}", f'iconColor: "{colour}"']
    for key, value in fields.items():
        if key in ("kind", "created"):
            continue
        if isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                lines.extend(f'  - "{v}"' for v in value)
        elif isinstance(value, str) and value.startswith("[["):
            lines.append(f'{key}: "{value}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append(f"created: {fields.get('created', d(-30))}")
    lines.append("---")
    return "\n".join(lines)


def paths():
    for folder, title, fields, _ in NOTES:
        yield VAULT / folder / f"{title}.md"
    yield VAULT / "Reviews" / f"{TODAY.strftime('%G-W%V')}.md"


def load():
    written = 0
    for folder, title, fields, body in NOTES:
        kind = fields["kind"]
        target = VAULT / folder / f"{title}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"{frontmatter(fields, kind)}\n\n# {title}\n\n{body}\n", encoding="utf-8"
        )
        written += 1

    review = VAULT / "Reviews" / f"{TODAY.strftime('%G-W%V')}.md"
    review.parent.mkdir(parents=True, exist_ok=True)
    icon, colour = STYLE["review"]
    review.write_text(
        f"---\nkind: review\nicon: {icon}\niconColor: \"{colour}\"\n"
        f"week: {TODAY.strftime('%G-W%V')}\ncreated: {d(0)}\n---\n\n"
        f"# {TODAY.strftime('%G-W%V')}\n\n"
        "Pinned to this note's own `week`, so it stays a record of this week rather than a\n"
        "rolling window ending today.\n\n"
        "## Closed this week\n\n" + review_block(
            "Closed", 'closed.format("GGGG-[W]WW") == formula.wk',
            ["file.name", "note.kind", "note.type", "note.closed", "note.project"],
            "note.closed", "DESC") + "\n\n"
        "## Due this week\n\n" + review_block(
            "Due this week", 'due.format("GGGG-[W]WW") == formula.wk',
            ["file.name", "done", "note.status", "note.due", "note.priority", "note.project"],
            "note.due", "ASC") + "\n\n"
        "## Routines missed\n\nLive, not pinned — `last_done` holds one value, not a history.\n\n"
        "![[Today.base#Routines due]]\n\n"
        "## Reflection\n\nWhat went well:\n\nWhat to change next week:\n", encoding="utf-8"
    )
    written += 1
    print(f"wrote {written} demo notes")
    print()
    print("  Reload Obsidian now (Cmd+R) if it is open.")
    print("  These files were written behind its back, so Iconize has registered their")
    print("  icons but the file explorer has not drawn them yet -- notes will show up")
    print("  with no icon until a reload. Nothing is wrong.")
    print()
    print("  Remove them again with: python3 demo/demo.py clear")


def clear():
    removed = 0
    for path in paths():
        if path.exists():
            path.unlink()
            removed += 1
    print(f"removed {removed} demo notes")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "load":
        load()
    elif action == "clear":
        clear()
    else:
        print(__doc__)
        sys.exit(1)
