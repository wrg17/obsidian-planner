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
