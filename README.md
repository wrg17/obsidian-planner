# Planner — Jira + Confluence in an Obsidian vault

A starter vault that gives you typed tickets, a kanban-style board, project/epic/task hierarchy,
decision records and meeting notes, built almost entirely on **Obsidian Bases** — no Dataview, no
scripting required to use it.

Clone it, open it as a vault, install two plugins, and you have a working planner with worked
example content you can delete.

## What's in it

| | |
|---|---|
| `Bases/` | Six `.base` files: **Board**, **Today**, **Portfolio**, **Triage**, **Docs**, **Meetings** |
| `Items/` | Areas, projects, epics, tasks, subtasks, routines — flat, related by link properties |
| `Docs/` | Specs and decision records (ADRs) |
| `Meetings/`, `Reviews/`, `Journal/` | Meeting notes, weekly reviews, daily notes |
| `Templates/` | 11 self-filing templates |
| `Home.md` | Your-work dashboard |
| `System.md` | **The manual.** How it works, the vocabularies, and every gotcha found building it |

Ten note types share one `kind` discriminator: `area · project · epic · task · subtask · routine ·
doc · decision · meeting · review`. Tickets carry `status`, `type` (feature/bug/chore/spike/
research), `priority`, dates, and a `done` checkbox for one-click completion.

## Requirements

- **Obsidian 1.13+** (Bases must support `groupBy` on formulas, `sort`, and `newItemFolder`)
- Core plugins: **Bases**, **Templates**, **Daily notes**, **Properties**
- Community plugins: **Iconize** (icons, cosmetic) and **Templater** (self-filing templates)

Plugin code is not vendored — install both from Community plugins. Templater's settings are tracked,
so its config arrives with the clone. Iconize's store is **not**: it is rewritten on every launch, so
tracking it would leave a dirty tree after simply opening the vault. Note icons rebuild themselves
from the `icon:`/`iconColor:` frontmatter every note carries; **folder** icons have no frontmatter to
rebuild from, so set those once from the table in `System.md` → *Icons*.

Treat everything under `.obsidian/` as an app-written snapshot: change it in Settings, never in a
text editor. Both plugins load their `data.json` once at startup and rewrite it from memory with no
watcher for external edits, so hand-editing is silently discarded. If icons ever look missing, the
repair is **Settings → Iconize → Refresh icons from frontmatter** + restart — the frontmatter in
your notes is the real source of truth. See *Configuration ownership* in `System.md`.

## Setup

Follow the checklist at the top of `System.md`. It is nine steps and takes about two minutes; the
ones that actually matter are the template folder, the default new-note location, and the Daily
notes folder/template.

## Try it with the demo data

The repo ships **empty** — `Items/`, `Docs/`, `Meetings/`, `Reviews/` and `Journal/` contain
nothing. That is deliberate: your planner should start as yours. But an empty view and a broken
view look exactly alike, so there is a throwaway dataset:

```sh
python3 demo/demo.py load     # ~25 notes: every view populated
python3 demo/demo.py clear    # delete exactly those again
```

**Reload Obsidian (`Cmd+R`) after either command.** Both write files behind the app's back, and
Iconize only draws a note's icon when the file explorer renders it — so fresh notes appear with no
icon until you reload. The icons are registered; they just aren't painted yet.

It covers all seven statuses, all five issue types, priorities 1–4, a blocked ticket, a cancelled
one and a closed subtask. Dates are generated relative to today, so something is always due today,
something is overdue, and a routine is a week late — the board looks alive whenever you run it.

None of it is committed here — `clear` deletes every file it created, so run that before you start
adding real work.

`Bases/Triage.base` ships empty and should stay that way — every view in it is a "something is
wrong" query. To confirm it works, set any item's `priority` to `9`; it shows up in **Invalid
values** immediately, and reverting clears it.

## Python package and API

The vault is plain markdown and works with no Python at all. Alongside it, `src/planner`
models the same rules as code, so notes can be created and validated without Obsidian
open — and so the vault can check itself, which markdown alone cannot.

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,api]"
.venv/bin/pytest                                    # 104 tests
.venv/bin/uvicorn planner.api:app --reload          # http://127.0.0.1:8000/docs
```

`src/planner/schema.py` is the single source of truth: note kinds, their fields, and the
vocabularies. The vault layer, the API and the generated docs all read from it, so they
cannot drift — which is exactly how three copies of one formula once disagreed about when
a weekday routine was due.

```python
from planner import Vault
vault = Vault(".")
vault.create(kind="task", title="Pick a type scale", parent="Design system")
vault.close("Pick a type scale")        # status, done and closed move together
vault.problems()                        # the Triage base, as a function call
```

**REST API** — Swagger UI at `/docs`, OpenAPI at `/openapi.json`:

| | |
|---|---|
| `GET /notes` | filter by `kind`, `project`, `parent`, `status`, `open` |
| `POST /notes` | folder derived from `kind`; defaults applied |
| `GET·PATCH·DELETE /notes/{title}` | `null` in a PATCH removes the field |
| `POST /notes/{title}/close` | the three fields that must move together |
| `GET /schema` | kinds, fields and vocabularies the server enforces |
| `GET /problems` | notes that fail to parse or validate |

The API speaks plain titles, not Obsidian link syntax — send `"parent": "Design system"`
and the storage layer writes `parent: "[[Design system]]"`. Point it at a vault with
`PLANNER_VAULT=/path/to/vault`.

## Design notes

Three constraints shaped everything, and they're worth knowing before you customise:

1. **Bases has no board layout and no drag-and-drop.** The board is a cards view grouped into
   collapsible lanes by a `lane` formula; you move a ticket by editing its `status` cell or ticking
   `done`. Table views support inline editing, cell multi-select and paste, so bulk changes are one
   operation.
2. **Bases cannot walk a parent chain** — no joins, no recursion. Hierarchy is expressed as link
   properties, and `project` is deliberately denormalised onto every ticket so that
   "everything in this project" is expressible at all.
3. **Progress rollups come from group summaries**, not per-row aggregates: group by project or
   parent and sum a `done_num` formula. That is the only aggregation Bases offers, and it is
   enough.

`System.md` documents the rest, including several things that fail *silently* — unquoted hex in
`iconColor` being read as a YAML comment, Lucide icon names that don't exist in Obsidian's curated
subset, and `newItemTemplate` suppressing the property pre-fill that makes the factories work.
