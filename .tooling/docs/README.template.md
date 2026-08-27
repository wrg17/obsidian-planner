<!-- This is the source for ../../README.md. Edit here, then run
     `python -m planner.docsgen --write` from .tooling/.
     The rendered README carries no markers, because it sits in the vault and
     Obsidian shows anything that is not a %%comment%%. -->

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
| `.tooling/` | Everything that is **not** notes: the Python package, its tests, the demo generator. Dot-prefixed so Obsidian never sees it |
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
python3 .tooling/demo/demo.py load     # ~25 notes: every view populated
python3 .tooling/demo/demo.py clear    # delete exactly those again
```

**Reload Obsidian (`Cmd+R`) after either command**, and **close it first if you use Obsidian
Sync.** Both write files behind the app's back. Iconize only draws a note's icon when the file
explorer renders it, so fresh notes appear unadorned until you reload — harmless. Sync is not
harmless: it reads a rapid delete-then-recreate as a conflict and restores the deleted file
beside the new one, leaving `Note 2`, `Note 3` copies throughout the vault. `clear` still removes
them, because it matches the `demo: true` frontmatter marker rather than filenames, but they
should not be created in the first place.

It covers all seven statuses, all five issue types, priorities 1–4, a blocked ticket, a cancelled
one and a closed subtask. Dates are generated relative to today, so something is always due today,
something is overdue, and a routine is a week late — the board looks alive whenever you run it.

None of it is committed here — `clear` deletes every file it created, so run that before you start
adding real work.

`Bases/Triage.base` ships empty and should stay that way — every view in it is a "something is
wrong" query. To confirm it works, set any item's `priority` to `9`; it shows up in **Invalid
values** immediately, and reverting clears it.

## Python package, API and MCP

The vault is plain markdown and works with no Python at all. Alongside it, `src/planner`
models the same rules as code — so notes can be created and validated without Obsidian
open, and so the vault can check itself, which markdown alone cannot.

Everything runs from a `Makefile` in `.tooling/`. Python has no `package.json`
equivalent — `[project.scripts]` declares installed console entry points rather than
tasks, and `tox`/`nox` solve version matrices rather than everyday commands — so a
Makefile is what most Python projects settle on. Run `make` on its own for the list.

**Docker is the only dependency.** Postgres is a compose service, never something to
install and remember to start: `make db` brings it up, and every target that needs it
depends on that.

```sh
cd .tooling
make install     # venv and all extras
make test        # starts the db, runs the suite with coverage
make run         # starts the db, serves the API on the host with --reload
make up          # or: API in a container too
```

### Containers

`docker-compose.yml` runs the API and its audit database.

```sh
make up          # start;  http://127.0.0.1:8000/docs
make logs        # follow the API
make audit       # recent operations from the audit log
make test-docker # run the suite in a container against the compose Postgres
make down        # stop, keeping the database
make clean       # stop and delete the audit volume (the vault is untouched)
```

The vault is **bind-mounted, never copied**. It is a directory Obsidian edits
continuously on the host, and a copy would be a second source of truth that diverges the
moment either side writes — so the container becomes one more writer alongside Obsidian,
which is the position the local process is in too, and why the journal's conflict
handling exists.

Only the five note folders are mounted, not the repository root: the API reads nothing
else, and mounting `..` would hand the container the source tree, `.git`, and a 178 MB
virtualenv for no reason.

The suite gets its own database, `planner_test`, beside `planner` —
`pytest-postgresql` creates and drops whatever database it is handed, so pointing it at
the real one would delete the audit history on every run.

Postgres is published on `127.0.0.1:55433` rather than 5432, which is usually a local
server, or 5433, which is often an ssh tunnel. The API keeps 8000, so `make up` and
`make run` cannot both hold it — deliberately.

**If `make up` seems to hang, look for a container stuck in `Created`.** A `compose up`
that is interrupted part-way can leave one holding the vault mount, and every later mount
of an overlapping path hangs too. That looks convincingly like a file-sharing or iCloud
problem and is not one — `docker rm -f` the stuck container and try again. Any runtime
works; on Colima, `colima ssh -- ls /path/to/vault` confirms the VM can see it, and a
vault anywhere under `$HOME` needs no extra mount configuration.

### Doing it by hand

```sh
cd .tooling
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,api,mcp,postgres]"
PLANNER_VAULT=.. .venv/bin/pytest                   # the suite; fails under 98% coverage
PLANNER_VAULT=.. .venv/bin/uvicorn planner.api:app  # http://127.0.0.1:8000/docs
PLANNER_VAULT=.. .venv/bin/python -m planner.mcp    # MCP server over stdio
```

### Layers

<!-- generated:layers -->
```
api/         FastAPI: routes, middleware, controllers, DTOs
contracts/   wire shapes shared by every transport
domain/      entities, vocabularies, validation — no IO, no framework
mcp/         MCP tools over the same service
repository/  persistence port, markdown adapter, reversible commands, unit of work, journals
service/     business rules, transport-agnostic
```
<!-- /generated:layers -->

Each layer may only import downward, and `.tooling/tests/architecture.integration.test.py`
enforces it by parsing the imports — including that the domain never imports FastAPI, pydantic or `pathlib`.
REST and MCP share one `NoteService`, so closing a ticket stamps `closed` on both; a
second front end that reimplemented that rule would drift within a month.

```python
from planner import open_vault
service = open_vault(".")
service.create(kind="task", title="Pick a type scale", parent="Design system")
service.close("Pick a type scale")      # status, done and closed move together
service.problems()                      # the Triage base, as a function call
```

### Generated documentation

The endpoint table above, the layer diagram, and the vocabulary and note-type tables in
`System.md` are **generated from the code** from a template in
`.tooling/docs/`. Everything around them is hand-written, which is the part worth
writing — edit the template, not this file.

```sh
.venv/bin/python -m planner.docsgen --check   # fails if stale
.venv/bin/python -m planner.docsgen --write   # regenerate
```

A test runs `--check`, so prose that has fallen behind the code fails the suite rather
than being believed by a reader. This was not hypothetical: when it was added the README
listed seven endpoints against twelve in the routing table.

### Tests and coverage

Test files are named for the module they cover and mirror the source tree:

```
src/planner/domain/note.py   ->  tests/domain/note.integration.test.py
src/planner/api/routers/notes.py ->  tests/api/routers/notes.integration.test.py
```

A dotted filename is not a legal module name, so this needs `--import-mode=importlib`
and `python_files = ["*.test.py"]` — both set in `pyproject.toml`, so plain `pytest`
works. `architecture.integration.test.py` is the one file not named for a module; it
checks the layering, and also that every module *has* a test file, so a new one cannot
slip in untested.

Endpoint behaviour is specified as numbered **invariants** in the route docstrings, and
the system-wide ones (S1-S9) in `api/app.py` — which are also published in the OpenAPI
description, so a client author never has to read the source. Tests name the invariant
they prove (`test_D2_deleting_a_parent_is_refused`), so a failure points at a stated
rule rather than a bare assertion.

```sh
cd .tooling
.venv/bin/pytest                       # runs with coverage; fails under 98%
.venv/bin/pytest tests/domain          # one layer
.venv/bin/pytest --no-cov -q           # quick loop
open htmlcov/index.html                # line-by-line report
.venv/bin/pdoc planner -o docs/api     # API reference from docstrings
.venv/bin/python -m planner.docsgen --write   # refresh generated doc sections
```

Coverage is branch-level and gated at 98% in `addopts`, so a drop fails the run rather
than being noticed later. `mcp/__main__.py` is the one exclusion — running it means
starting a real stdio server; the dispatch it calls is tested directly.

### REST

Swagger UI at `/docs`, OpenAPI at `/openapi.json`.

<!-- generated:endpoints -->
| | |
|---|---|
| `GET /notes` | List notes |
| `POST /notes` | Create a note |
| `POST /notes/bulk` | Create several notes as one transaction |
| `GET /notes/{title}` | Fetch one note |
| `PATCH /notes/{title}` | Update a note |
| `DELETE /notes/{title}` | Delete a note |
| `GET /notes/{title}/children` | Direct children |
| `POST /notes/{title}/close` | Close a ticket |
| `POST /notes/{title}/reopen` | Reopen a ticket |
| `GET /schema` | Kinds, fields, vocabularies |
| `GET /problems` | Notes that fail to validate |
| `GET /health` | Liveness and vault reachability |
<!-- /generated:endpoints -->
| `POST /notes` | folder derived from `kind`; defaults applied |
| `POST /notes/bulk` | a batch as one transaction — all of them or none |
| `GET·PATCH·DELETE /notes/{title}` | `null` in a PATCH removes the field |
| `GET /notes/{title}/children` | `?recursive=true` for the whole subtree |
| `POST /notes/{title}/close` · `/reopen` | the three fields that must move together |
| `GET /schema` · `/problems` · `/health` | rules, triage, liveness |

Vocabularies are **declared enums**, not prose. `kind` is a `$ref` to a ten-value enum
generated from the domain, so `"Epic"` fails at the contract rather than deep inside —
and Swagger renders a dropdown. Both validation layers return the same `{detail, field}`
error shape, since which one fired is an implementation detail.

**Writes are transactional.** Every filesystem mutation is a reversible command, and
multi-note operations run inside a unit of work — so a cascade delete or a bulk create
that fails part-way restores what it had already changed. Individual writes land by
temp-file-and-rename, which is atomic on POSIX, so a crash cannot leave Obsidian a
half-written note to parse. **A crash is recoverable.** Intent is flushed to a write-ahead journal before each
change lands, and startup undoes anything a crash abandoned. The interesting case is a
file that changed *after* the crash: provenance is not observable — the filesystem
stores bytes, not an author — so recovery compares hashes instead.

| file at recovery | inference | action |
|---|---|---|
| matches the recorded prior | our write never landed | nothing |
| matches what we intended | our write landed, transaction broke | restore prior |
| matches neither | someone edited it after the crash | **leave it**, report a conflict |

The last row is the one that matters: a change we cannot account for can only have come
from a person editing their own notes, and their edit is newer than our abandoned
transaction. `GET /health` reports an interrupted transaction so the condition is never
silent.

### Audit log

Set `PLANNER_DSN` and every operation is recorded in Postgres — what changed, at whose
request, and how it ended (`committed · rolled_back · recovered · conflicted`). Because
each row keeps the prior content, the log serves three purposes at once: crash recovery
reads the in-flight rows, provenance compares the last committed hash for a path against
the file to tell your writes from Obsidian's, and history gives an undo stack.

Committed operations are pruned after 30 days — `prior_content` grows with the volume of
text edited, not the number of operations. Anything that *didn't* go cleanly is kept
indefinitely: it is evidence, and the reason to keep a log is to still have it when
someone asks.

**If Postgres is unreachable the API degrades to the file journal and keeps working.** A
database being down is not a reason you cannot write a note in your own vault. Crash
recovery is unaffected; the cost is a gap in the audit trail, and it is logged as a gap
rather than passed over.

What Postgres does *not* buy is a real transaction. `COMMIT` is a promise about rows; it
cannot roll back a write to the vault, and the filesystem cannot participate in
two-phase commit. Compensation stays in the code.

**The contract is all-or-nothing.** Rollback restores prior content by writing the old
bytes back. One thing can break that: a file edited outside the API between our write
and our rollback, in which case the outside edit is kept rather than overwritten. The
exposure is ~5 ms for a single-file transaction against a ~2 s Obsidian autosave, on the
exact file the transaction is holding — so it is close to unreachable, and is treated as
an anomaly rather than a mode. When it does happen the operation is recorded as
`conflicted`, never pruned, so a vault left in a mixed state says so.

Three limits are documented rather than hidden — see `repository/journal.py`. The
transaction is not *isolated* (Obsidian sees each write as it lands, including ones
later rolled back); recovery never *rolls forward*; and clearing the journal cannot be
atomic with the last file write, so a crash in that window undoes a transaction that
actually succeeded. The last needs two-phase commit to fix, and the filesystem cannot
participate.

Links are plain titles: send `"parent": "Design system"` and storage writes
`parent: "[[Design system]]"`. Point at a vault with `PLANNER_VAULT=/path/to/vault`.
Every response carries `x-request-id` and `x-response-time-ms`.

### MCP

Ten tools, with schemas generated from the same vocabularies as everything else. That
matters more here than for REST: a model reads the tool schema as the specification, and
given `"type": "string"` it will confidently send `"Epic"`.

**A tool and an endpoint show the same documentation.** Both read
`contracts/operations.py`, which holds, per operation, a one-line summary, the guidance
someone meeting it for the first time needs, and the numbered invariants it upholds. An
earlier version wrote the two separately, on the theory that a model and a developer want
different things — which was wrong. A developer new to the repo does not know to read
`GET /schema` before creating a note any more than a model does.

The **inventory** has to agree too: `COVERS` maps every tool to its route, `NOT_EXPOSED`
records the routes deliberately left out and why, and a test fails on any route in
neither. That check found `reopen_note` missing beside `close_note` — a model could
close a ticket and not reopen it, which nobody had decided.

```json
{ "mcpServers": { "planner": {
    "command": "/path/to/planner/.venv/bin/python",
    "args": ["-m", "planner.mcp"],
    "env": { "PLANNER_VAULT": "/path/to/planner" } } } }
```

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
